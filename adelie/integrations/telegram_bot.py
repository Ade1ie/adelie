"""
adelie/integrations/telegram_bot.py

Telegram bot that connects to a specific Adelie workspace.
Users can remotely control the AI loop, check status, and get reports.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# Ensure package is importable
_PKG_ROOT = os.environ.get("ADELIE_PKG_ROOT", str(Path(__file__).resolve().parent.parent.parent))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logger = logging.getLogger(__name__)


class AdelieTelegramBot:
    """Telegram bot bound to a specific Adelie workspace."""

    def __init__(self, token: str, workspace_path: str):
        self.token = token
        self.workspace_path = Path(workspace_path).resolve()
        self.adelie_dir = self.workspace_path / ".adelie"
        self._loop_task: asyncio.Task | None = None
        self._loop_running = False
        self._current_goal = ""

        # Set env for this workspace
        self._setup_workspace_env()

    def _setup_workspace_env(self) -> None:
        """Configure environment for the target workspace."""
        os.environ["WORKSPACE_PATH"] = str(self.adelie_dir / "workspace")
        config_path = self.adelie_dir / "config.json"
        if config_path.exists():
            ws_config = json.loads(config_path.read_text(encoding="utf-8"))
            env_map = {
                "provider": "LLM_PROVIDER",
                "gemini_api_key": "GEMINI_API_KEY",
                "gemini_model": "GEMINI_MODEL",
                "ollama_base_url": "OLLAMA_BASE_URL",
                "ollama_model": "OLLAMA_MODEL",
                "loop_interval": "LOOP_INTERVAL_SECONDS",
            }
            for key, env_key in env_map.items():
                if key in ws_config:
                    os.environ[env_key] = str(ws_config[key])

        # Reload config
        import importlib
        import adelie.config as cfg
        importlib.reload(cfg)

    def _get_config(self):
        import importlib
        import adelie.config as cfg
        importlib.reload(cfg)
        return cfg

    # ── Bot command handlers ──────────────────────────────────────────────

    def _get_welcome_message(self) -> str:
        """Build the detailed welcome message."""
        # Get current phase
        config_path = self.adelie_dir / "config.json"
        phase = "initial"
        provider = "ollama"
        model = "gemma3:12b"
        if config_path.exists():
            ws_config = json.loads(config_path.read_text(encoding="utf-8"))
            phase = ws_config.get("phase", "initial")
            provider = ws_config.get("provider", "ollama")
            if provider == "ollama":
                model = ws_config.get("ollama_model", "gemma3:12b")
            else:
                model = ws_config.get("gemini_model", "gemini-2.0-flash")

        phase_labels = {
            "initial": "🌱 초기 — Planning",
            "mid": "🔨 중기 — Implementation",
            "mid_1": "🚀 중기 1기 — Execution",
            "mid_2": "⚡ 중기 2기 — Stabilization",
            "late": "🛡️ 후기 — Maintenance",
            "evolve": "🧬 자율 발전 — Evolution",
        }
        phase_label = phase_labels.get(phase, phase)

        return (
            "🐧 *Adelie Bot에 오신 것을 환영합니다!*\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "Adelie는 자율형 AI 루프 시스템입니다.\n"
            "이 봇으로 워크스페이스를 원격 조작할 수 있습니다.\n\n"
            
            f"📂 *워크스페이스*\n`{self.workspace_path}`\n\n"
            f"⚙️ *현재 설정*\n"
            f"• Provider: `{provider}` (`{model}`)\n"
            f"• Phase: {phase_label}\n\n"
            
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "📋 *명령어 가이드*\n\n"
            
            "🔄 *AI 루프 제어*\n"
            "/run `목표` — AI 루프 시작\n"
            "  예: `/run SaaS 프로덕트 개발`\n"
            "/stop — AI 루프 즉시 중지\n\n"
            
            "📊 *모니터링*\n"
            "/status — 시스템 상태 확인\n"
            "  (Provider, KB, 루프 상태)\n"
            "/inform — Inform AI 보고서 생성\n"
            "  (프로젝트 전체 진행 상황)\n\n"
            
            "📚 *지식 관리*\n"
            "/kb — Knowledge Base 카테고리별 현황\n"
            "/config — 현재 설정 상세 조회\n"
            "/ollama — 설치된 Ollama 모델 목록\n\n"
            
            "/help — 이 도움말 다시 보기\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "💡 *시작하려면*: `/run 프로젝트 목표`를 입력하세요!"
        )

    async def _save_chat_id(self, chat_id: int) -> None:
        """Save chat_id to config for auto-greeting on restart."""
        config_path = self.adelie_dir / "config.json"
        if config_path.exists():
            ws_config = json.loads(config_path.read_text(encoding="utf-8"))
        else:
            ws_config = {}
        ws_config["telegram_chat_id"] = chat_id
        config_path.write_text(json.dumps(ws_config, indent=2, ensure_ascii=False), encoding="utf-8")

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command."""
        await self._save_chat_id(update.effective_chat.id)
        await update.message.reply_text(
            self._get_welcome_message(),
            parse_mode="Markdown",
        )

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command."""
        await self.cmd_start(update, context)

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /status command."""
        self._setup_workspace_env()
        cfg = self._get_config()
        from adelie.llm_client import get_provider_info
        from adelie.kb import retriever
        retriever.ensure_workspace()

        categories = retriever.list_categories()
        total = sum(categories.values())
        kb_parts = [f"{k}: {v}" for k, v in categories.items() if v > 0]

        loop_status = "🟢 Running" if self._loop_running else "⚪ Stopped"
        goal_text = f"\n🎯 Goal: _{self._current_goal}_" if self._current_goal else ""

        msg = (
            f"🐧 *Adelie Status*\n\n"
            f"⚙️ Provider: `{get_provider_info()}`\n"
            f"⏱️ Interval: `{cfg.LOOP_INTERVAL_SECONDS}s`\n"
            f"📚 KB: {total} file(s) ({', '.join(kb_parts) or 'empty'})\n"
            f"🔄 Loop: {loop_status}{goal_text}"
        )

        # Check provider health
        if cfg.LLM_PROVIDER == "ollama":
            import requests
            try:
                r = requests.get(f"{cfg.OLLAMA_BASE_URL}/api/tags", timeout=3)
                r.raise_for_status()
                models_count = len(r.json().get("models", []))
                msg += f"\n✅ Ollama: {models_count} model(s)"
            except Exception:
                msg += f"\n❌ Ollama: not connected"
        elif cfg.LLM_PROVIDER == "gemini":
            msg += "\n" + ("✅ Gemini: API key set" if cfg.GEMINI_API_KEY else "❌ Gemini: no API key")

        await update.message.reply_text(msg, parse_mode="Markdown")

    async def cmd_run(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /run <goal> command — start AI loop in background."""
        if self._loop_running:
            await update.message.reply_text("⚠️ Loop is already running. Use /stop first.")
            return

        goal = " ".join(context.args) if context.args else "Operate and improve the system"
        self._current_goal = goal

        await update.message.reply_text(
            f"🚀 Starting AI loop...\n🎯 Goal: _{goal}_",
            parse_mode="Markdown",
        )

        self._loop_running = True
        self._loop_task = asyncio.create_task(
            self._run_loop_async(goal, update.effective_chat.id, context)
        )

    async def _run_loop_async(
        self, goal: str, chat_id: int, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Run the AI loop in a background asyncio task."""
        self._setup_workspace_env()
        cfg = self._get_config()

        from adelie.agents import writer_ai, expert_ai
        from adelie.kb import retriever
        retriever.ensure_workspace()

        loop_count = 0
        try:
            while self._loop_running:
                loop_count += 1
                system_state = {
                    "situation": "normal",
                    "goal": goal,
                    "loop_iteration": loop_count,
                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                }

                # Run Writer AI
                try:
                    writer_result = await asyncio.to_thread(
                        writer_ai.run, system_state, None, loop_count
                    )
                except Exception as e:
                    await context.bot.send_message(
                        chat_id, f"❌ Writer AI error: `{e}`", parse_mode="Markdown"
                    )
                    system_state["situation"] = "error"
                    system_state["error_message"] = str(e)

                # Run Expert AI
                try:
                    decision = await asyncio.to_thread(
                        expert_ai.run, system_state, loop_count
                    )
                except Exception as e:
                    await context.bot.send_message(
                        chat_id, f"❌ Expert AI error: `{e}`", parse_mode="Markdown"
                    )
                    break

                action = decision.get("action", "CONTINUE")
                reasoning = decision.get("reasoning", "")
                next_sit = decision.get("next_situation", "normal")

                # Notify user of significant events
                if action != "CONTINUE" or loop_count % 5 == 0:
                    written_count = len(writer_result) if isinstance(writer_result, list) else 0
                    msg = (
                        f"📍 *Loop #{loop_count}*\n"
                        f"📝 Writer: {written_count} file(s)\n"
                        f"🧠 Expert: `{action}` → _{reasoning[:100]}_"
                    )
                    await context.bot.send_message(chat_id, msg, parse_mode="Markdown")

                if action == "SHUTDOWN":
                    await context.bot.send_message(chat_id, "🛑 Expert AI requested shutdown.")
                    break

                system_state["situation"] = next_sit

                # Sleep between cycles
                cfg = self._get_config()
                await asyncio.sleep(cfg.LOOP_INTERVAL_SECONDS)

        except asyncio.CancelledError:
            pass
        finally:
            self._loop_running = False
            await context.bot.send_message(chat_id, f"⏹️ Loop stopped after {loop_count} cycle(s).")

    async def cmd_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /stop command — stop AI loop."""
        if not self._loop_running:
            await update.message.reply_text("ℹ️ Loop is not running.")
            return

        self._loop_running = False
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()

        await update.message.reply_text("🛑 Stopping AI loop...")

    async def cmd_inform(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /inform command — generate status report."""
        await update.message.reply_text("📋 Generating project report...")

        self._setup_workspace_env()
        from adelie.agents import inform_ai

        goal = " ".join(context.args) if context.args else self._current_goal or ""
        system_state = {
            "situation": "normal",
            "goal": goal,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }

        try:
            report = await asyncio.to_thread(
                inform_ai.run, system_state, goal, 0
            )
            # Telegram has 4096 char limit — split if needed
            if len(report) <= 4000:
                await update.message.reply_text(report, parse_mode="Markdown")
            else:
                chunks = [report[i:i+4000] for i in range(0, len(report), 4000)]
                for i, chunk in enumerate(chunks):
                    await update.message.reply_text(
                        chunk, parse_mode="Markdown" if i == 0 else None
                    )
        except Exception as e:
            await update.message.reply_text(f"❌ Inform AI error: {e}")

    async def cmd_config(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /config command."""
        self._setup_workspace_env()
        config_path = self.adelie_dir / "config.json"
        if config_path.exists():
            ws_config = json.loads(config_path.read_text(encoding="utf-8"))
        else:
            ws_config = {}

        provider = ws_config.get("provider", "gemini")
        msg = (
            f"⚙️ *Configuration*\n\n"
            f"Provider: `{provider}`\n"
        )
        if provider == "ollama":
            msg += f"Model: `{ws_config.get('ollama_model', 'llama3.2')}`\n"
            msg += f"URL: `{ws_config.get('ollama_base_url', 'http://localhost:11434')}`\n"
        else:
            msg += f"Model: `{ws_config.get('gemini_model', 'gemini-2.0-flash')}`\n"
        msg += f"Interval: `{ws_config.get('loop_interval', 30)}s`\n"
        msg += f"Workspace: `{self.workspace_path}`"

        await update.message.reply_text(msg, parse_mode="Markdown")

    async def cmd_kb(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /kb command."""
        self._setup_workspace_env()
        from adelie.kb import retriever
        retriever.ensure_workspace()

        categories = retriever.list_categories()
        lines = ["📚 *Knowledge Base*\n"]
        total = 0
        for cat, count in categories.items():
            emoji = {"skills": "🛠️", "logic": "🧠", "errors": "⚠️",
                     "dependencies": "📦", "exports": "📤", "maintenance": "🔧"}.get(cat, "📁")
            lines.append(f"{emoji} {cat}: {count}")
            total += count
        lines.append(f"\n📊 Total: {total} file(s)")

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    async def cmd_ollama(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /ollama command."""
        self._setup_workspace_env()
        cfg = self._get_config()
        import requests

        try:
            r = requests.get(f"{cfg.OLLAMA_BASE_URL}/api/tags", timeout=5)
            r.raise_for_status()
            models = r.json().get("models", [])
            if not models:
                await update.message.reply_text("No Ollama models installed.")
                return

            lines = ["🦙 *Ollama Models*\n"]
            for m in models:
                name = m.get("name", "")
                size_gb = f"{m.get('size', 0) / 1e9:.1f}GB"
                active = " ← active" if cfg.OLLAMA_MODEL in name else ""
                lines.append(f"• `{name}` ({size_gb}){active}")

            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        except Exception:
            await update.message.reply_text(f"❌ Cannot connect to Ollama at {cfg.OLLAMA_BASE_URL}")

    async def cmd_unknown(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle unknown commands."""
        await update.message.reply_text("❓ Unknown command. Use /help to see available commands.")

    # ── Bot setup & run ───────────────────────────────────────────────────

    async def _post_init(self, application: Application) -> None:
        """Set bot commands menu and send auto-greeting on startup."""
        await application.bot.set_my_commands([
            BotCommand("start", "환영 & 도움말"),
            BotCommand("status", "시스템 상태"),
            BotCommand("run", "AI 루프 시작"),
            BotCommand("stop", "AI 루프 중지"),
            BotCommand("inform", "프로젝트 보고서"),
            BotCommand("config", "설정 조회"),
            BotCommand("kb", "Knowledge Base"),
            BotCommand("ollama", "Ollama 모델"),
            BotCommand("help", "도움말"),
        ])

        # Auto-send greeting to saved chat_id
        config_path = self.adelie_dir / "config.json"
        if config_path.exists():
            ws_config = json.loads(config_path.read_text(encoding="utf-8"))
            chat_id = ws_config.get("telegram_chat_id")
            if chat_id:
                try:
                    await application.bot.send_message(
                        chat_id=chat_id,
                        text=(
                            "🐧 *Adelie Bot이 시작되었습니다!*\n\n"
                            f"📂 워크스페이스:\n`{self.workspace_path}`\n\n"
                            "준비 완료! /help 로 명령어를 확인하세요.\n"
                            "바로 시작하려면: `/run 목표`를 입력하세요!"
                        ),
                        parse_mode="Markdown",
                    )
                except Exception as e:
                    print(f"   ⚠️  Auto-greeting failed: {e}")
                    print(f"   Telegram에서 봇에게 /start 를 먼저 보내주세요.")

    def start(self) -> None:
        """Build and start the Telegram bot."""
        app = (
            Application.builder()
            .token(self.token)
            .post_init(self._post_init)
            .build()
        )

        # Register handlers
        app.add_handler(CommandHandler("start", self.cmd_start))
        app.add_handler(CommandHandler("help", self.cmd_help))
        app.add_handler(CommandHandler("status", self.cmd_status))
        app.add_handler(CommandHandler("run", self.cmd_run))
        app.add_handler(CommandHandler("stop", self.cmd_stop))
        app.add_handler(CommandHandler("inform", self.cmd_inform))
        app.add_handler(CommandHandler("config", self.cmd_config))
        app.add_handler(CommandHandler("kb", self.cmd_kb))
        app.add_handler(CommandHandler("ollama", self.cmd_ollama))
        # Unknown commands
        app.add_handler(MessageHandler(filters.COMMAND, self.cmd_unknown))

        print(f"🐧 Adelie Telegram Bot started")
        print(f"   Workspace: {self.workspace_path}")
        print(f"   Press Ctrl+C to stop")

        app.run_polling(allowed_updates=Update.ALL_TYPES)
