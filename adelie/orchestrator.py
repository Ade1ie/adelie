"""
adelie/orchestrator.py

Endless loop controller.

State machine:
  NORMAL      → Writer AI → Expert AI → loop
  ERROR       → write to errors/ → Expert AI reads error KB → recovery
  EXPORT      → write to exports/ → continue
  MAINTENANCE → pause loop → resume on signal
"""

from __future__ import annotations

import json
from typing import Callable, Optional
import signal
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from enum import Enum
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

from adelie.agents import expert_ai, writer_ai
from adelie.config import LOOP_INTERVAL_SECONDS, WORKSPACE_PATH, PROJECT_ROOT, ADELIE_ROOT, MCP_ENABLED
from adelie.context_compactor import CycleHistory
from adelie.context_engine import AgentType, AssembledContext, assemble_context, after_cycle, get_budget
from adelie.hooks import HookEvent, HookManager
from adelie.kb import retriever
from adelie.loop_detector import LoopDetector, LoopLevel
from adelie.process_supervisor import ProcessSupervisor
from adelie.scheduler import Scheduler
from adelie.phases import Phase

console = Console()


# ── Loop States ───────────────────────────────────────────────────────────────

class LoopState(str, Enum):
    NORMAL      = "normal"
    ERROR       = "error"
    EXPORT      = "export"
    MAINTENANCE = "maintenance"
    NEW_LOGIC   = "new_logic"
    SHUTDOWN    = "shutdown"


# ── Orchestrator ──────────────────────────────────────────────────────────────

class Orchestrator:
    MAX_RECOVER_RETRIES = 3
    MAX_NEW_LOGIC_CYCLES = 3  # Force transition after N cycles in new_logic

    def __init__(self, goal: str | None = None, phase: str = "initial"):
        self.goal = goal or "Autonomously develop and improve the project"
        self.phase = phase
        self.state = LoopState.NORMAL
        self.last_expert_output: dict | None = None
        self.last_error: str | None = None
        self._running = True
        self._recover_count = 0
        self._new_logic_count = 0
        self._phase_ready_count = 0      # How many cycles the system has recommended transition
        self._phase_recommendation: str | None = None  # Recommended next phase
        self._pause_requested = False    # Controlled by interactive CLI

        # Restore persisted state from config.json
        self.loop_iteration = 0
        self._test_pass_history: list[bool] = []
        self._review_score_history: list[int] = []
        self._restore_state()

        # Loop detection
        self._loop_detector = LoopDetector()

        # Cycle history for context compaction
        self._cycle_history = CycleHistory(detail_window=3, max_summary_tokens=500)

        # Agent scheduler
        self.scheduler = Scheduler()

        # Hook manager for plugins
        self.hooks = HookManager()

        # MCP manager (lazy — connects on first run)
        self._mcp_manager = None

        # Process supervisor for spawned commands
        self.supervisor = ProcessSupervisor(max_concurrent=5)

        # Lock to protect staging directory operations from race conditions
        # between the tester thread (Phase 3) and the main orchestrator thread.
        self._staging_lock = threading.Lock()



        # Graceful shutdown on Ctrl+C or SIGTERM
        signal.signal(signal.SIGINT,  self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        retriever.ensure_workspace()

        # Assembled context tracking for after_cycle token monitoring
        self._last_assembled_contexts: list | None = None
        self._last_build_errors: list[dict] = []

        # Auto-scan: if KB is empty and project has existing code, scan first
        self._auto_scan_done = False

        # ── TUI event callbacks (set by interactive.py) ───────────────────
        self._on_agent_start: Optional[Callable[[str], None]] = None
        self._on_agent_end: Optional[Callable[[str, str], None]] = None
        self._on_cycle_start: Optional[Callable[[int, str, str], None]] = None
        self._on_cycle_end: Optional[Callable[[dict], None]] = None

    def set_ui_callbacks(
        self,
        on_agent_start: Optional[Callable] = None,
        on_agent_end: Optional[Callable] = None,
        on_cycle_start: Optional[Callable] = None,
        on_cycle_end: Optional[Callable] = None,
    ) -> None:
        """Register TUI callbacks for real-time agent tracking."""
        self._on_agent_start = on_agent_start
        self._on_agent_end = on_agent_end
        self._on_cycle_start = on_cycle_start
        self._on_cycle_end = on_cycle_end

    def _emit_agent_start(self, agent_name: str) -> None:
        if self._on_agent_start:
            try:
                self._on_agent_start(agent_name)
            except Exception:
                pass

    def _emit_agent_end(self, agent_name: str, detail: str = "") -> None:
        if self._on_agent_end:
            try:
                self._on_agent_end(agent_name, detail)
            except Exception:
                pass

    def _handle_signal(self, sig, frame):
        console.print("\n[bold yellow]🛑 Shutdown signal received — finishing current cycle then stopping.[/bold yellow]")
        self._running = False

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _build_system_state(self) -> dict:
        from adelie.project_context import get_tree_summary, get_source_stats

        state = {
            "goal":           self.goal,
            "phase":          self.phase,
            "situation":      self.state.value,
            "loop_iteration": self.loop_iteration,
            "timestamp":      datetime.now().isoformat(timespec="seconds"),
            "error_message":  self.last_error,
            "tags":           self._situation_tags(),
            "project_tree":   get_tree_summary(),
            "source_stats":   get_source_stats(),
        }
        # Add cycle history for agent context
        history_ctx = self._cycle_history.get_context()
        if history_ctx:
            state["cycle_history"] = history_ctx
        # If system recommends a phase transition, tell the Expert AI
        if self._phase_recommendation:
            from adelie.phases import get_phase_label
            state["phase_recommendation"] = self._phase_recommendation
            state["phase_recommendation_label"] = get_phase_label(self._phase_recommendation)
            state["phase_ready_count"] = self._phase_ready_count
        # Include recent build errors for Expert AI context
        if self._last_build_errors:
            state["build_errors"] = self._last_build_errors[:3]  # 최대 3개
        return state

    def get_agent_context(self, agent_type: AgentType | str) -> dict:
        """
        Build tailored context for a specific agent using the context engine.
        Returns dict with 'rendered' (string) and 'metadata' (stats).
        """
        from adelie.project_context import get_tree_summary, get_source_stats, get_key_configs

        system_state = self._build_system_state()
        history_ctx = self._cycle_history.get_context()

        # Assemble using the context engine
        ctx = assemble_context(
            agent_type=agent_type,
            system_state=system_state,
            kb_index=retriever.get_index_summary(),
            cycle_history=history_ctx,
            project_tree=system_state.get("project_tree", ""),
            source_stats=system_state.get("source_stats"),
            key_configs=get_key_configs(),
        )

        # Track assembled context for after_cycle token monitoring
        if self._last_assembled_contexts is None:
            self._last_assembled_contexts = []
        self._last_assembled_contexts.append(ctx)

        return {
            "rendered": ctx.render(),
            "total_tokens": ctx.total_tokens,
            "budget": ctx.budget,
            "within_budget": ctx.within_budget,
            "truncated": ctx.truncated_sections,
        }

    def _situation_tags(self) -> list[str]:
        tag_map = {
            LoopState.ERROR:       ["error", "recovery"],
            LoopState.EXPORT:      ["export", "output"],
            LoopState.MAINTENANCE: ["maintenance", "health"],
            LoopState.NEW_LOGIC:   ["logic", "bootstrap"],
            LoopState.NORMAL:      [],
        }
        return tag_map.get(self.state, [])

    def _check_phase_readiness(self) -> str | None:
        """
        Check if conditions for the next phase are met.
        Returns the next phase value if ready, None otherwise.
        Does NOT actually transition — just recommends.
        """
        from adelie.phases import Phase
        from adelie.config import LLM_PROVIDER

        categories = retriever.list_categories()
        total_files = sum(categories.values())

        # Build a set of existing filenames for checking
        kb_files = set()
        for cat_dir in WORKSPACE_PATH.iterdir():
            if cat_dir.is_dir():
                for f in cat_dir.glob("*.md"):
                    kb_files.add(f.stem.lower())

        # Local models need more loops — quality per cycle is lower
        loop_mult = 2.0 if LLM_PROVIDER == "ollama" else 1.0

        # Quality metrics for phase gates
        recent_tests = self._test_pass_history[-5:]  # last 5
        test_pass_rate = (sum(recent_tests) / len(recent_tests)) if recent_tests else 0
        recent_scores = self._review_score_history[-5:]
        avg_review_score = (sum(recent_scores) / len(recent_scores)) if recent_scores else 0

        transitions = {
            Phase.INITIAL: {
                "next": Phase.MID,
                "check": lambda: (
                    total_files >= 5
                    and any("roadmap" in f for f in kb_files)
                    and any("architecture" in f or "vision" in f for f in kb_files)
                ),
                "min_loops": int(8 * loop_mult),
            },
            Phase.MID: {
                "next": Phase.MID_1,
                "check": lambda: (
                    total_files >= 8
                    and any("implementation" in f or "test" in f for f in kb_files)
                    and avg_review_score >= 4  # Quality gate
                ),
                "min_loops": int(15 * loop_mult),
            },
            Phase.MID_1: {
                "next": Phase.MID_2,
                "check": lambda: (
                    total_files >= 10
                    and any("operations" in f or "test_result" in f for f in kb_files)
                    and test_pass_rate >= 0.3  # At least some tests pass
                    and avg_review_score >= 5  # Quality gate
                ),
                "min_loops": int(20 * loop_mult),
            },
            Phase.MID_2: {
                "next": Phase.LATE,
                "check": lambda: (
                    total_files >= 12
                    and any("deploy" in f or "stability" in f for f in kb_files)
                    and test_pass_rate >= 0.5  # Half tests pass
                    and avg_review_score >= 6  # Good quality
                ),
                "min_loops": int(25 * loop_mult),
            },
            Phase.LATE: {
                "next": Phase.EVOLVE,
                "check": lambda: (
                    total_files >= 15
                    and any("feature_proposal" in f or "innovation" in f for f in kb_files)
                    and test_pass_rate >= 0.7  # Most tests pass
                    and avg_review_score >= 7  # High quality
                ),
                "min_loops": int(30 * loop_mult),
            },
        }

        rule = transitions.get(self.phase)
        if rule and self.loop_iteration >= rule["min_loops"] and rule["check"]():
            return rule["next"].value
        return None

    def _save_state(self) -> None:
        """Persist current phase, loop_iteration, and quality history to .adelie/config.json."""
        config_path = WORKSPACE_PATH.parent / "config.json"
        if config_path.exists():
            cfg_data = json.loads(config_path.read_text(encoding="utf-8"))
        else:
            cfg_data = {}
        cfg_data["phase"] = self.phase
        cfg_data["loop_iteration"] = self.loop_iteration
        cfg_data["test_pass_history"] = self._test_pass_history[-10:]
        cfg_data["review_score_history"] = self._review_score_history[-10:]
        config_path.write_text(json.dumps(cfg_data, indent=2, ensure_ascii=False), encoding="utf-8")

    def _save_phase(self) -> None:
        """Persist current phase (alias for _save_state for backward compat)."""
        self._save_state()

    def _restore_state(self) -> None:
        """Restore loop_iteration and quality history from config.json."""
        config_path = WORKSPACE_PATH.parent / "config.json"
        if not config_path.exists():
            return
        try:
            cfg_data = json.loads(config_path.read_text(encoding="utf-8"))
            self.loop_iteration = cfg_data.get("loop_iteration", 0)
            self._test_pass_history = cfg_data.get("test_pass_history", [])
            self._review_score_history = cfg_data.get("review_score_history", [])
            if self.loop_iteration > 0:
                console.print(f"[dim]  ↻ Resumed from loop #{self.loop_iteration}[/dim]")
        except Exception:
            pass

    def _write_error_to_kb(self, error: Exception | str) -> None:
        """Directly write an error file to the KB errors/ folder."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        err_path: Path = WORKSPACE_PATH / "errors" / f"error_{ts}.md"
        content = (
            f"# Error Report\n\n"
            f"**Timestamp**: {datetime.now().isoformat()}\n"
            f"**Loop iteration**: {self.loop_iteration}\n"
            f"**Error**: {error}\n\n"
            f"## System State\n```json\n{json.dumps(self._build_system_state(), indent=2)}\n```\n"
        )
        err_path.write_text(content, encoding="utf-8")
        retriever.update_index(
            f"errors/{err_path.name}",
            tags=["error", "auto-generated"],
            summary=f"Auto-logged error at loop #{self.loop_iteration}: {str(error)[:80]}",
        )
        console.print(f"[red]📁 Error logged to[/red] [bold]{err_path.name}[/bold]")

    def _archive_errors(self) -> None:
        """Remove resolved error files from errors/ so they don't re-trigger recovery."""
        errors_dir = WORKSPACE_PATH / "errors"
        if not errors_dir.exists():
            return
        index = retriever.get_index()
        for err_file in list(errors_dir.glob("*.md")):
            rel = err_file.relative_to(WORKSPACE_PATH).as_posix()
            err_file.unlink()
            if rel in index:
                del index[rel]
            console.print(f"[dim]🗑️  Archived error file: {err_file.name}[/dim]")
        # Persist updated index
        retriever.INDEX_FILE.write_text(
            json.dumps(index, indent=2), encoding="utf-8"
        )

    def _write_export(self, export_data: dict) -> None:
        """Write Expert AI export data to the KB exports/ folder."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        exp_path: Path = WORKSPACE_PATH / "exports" / f"export_{ts}.json"
        exp_path.write_text(json.dumps(export_data, indent=2, ensure_ascii=False), encoding="utf-8")
        retriever.update_index(
            f"exports/{exp_path.name}",
            tags=["export", "output"],
            summary=f"Export at loop #{self.loop_iteration}",
        )
        console.print(f"[blue]📤 Export written to[/blue] [bold]{exp_path.name}[/bold]")

    def _verify_staged_files(self, written_files: list[dict]) -> tuple[list[dict], list[dict]]:
        """
        Verify staged files with lightweight syntax checks before promotion.
        Returns (passed, failed) file lists.
        """
        import shutil
        import subprocess
        staging_root = ADELIE_ROOT / "staging"
        # On Windows, 'python3' may resolve to the Microsoft Store stub
        # (WindowsApps/python3.EXE) which doesn't work. Prefer sys.executable.
        if sys.platform == "win32":
            python_bin = sys.executable
        else:
            python_bin = shutil.which("python3") or shutil.which("python") or sys.executable
        passed: list[dict] = []
        failed: list[dict] = []

        for finfo in written_files:
            filepath = finfo.get("filepath", "")
            if not filepath:
                continue
            staged_path = staging_root / filepath
            if not staged_path.exists():
                continue

            ext = staged_path.suffix.lower()
            error_msg = None

            # Python: py_compile check
            if ext == ".py":
                try:
                    result = subprocess.run(
                        [python_bin, "-m", "py_compile", str(staged_path)],
                        capture_output=True, text=True, timeout=10,
                    )
                    if result.returncode != 0:
                        error_msg = result.stderr[:200]
                except Exception:
                    pass  # If check fails, still promote

            # JS/TS: node --check (only for .js — .ts needs tsc)
            elif ext == ".js":
                try:
                    result = subprocess.run(
                        ["node", "--check", str(staged_path)],
                        capture_output=True, text=True, timeout=10,
                    )
                    if result.returncode != 0:
                        error_msg = result.stderr[:200]
                except Exception:
                    pass

            # JSON: parse check
            elif ext == ".json":
                try:
                    import json as _json
                    _json.loads(staged_path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, Exception) as e:
                    error_msg = str(e)[:200]

            if error_msg:
                failed.append({**finfo, "error": error_msg})
                console.print(
                    f"  [red]❌ Verify failed: {filepath}[/red] — {error_msg[:80]}"
                )
            else:
                passed.append(finfo)

        if failed:
            console.print(
                f"[yellow]⚠️  {len(failed)} file(s) failed verification, "
                f"{len(passed)} file(s) passed[/yellow]"
            )

        return passed, failed

    def _promote_staged_files(self, written_files: list[dict]) -> int:
        """Copy verified staged files from .adelie/staging/ to PROJECT_ROOT."""
        import shutil
        staging_root = ADELIE_ROOT / "staging"
        if not staging_root.exists():
            return 0

        # Verify before promoting
        passed, failed = self._verify_staged_files(written_files)

        # Create checkpoint before overwriting files
        if passed:
            try:
                from adelie.checkpoint import CheckpointManager
                cp_mgr = CheckpointManager()
                cp_mgr.create(
                    files=passed,
                    cycle=self.loop_iteration,
                    phase=self.phase,
                )
            except Exception as e:
                console.print(f"[dim]⚠️ Checkpoint creation failed (non-fatal): {e}[/dim]")

        promoted = 0
        for finfo in passed:
            filepath = finfo.get("filepath", "")
            if not filepath:
                continue
            staged_path = staging_root / filepath
            target_path = PROJECT_ROOT / filepath
            if staged_path.exists():
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(staged_path, target_path)
                promoted += 1
        if promoted:
            console.print(f"[bold green]✅ Promoted {promoted} file(s) from staging → project[/bold green]")
        return promoted

    def _cleanup_staging(self) -> None:
        """Remove all files from staging directory."""
        import shutil
        staging_root = ADELIE_ROOT / "staging"
        if staging_root.exists():
            shutil.rmtree(staging_root, ignore_errors=True)
            staging_root.mkdir(parents=True, exist_ok=True)

    def _collect_staged_files(self, since_time: float) -> list[dict]:
        """
        Collect code files from the staging directory modified after since_time.
        Uses a start-time anchor instead of a fixed offset to avoid race conditions
        when coder execution takes longer than expected.
        """
        from adelie.agents.coder_ai import STAGING_ROOT
        code_exts = {
            ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css",
            ".json", ".sql", ".go", ".rs", ".svelte", ".vue",
        }
        files: list[dict] = []
        if not STAGING_ROOT.exists():
            return files
        for f in STAGING_ROOT.rglob("*"):
            if (
                f.is_file()
                and f.suffix in code_exts
                and f.stat().st_mtime >= since_time
            ):
                rel = f.relative_to(STAGING_ROOT).as_posix()
                files.append({"filepath": rel, "language": "", "description": ""})
        return files

    def _write_maintenance_note(self) -> None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        maint_path: Path = WORKSPACE_PATH / "maintenance" / f"status_{ts}.md"
        content = (
            f"# Maintenance Window\n\n"
            f"**Started**: {datetime.now().isoformat()}\n"
            f"**Loop iteration**: {self.loop_iteration}\n"
            f"**Reason**: Expert AI requested a maintenance pause.\n"
        )
        maint_path.write_text(content, encoding="utf-8")
        retriever.update_index(
            f"maintenance/{maint_path.name}",
            tags=["maintenance"],
            summary=f"Maintenance at loop #{self.loop_iteration}",
        )

    # ── Single Cycle ──────────────────────────────────────────────────────────

    def run_cycle(self) -> None:
        """Execute one full Writer AI → Expert AI cycle."""
        self.loop_iteration += 1
        cycle_start_time = time.time()  # Track cycle timing
        from adelie.phases import get_phase_label
        from adelie.llm_client import reset_usage, get_usage, set_current_agent, clear_current_agent, get_agent_usage
        reset_usage()  # Reset token counters for this loop

        # Log rotation — keep only recent logs
        if self.loop_iteration % 3 == 0:
            from adelie.log_rotation import rotate_logs
            rotate_logs()

        # Track loop metrics
        loop_metrics = {
            "files_written": 0,
            "review_scores": [],
            "tests_passed": 0,
            "tests_total": 0,
            "cycle_time": 0.0,
            "parallel_phases": [],
        }

        phase_label = get_phase_label(self.phase)
        console.print(Rule(
            f"[bold]Loop #{self.loop_iteration}[/bold]  "
            f"state=[cyan]{self.state.value}[/cyan]  "
            f"phase=[magenta]{phase_label}[/magenta]"
        ))

        # Emit TUI cycle-start callback
        if self._on_cycle_start:
            try:
                self._on_cycle_start(self.loop_iteration, phase_label, self.state.value)
            except Exception:
                pass

        # Emit before-cycle hook
        self.hooks.emit(HookEvent.BEFORE_CYCLE, {
            "iteration": self.loop_iteration,
            "state": self.state.value,
            "phase": self.phase,
        })

        # Wait if pause was requested
        self._wait_if_paused()

        # ── Auto-scan on first run if KB is empty ─────────────────────────
        if not self._auto_scan_done:
            self._auto_scan_done = True
            kb_file_count = sum(retriever.list_categories().values())
            project_root = PROJECT_ROOT
            has_source = any(
                f.suffix in {".py", ".js", ".ts", ".jsx", ".tsx", ".svelte", ".vue", ".go", ".rs"}
                for f in project_root.rglob("*")
                if f.is_file()
                and not any(p in str(f) for p in [".adelie", "node_modules", "__pycache__", ".git", ".venv"])
            )
            if not kb_file_count and has_source:
                console.print("[bold cyan]📋 First run — scanning existing codebase...[/bold cyan]")
                try:
                    from adelie.agents.scanner_ai import run_scan
                    run_scan(project_root=project_root)
                except Exception as e:
                    console.print(f"[red]❌ Scanner error: {e}[/red]")

        system_state = self._build_system_state()

        # ── User Feedback Injection ───────────────────────────────────────────
        try:
            from adelie.feedback_queue import read_pending, format_for_prompt, mark_processed
            pending_feedback = read_pending()
            if pending_feedback:
                system_state["user_feedback"] = [{
                    "id": fb.get("id"),
                    "message": fb.get("message"),
                    "priority": fb.get("priority"),
                    "source": fb.get("source"),
                } for fb in pending_feedback]
                system_state["user_feedback_prompt"] = format_for_prompt(pending_feedback)
                console.print(f"[bold yellow]🗣️  {len(pending_feedback)} user feedback item(s) pending[/bold yellow]")
                # Mark as processed so they don't appear next cycle
                for fb in pending_feedback:
                    mark_processed(fb.get("id", ""))
        except Exception as e:
            console.print(f"[dim]⚠️ Feedback read error: {e}[/dim]")

        # ── Loop Detection Check ──────────────────────────────────────────────
        loop_result = self._loop_detector.check()
        intervention_prompt = ""
        if loop_result.stuck:
            if loop_result.level == LoopLevel.CRITICAL:
                console.print(
                    f"[bold red]🔄 LOOP DETECTED ({loop_result.detector}): "
                    f"{loop_result.message}[/bold red]"
                )
                # Force state transition on critical loops
                if self.state.value in ("new_logic", "error"):
                    console.print("[bold yellow]🔧 Forcing transition to NORMAL state[/bold yellow]")
                    self.state = LoopState.NORMAL
                    system_state["situation"] = "normal"
            else:
                console.print(
                    f"[yellow]⚠️ Loop warning ({loop_result.detector}): "
                    f"{loop_result.message}[/yellow]"
                )
            intervention_prompt = self._loop_detector.get_intervention_prompt(loop_result)

        # ── Writer AI ─────────────────────────────────────────────────────────
        writer_output = None
        try:
            set_current_agent("writer")
            self._emit_agent_start("Writer")
            writer_output = writer_ai.run(
                system_state=system_state,
                expert_output=self.last_expert_output,
                loop_iteration=self.loop_iteration,
            )
            self.scheduler.mark_ran("writer", self.loop_iteration)
            files_count = len(writer_output) if writer_output else 0
            self._emit_agent_end("Writer", f"{files_count} file(s) written")
        except Exception as e:
            console.print(f"[red]❌ Writer AI failed: {e}[/red]")
            self._write_error_to_kb(e)
            self.last_error = str(e)
            self.state = LoopState.ERROR
            self.hooks.emit(HookEvent.ON_ERROR, {
                "iteration": self.loop_iteration,
                "agent": "writer",
                "error": str(e),
            })
            return  # Skip Expert AI this cycle

        # ── Expert AI ─────────────────────────────────────────────────────────
        try:
            set_current_agent("expert")
            self._emit_agent_start("Expert")
            decision = expert_ai.run(
                system_state=system_state,
                loop_iteration=self.loop_iteration,
                intervention_prompt=intervention_prompt,
                writer_output=writer_output,
            )
            self.scheduler.mark_ran("expert", self.loop_iteration)
            action = decision.get("action", "CONTINUE")
            coder_count = len(decision.get("coder_tasks", []))
            self._emit_agent_end("Expert", f"{action}, {coder_count} coder task(s)")
        except Exception as e:
            console.print(f"[red]❌ Expert AI failed: {e}[/red]")
            self._write_error_to_kb(e)
            self.last_error = str(e)
            self.state = LoopState.ERROR
            self.hooks.emit(HookEvent.ON_ERROR, {
                "iteration": self.loop_iteration,
                "agent": "expert",
                "error": str(e),
            })
            return

        self.last_expert_output = decision
        self.last_error = None

        # ── Record cycle for loop detection ───────────────────────────────────
        kb_file_count = sum(retriever.list_categories().values())
        self._loop_detector.record_cycle(
            iteration=self.loop_iteration,
            state=self.state.value,
            expert_output=decision,
            writer_output=writer_output,
            kb_file_count=kb_file_count,
        )

        # ── Record cycle for context compaction ──────────────────────────────
        files_written_count = len(writer_output) if writer_output else 0
        self._cycle_history.record(
            iteration=self.loop_iteration,
            state=self.state.value,
            expert_output=decision,
            files_written=files_written_count,
            kb_total=kb_file_count,
        )

        # ── Phase transition logic (recommend → confirm) ──────────────────────
        from adelie.phases import Phase, get_phase_label
        recommended_next = self._check_phase_readiness()

        if recommended_next:
            self._phase_recommendation = recommended_next
            self._phase_ready_count += 1
            console.print(
                f"[yellow]💡 Phase transition recommended → {get_phase_label(recommended_next)} "
                f"({self._phase_ready_count}/5 — waiting for Expert AI confirmation)[/yellow]"
            )
        else:
            self._phase_recommendation = None
            self._phase_ready_count = 0

        # Expert AI can confirm transition via suggested_phase
        suggested_phase = decision.get("suggested_phase")
        if suggested_phase and suggested_phase != self.phase:
            phase_order = [p.value for p in Phase]
            try:
                current_idx = phase_order.index(self.phase)
                suggested_idx = phase_order.index(suggested_phase)
                # Allow forward transitions, or allow EVOLVE to cycle back to earlier phases
                if suggested_idx > current_idx or self.phase == Phase.EVOLVE.value:
                    old_phase = self.phase
                    old = get_phase_label(old_phase)
                    self.phase = suggested_phase
                    new = get_phase_label(self.phase)
                    console.print(f"[bold green]✅ Expert AI confirmed phase → {new}[/bold green]")
                    self._save_phase()
                    self._phase_ready_count = 0
                    self._phase_recommendation = None
                    self.hooks.emit(HookEvent.PHASE_CHANGE, {
                        "iteration": self.loop_iteration,
                        "old_phase": old_phase,
                        "new_phase": self.phase,
                    })
            except ValueError:
                pass

        # Safety valve: force transition if Expert AI ignores too many recommendations
        # Local models get more patience (8 cycles vs 5 for API)
        from adelie.config import LLM_PROVIDER
        max_ignore = 8 if LLM_PROVIDER == "ollama" else 5
        if self._phase_ready_count >= max_ignore and self._phase_recommendation:
            old_phase = self.phase
            old = get_phase_label(old_phase)
            self.phase = self._phase_recommendation
            new = get_phase_label(self.phase)
            console.print(
                f"[bold magenta]🔄 Auto Phase Transition ({max_ignore}x recommended): {old} → {new}[/bold magenta]"
            )
            self._save_phase()
            self._phase_ready_count = 0
            self._phase_recommendation = None
            self.hooks.emit(HookEvent.PHASE_CHANGE, {
                "iteration": self.loop_iteration,
                "old_phase": old_phase,
                "new_phase": self.phase,
                "auto": True,
            })

        # ── Handle Expert AI decision ─────────────────────────────────────────
        action          = decision.get("action", "CONTINUE")
        next_situation  = decision.get("next_situation", "normal")
        export_data     = decision.get("export_data")

        # ══════════════════════════════════════════════════════════════════════
        # PHASE 2a: Research AI + Coder Manager (PARALLEL)
        # Both depend only on Expert AI decision — independent of each other.
        # Research writes to KB, Coder writes to staging.
        # ══════════════════════════════════════════════════════════════════════
        coder_tasks = decision.get("coder_tasks", [])
        all_written_files: list[dict] = []
        research_queries = decision.get("research_queries", [])

        # ── Plan Mode: intercept coder tasks for user approval ────────────
        from adelie.config import PLAN_MODE_ENABLED
        if PLAN_MODE_ENABLED and coder_tasks and self.phase != "initial":
            from adelie.plan_mode import PlanManager
            plan_mgr = PlanManager()
            # Expire old pending plans
            plan_mgr.expire_old_pending()
            # Check if there's an approved plan with these tasks
            pending = plan_mgr.get_pending()
            if pending is None:
                # Create a new plan and wait
                plan = plan_mgr.create_plan(
                    cycle=self.loop_iteration,
                    coder_tasks=coder_tasks,
                    expert_reasoning=decision.get("reasoning", ""),
                )
                console.print(
                    f"[bold yellow]📋 Plan Mode: Plan created ({plan.plan_id}) — "
                    f"{len(coder_tasks)} task(s) awaiting approval[/bold yellow]"
                )
                console.print(
                    f"[dim]  Use /approve to execute, /reject [reason] to reject, "
                    f"/plan to view details[/dim]"
                )
                # Skip coder execution this cycle
                coder_tasks = []
            elif pending.status.value == "pending":
                # Still pending — skip coder execution
                console.print(
                    f"[yellow]⏳ Plan Mode: Waiting for plan approval ({pending.plan_id})[/yellow]"
                )
                coder_tasks = []

        phase2_tasks: dict[str, dict] = {}  # name → {"fn": callable, "args": ...}

        # Prepare Research AI task
        run_research_parallel = (
            research_queries
            and self.scheduler.should_run("research", self.loop_iteration)
        )

        # Prepare Coder task
        run_coder_parallel = coder_tasks and self.phase != "initial"

        if run_research_parallel or run_coder_parallel:
            phase2_start = time.time()
            console.print("[dim]  ⚡ Phase 2a: parallel execution[/dim]", end="")
            parallel_names = []
            if run_research_parallel:
                parallel_names.append("Research")
            if run_coder_parallel:
                parallel_names.append("Coder")
            console.print(f"[dim] [{', '.join(parallel_names)}][/dim]")

            with ThreadPoolExecutor(max_workers=len(parallel_names), thread_name_prefix="adelie-p2") as pool:
                futures = {}

                if run_research_parallel:
                    def _run_research():
                        from adelie.agents.research_ai import run as run_research
                        set_current_agent("research")
                        self._emit_agent_start("Research")
                        return run_research(queries=research_queries, max_queries=5)
                    futures[pool.submit(_run_research)] = "research"

                if run_coder_parallel:
                    from adelie.phases import PHASE_INFO
                    phase_info = PHASE_INFO.get(self.phase, {})
                    max_layer = phase_info.get("max_coder_layer", 0)
                    coder_start_time = time.time()

                    def _run_coder():
                        from adelie.agents.coder_manager import run_coders
                        set_current_agent("coder")
                        self._emit_agent_start("Coder")
                        return run_coders(coder_tasks, max_active_layer=max_layer)
                    futures[pool.submit(_run_coder)] = "coder"

                for future in as_completed(futures, timeout=300):
                    agent_name = futures[future]
                    try:
                        result = future.result()
                        if agent_name == "research":
                            self.scheduler.mark_ran("research", self.loop_iteration)
                            loop_metrics["research_queries"] = len(research_queries)
                            loop_metrics["research_results"] = len(result) if result else 0
                            self._emit_agent_end("Research", f"{len(result) if result else 0} result(s)")
                        elif agent_name == "coder":
                            if result and result.get("total_files", 0) > 0:
                                all_written_files = self._collect_staged_files(coder_start_time)
                                loop_metrics["files_written"] = len(all_written_files)
                            self._emit_agent_end("Coder", f"{len(all_written_files)} file(s)")
                    except Exception as e:
                        console.print(f"[red]❌ {agent_name.title()} error: {e}[/red]")
                        self._emit_agent_end(agent_name.title(), f"error: {e}")

            phase2_elapsed = time.time() - phase2_start
            loop_metrics["parallel_phases"].append({"phase": "2a", "agents": parallel_names, "time": round(phase2_elapsed, 1)})
        else:
            # No Phase 2a work needed
            if run_coder_parallel is False and coder_tasks and self.phase != "initial":
                # Edge case guard — should not reach here
                pass

        # ══════════════════════════════════════════════════════════════════════
        # PHASE 2b: Reviewer AI → Coder Retry Loop (SEQUENTIAL — data dependency)
        # Reviewer needs Coder output; retry loop feeds back to Coder.
        # ══════════════════════════════════════════════════════════════════════
        MAX_REVIEW_RETRIES = 2
        reviewer_approved = False
        if all_written_files and self.phase != "initial" and self.scheduler.should_run("reviewer", self.loop_iteration):
            try:
                from adelie.agents.reviewer_ai import run_review
                from adelie.agents.coder_manager import run_coders
                from adelie.phases import PHASE_INFO
                set_current_agent("reviewer")
                self._emit_agent_start("Reviewer")
                self.scheduler.mark_ran("reviewer", self.loop_iteration)
                phase_info = PHASE_INFO.get(self.phase, {})
                max_layer = phase_info.get("max_coder_layer", 0)
                for task in coder_tasks:
                    name = task.get("name", "unnamed")
                    task_files = [f for f in all_written_files if any(
                        tf in f.get("filepath", "") for tf in task.get("files", [])
                    )] or all_written_files

                    for retry in range(MAX_REVIEW_RETRIES + 1):
                        review = run_review(coder_name=name, written_files=task_files)
                        score = review.get("overall_score", 5)
                        self._review_score_history.append(score)

                        if review.get("approved", True):
                            reviewer_approved = True
                            break
                        if retry >= MAX_REVIEW_RETRIES:
                            # Retry limit reached — use actual review result (do NOT force approve)
                            reviewer_approved = False
                            break

                        # Feed review back to coder for retry
                        console.print(f"  [yellow]🔄 Retry {retry+1}/{MAX_REVIEW_RETRIES} — sending feedback to coder[/yellow]")
                        feedback = review.get("summary", "") + "\n"
                        for issue in review.get("issues", []):
                            feedback += f"- [{issue.get('severity')}] {issue.get('title')}: {issue.get('suggestion', '')}\n"

                        task["feedback"] = feedback
                        try:
                            coder_result = run_coders([task], max_active_layer=max_layer)
                        except Exception:
                            break
                        loop_metrics["review_scores"].append(score)
            except Exception as e:
                console.print(f"[red]❌ Reviewer error: {e}[/red]")
                self._emit_agent_end("Reviewer", f"error: {e}")
            else:
                self._emit_agent_end("Reviewer", "approved" if reviewer_approved else "rejected")
        elif all_written_files and self.phase != "initial":
            # Reviewer not scheduled this cycle — auto-approve staged files
            reviewer_approved = True

        # ── Cross-file import consistency check (before promotion) ─────────
        if all_written_files and reviewer_approved:
            try:
                from adelie.utils.import_checker import check_imports, format_import_issues
                from adelie.agents.coder_ai import STAGING_ROOT
                import_issues = check_imports(all_written_files, STAGING_ROOT, PROJECT_ROOT)
                if import_issues:
                    console.print(
                        f"[yellow]⚠️  Import checker found {len(import_issues)} issue(s)[/yellow]"
                    )
                    # Feed back to coder for one fix attempt
                    feedback = format_import_issues(import_issues)
                    if coder_tasks and self.phase != "initial":
                        from adelie.agents.coder_manager import run_coders
                        from adelie.phases import PHASE_INFO
                        phase_info = PHASE_INFO.get(self.phase, {})
                        max_layer = phase_info.get("max_coder_layer", 0)
                        for task in coder_tasks:
                            task["feedback"] = feedback
                        try:
                            fix_start = time.time()
                            run_coders(coder_tasks, max_active_layer=max_layer)
                            new_files = self._collect_staged_files(fix_start)
                            if new_files:
                                all_written_files = new_files
                        except Exception as ie:
                            console.print(f"[dim]⚠️ Import fix error: {ie}[/dim]")
            except Exception as e:
                console.print(f"[dim]⚠️ Import checker error: {e}[/dim]")

        # ── Promote staged files to project (after review) ────────────────
        if all_written_files and reviewer_approved:
            with self._staging_lock:
                self._promote_staged_files(all_written_files)
                self._cleanup_staging()

            # ── Git auto-commit (MID_1+) ──────────────────────────────────────
            if self.phase in ("mid_1", "mid_2", "late", "evolve"):
                try:
                    from adelie.git_ops import auto_commit, is_git_repo
                    if is_git_repo():
                        auto_commit(
                            message=f"adelie: loop #{self.loop_iteration} — {len(all_written_files)} file(s)",
                            files=[f["filepath"] for f in all_written_files],
                        )
                except Exception as e:
                    console.print(f"[dim]⚠️ Git commit error: {e}[/dim]")

        # ══════════════════════════════════════════════════════════════════════
        # PHASE 3: Tester AI + Runner AI (PARALLEL)
        # After code is promoted, testing and building are independent.
        # Note: Tester has a Coder-fix retry loop that stays sequential within
        # Tester's thread, but doesn't block Runner.
        # ══════════════════════════════════════════════════════════════════════
        run_tester = (
            all_written_files
            and self.phase in ("mid_1", "mid_2", "late", "evolve")
            and self.scheduler.should_run("tester", self.loop_iteration)
        )
        run_runner = (
            all_written_files
            and self.phase in ("mid_1", "mid_2", "late", "evolve")
            and self.scheduler.should_run("runner", self.loop_iteration)
        )

        if run_tester or run_runner:
            phase3_start = time.time()
            parallel_names = []
            if run_tester:
                parallel_names.append("Tester")
            if run_runner:
                parallel_names.append("Runner")
            console.print(f"[dim]  ⚡ Phase 3: parallel execution [{', '.join(parallel_names)}][/dim]")

            with ThreadPoolExecutor(max_workers=len(parallel_names), thread_name_prefix="adelie-p3") as pool:
                futures = {}

                if run_tester:
                    _test_pass_results = []
                    _test_metrics = {}
                    _p3_coder_tasks = list(coder_tasks)  # Copy for thread safety
                    _p3_all_files = list(all_written_files)

                    def _run_tester():
                        from adelie.agents.tester_ai import run_tests
                        from adelie.agents.coder_manager import run_coders as _run_coders
                        from adelie.phases import PHASE_INFO
                        set_current_agent("tester")
                        self._emit_agent_start("Tester")
                        MAX_TEST_FIX_RETRIES = 2
                        _phase_info = PHASE_INFO.get(self.phase, {})
                        _max_layer = _phase_info.get("max_coder_layer", 0)
                        _files = _p3_all_files

                        for test_retry in range(MAX_TEST_FIX_RETRIES + 1):
                            test_result = run_tests(source_files=_files, max_test_layer=_max_layer)
                            total = test_result.get("total_tests", 0)
                            passed = test_result.get("passed", 0)
                            failed = test_result.get("failed", 0)

                            if total > 0:
                                _test_pass_results.append(passed == total)
                                _test_metrics["passed"] = passed
                                _test_metrics["total"] = total

                            if failed == 0 or test_retry >= MAX_TEST_FIX_RETRIES:
                                break

                            failure_summary = test_result.get("failure_summary", "Tests failed.")
                            console.print(
                                f"[yellow]🔄 Test fix retry {test_retry + 1}/{MAX_TEST_FIX_RETRIES} — "
                                f"feeding {failed} failure(s) back to coder[/yellow]"
                            )
                            for task in _p3_coder_tasks:
                                task["feedback"] = (
                                    f"## ⚠️ TEST FAILURE FEEDBACK (fix these)\n{failure_summary}\n\n"
                                    f"Fix the code so ALL tests pass. Do NOT change test expectations — fix the source code."
                                )
                            try:
                                fix_start_time = time.time()
                                coder_result = _run_coders(_p3_coder_tasks, max_active_layer=_max_layer)
                                if coder_result.get("total_files", 0) > 0:
                                    new_files = self._collect_staged_files(fix_start_time)
                                    if new_files:
                                        _files = new_files
                                    with self._staging_lock:
                                        self._promote_staged_files(_files)
                                        self._cleanup_staging()
                            except Exception as ce:
                                console.print(f"[red]❌ Coder fix error: {ce}[/red]")
                                break

                        return {"pass_results": _test_pass_results, "metrics": _test_metrics}

                    futures[pool.submit(_run_tester)] = "tester"

                if run_runner:
                    def _run_runner():
                        from adelie.agents.runner_ai import run_pipeline
                        set_current_agent("runner")
                        self._emit_agent_start("Runner")
                        max_tier = "build"
                        if self.phase in ("mid_2", "late", "evolve"):
                            max_tier = "deploy"
                        return run_pipeline(source_files=all_written_files, max_tier=max_tier)
                    futures[pool.submit(_run_runner)] = "runner"

                for future in as_completed(futures, timeout=600):
                    agent_name = futures[future]
                    try:
                        result = future.result()
                        if agent_name == "tester":
                            self.scheduler.mark_ran("tester", self.loop_iteration)
                            if result:
                                self._test_pass_history.extend(result.get("pass_results", []))
                                metrics = result.get("metrics", {})
                                loop_metrics["tests_passed"] = metrics.get("passed", 0)
                                loop_metrics["tests_total"] = metrics.get("total", 0)
                            self._emit_agent_end("Tester", f"{loop_metrics['tests_passed']}/{loop_metrics['tests_total']} passed")
                        elif agent_name == "runner":
                            self.scheduler.mark_ran("runner", self.loop_iteration)
                            if result and result.get("errors"):
                                self._last_build_errors = result["errors"]
                            elif result and result.get("failed", 0) == 0:
                                self._last_build_errors = []  # 성공 시 초기화
                            self._emit_agent_end("Runner", "ok" if not self._last_build_errors else f"{len(self._last_build_errors)} error(s)")
                    except Exception as e:
                        console.print(f"[red]❌ {agent_name.title()} error: {e}[/red]")
                        self._emit_agent_end(agent_name.title(), f"error")

            phase3_elapsed = time.time() - phase3_start
            loop_metrics["parallel_phases"].append({"phase": "3", "agents": parallel_names, "time": round(phase3_elapsed, 1)})

        # ══════════════════════════════════════════════════════════════════════
        # PHASE 3b: Build Error → Coder Fix Retry (SEQUENTIAL)
        # If Runner detected build errors, feed them back to Coder for
        # same-cycle fix — mirrors the Tester AI retry pattern.
        # ══════════════════════════════════════════════════════════════════════
        MAX_BUILD_FIX_RETRIES = 2
        if (
            self._last_build_errors
            and coder_tasks
            and self.phase in ("mid_1", "mid_2", "late", "evolve")
        ):
            from adelie.agents.runner_ai import _diagnose_build_error
            from adelie.agents.coder_manager import run_coders as _build_fix_coders
            from adelie.agents.runner_ai import run_pipeline as _rerun_pipeline
            from adelie.phases import PHASE_INFO as _PHASE_INFO
            _bf_phase_info = _PHASE_INFO.get(self.phase, {})
            _bf_max_layer = _bf_phase_info.get("max_coder_layer", 0)

            for build_retry in range(MAX_BUILD_FIX_RETRIES):
                # Format build errors as coder feedback
                error_lines = ["## ⚠️ BUILD FAILURE — FIX THESE ERRORS\n"]
                for err in self._last_build_errors:
                    error_lines.append(f"### Command: `{err.get('command', '?')}`")
                    error_lines.append(f"Error: {err.get('stderr', '')[:300]}")
                    for diag in err.get("diagnostics", []):
                        if diag.get("file"):
                            error_lines.append(
                                f"  - {diag['file']}:{diag.get('line', '?')} "
                                f"[{diag.get('error_type', '')}] {diag.get('message', '')}"
                            )
                    error_lines.append("")
                error_lines.append("Fix the source code to resolve ALL build errors.")
                error_feedback = "\n".join(error_lines)

                console.print(
                    f"[yellow]🔧 Build fix retry {build_retry + 1}/{MAX_BUILD_FIX_RETRIES} — "
                    f"feeding {len(self._last_build_errors)} error(s) back to coder[/yellow]"
                )

                for task in coder_tasks:
                    task["feedback"] = error_feedback

                try:
                    set_current_agent("coder")
                    fix_start_time = time.time()
                    coder_result = _build_fix_coders(coder_tasks, max_active_layer=_bf_max_layer)
                    if coder_result.get("total_files", 0) > 0:
                        new_files = self._collect_staged_files(fix_start_time)
                        if new_files:
                            all_written_files = new_files
                        self._promote_staged_files(all_written_files)
                        self._cleanup_staging()

                        # Re-run build
                        set_current_agent("runner")
                        max_tier = "build"
                        if self.phase in ("mid_2", "late", "evolve"):
                            max_tier = "deploy"
                        runner_result = _rerun_pipeline(
                            source_files=all_written_files, max_tier=max_tier
                        )
                        if runner_result and runner_result.get("errors"):
                            self._last_build_errors = runner_result["errors"]
                        else:
                            self._last_build_errors = []
                            console.print(
                                f"[green]✅ Build fix succeeded on retry {build_retry + 1}[/green]"
                            )
                            break
                    else:
                        console.print("[dim]  No fix files generated — stopping retry[/dim]")
                        break
                except Exception as bfe:
                    console.print(f"[red]❌ Build fix error: {bfe}[/red]")
                    break

        # ══════════════════════════════════════════════════════════════════════
        # PHASE 4: Monitor AI + Analyst AI (PARALLEL — fully independent)
        # Both only read system state / KB. No data dependency.
        # ══════════════════════════════════════════════════════════════════════
        run_monitor = (
            self.phase in ("mid_2", "late", "evolve")
            and self.scheduler.should_run("monitor", self.loop_iteration)
        )
        run_analyst = (
            self.phase in ("mid_2", "late", "evolve")
            and self.scheduler.should_run("analyst", self.loop_iteration)
        )

        health_result = None  # Track for Monitor→Runner critical restart

        if run_monitor or run_analyst:
            phase4_start = time.time()
            parallel_names = []
            if run_monitor:
                parallel_names.append("Monitor")
            if run_analyst:
                parallel_names.append("Analyst")
            console.print(f"[dim]  ⚡ Phase 4: parallel execution [{', '.join(parallel_names)}][/dim]")

            with ThreadPoolExecutor(max_workers=len(parallel_names), thread_name_prefix="adelie-p4") as pool:
                futures = {}

                if run_monitor:
                    def _run_monitor():
                        from adelie.agents.monitor_ai import run_health_check
                        set_current_agent("monitor")
                        self._emit_agent_start("Monitor")
                        return run_health_check()
                    futures[pool.submit(_run_monitor)] = "monitor"

                if run_analyst:
                    def _run_analyst():
                        from adelie.agents.analyst_ai import run_analysis
                        set_current_agent("analyst")
                        self._emit_agent_start("Analyst")
                        return run_analysis(analysis_type="full")
                    futures[pool.submit(_run_analyst)] = "analyst"

                for future in as_completed(futures, timeout=180):
                    agent_name = futures[future]
                    try:
                        result = future.result()
                        if agent_name == "monitor":
                            self.scheduler.mark_ran("monitor", self.loop_iteration)
                            health_result = result
                            overall = result.get("overall", "ok") if result else "ok"
                            self._emit_agent_end("Monitor", overall)
                        elif agent_name == "analyst":
                            self.scheduler.mark_ran("analyst", self.loop_iteration)
                            self._emit_agent_end("Analyst", "done")
                    except Exception as e:
                        console.print(f"[red]❌ {agent_name.title()} error: {e}[/red]")
                        self._emit_agent_end(agent_name.title(), f"error")

            phase4_elapsed = time.time() - phase4_start
            loop_metrics["parallel_phases"].append({"phase": "4", "agents": parallel_names, "time": round(phase4_elapsed, 1)})

        # ── Monitor critical → Runner restart (sequential, post-parallel) ─────
        if health_result and health_result.get("overall") == "critical" and health_result.get("processes_dead", 0) > 0:
            console.print("[yellow]⚠️  Monitor critical — Runner will restart services[/yellow]")
            try:
                from adelie.agents.runner_ai import run_pipeline
                run_pipeline(source_files=all_written_files or [], max_tier="run")
            except Exception:
                pass

        old_state = self.state

        if action == "EXPORT" and export_data:
            self._write_export(export_data)
            self.state = LoopState(next_situation) if next_situation in LoopState._value2member_map_ else LoopState.NORMAL

        elif action == "PAUSE":
            self._write_maintenance_note()
            self.state = LoopState.MAINTENANCE
            console.print("[yellow]⏸️  Entering maintenance — loop will pause for one interval.[/yellow]")

        elif action == "SHUTDOWN":
            console.print("[bold red]🔴 Expert AI requested shutdown.[/bold red]")
            self._running = False

        elif action == "RECOVER":
            self._recover_count += 1
            if self._recover_count >= self.MAX_RECOVER_RETRIES:
                console.print(f"[yellow]⚠️  Max recovery retries ({self.MAX_RECOVER_RETRIES}) reached — entering maintenance.[/yellow]")
                self._archive_errors()
                self.state = LoopState.MAINTENANCE
            else:
                console.print(f"[yellow]🔄 Recovery attempt {self._recover_count}/{self.MAX_RECOVER_RETRIES} — clearing errors and returning to normal.[/yellow]")
                self._archive_errors()
                self.state = LoopState.NORMAL
                self.hooks.emit(HookEvent.ON_RECOVERY, {
                    "iteration": self.loop_iteration,
                    "attempt": self._recover_count,
                })

        else:
            # CONTINUE or NEW_LOGIC — follow Expert AI's suggested next situation
            self._recover_count = 0  # Reset on successful non-RECOVER action

            # Track new_logic cycles to prevent infinite bootstrapping
            if next_situation == "new_logic":
                self._new_logic_count += 1
                if self._new_logic_count >= self.MAX_NEW_LOGIC_CYCLES:
                    console.print(
                        f"[yellow]⚠️  Max new_logic cycles ({self.MAX_NEW_LOGIC_CYCLES}) reached — "
                        f"transitioning to normal.[/yellow]"
                    )
                    self.state = LoopState.NORMAL
                    self._new_logic_count = 0
                    return
            else:
                self._new_logic_count = 0

            try:
                self.state = LoopState(next_situation)
            except ValueError:
                self.state = LoopState.NORMAL

        # Emit state change hook if state actually changed
        if self.state != old_state:
            self.hooks.emit(HookEvent.STATE_CHANGE, {
                "iteration": self.loop_iteration,
                "old_state": old_state.value,
                "new_state": self.state.value,
            })

        # ── Display token usage + loop metrics ──────────────────────────────────
        cycle_elapsed = time.time() - cycle_start_time
        loop_metrics["cycle_time"] = round(cycle_elapsed, 1)
        usage = get_usage()
        if usage["calls"] > 0:
            parts = [
                f"{usage['total_tokens']:,} tok",
                f"(↑{usage['prompt_tokens']:,} ↓{usage['completion_tokens']:,})",
                f"{usage['calls']} calls",
                f"⏱️{cycle_elapsed:.1f}s",
            ]
            if loop_metrics["files_written"]:
                parts.append(f"📄{loop_metrics['files_written']} files")
            if loop_metrics["review_scores"]:
                avg = sum(loop_metrics['review_scores']) / len(loop_metrics['review_scores'])
                parts.append(f"⭐{avg:.0f}/10")
            if loop_metrics["tests_total"]:
                parts.append(f"🧪{loop_metrics['tests_passed']}/{loop_metrics['tests_total']}")
            loop_stats = self._loop_detector.get_stats()
            if loop_stats.get("interventions_given", 0) > 0:
                parts.append(f"🔄{loop_stats['interventions_given']} interventions")
            # Show parallel execution info
            for pp in loop_metrics.get("parallel_phases", []):
                parts.append(f"⚡P{pp['phase']}:{pp['time']}s")
            console.print(f"[dim]📊 Loop #{self.loop_iteration}: {' | '.join(parts)}[/dim]")

        # ── Record persistent metrics ─────────────────────────────────────────
        try:
            from adelie.metrics import record_cycle as _record_cycle
            agent_usage = get_agent_usage()
            _record_cycle(
                iteration=self.loop_iteration,
                phase=self.phase,
                state=self.state.value,
                cycle_time=cycle_elapsed,
                agent_metrics=agent_usage,
                token_usage=usage,
                loop_metrics=loop_metrics,
            )
        except Exception as e:
            console.print(f"[dim]⚠️ Metrics recording error: {e}[/dim]")

        # Check spawned processes
        self.supervisor.check_all()

        # ── Context Engine after-cycle hook ────────────────────────────────────
        # Inspired by openclaw's afterTurn() — track token utilization and
        # recommend compaction when contexts persistently exceed budget.
        try:
            cycle_result = after_cycle(
                assembled_contexts=self._last_assembled_contexts,
                cycle_history=self._cycle_history,
            )
            if cycle_result.get("needs_compaction"):
                console.print("[yellow]📦 Triggering cycle history compaction…[/yellow]")
                # Force the cycle history to compress more aggressively
                if self._cycle_history._recent:
                    oldest = self._cycle_history._recent[0]
                    self._cycle_history._compress_oldest(oldest)
        except Exception as e:
            console.print(f"[dim]  ⚠️ after_cycle hook error: {e}[/dim]")

        # Emit after-cycle hook
        self.hooks.emit(HookEvent.AFTER_CYCLE, {
            "iteration": self.loop_iteration,
            "state": self.state.value,
        })

        # Persist state for resume after Ctrl+C
        self._save_state()

    def pause(self) -> None:
        """Request the orchestrator to pause before the next cycle."""
        self._pause_requested = True

    def resume(self) -> None:
        """Resume the orchestrator from a paused state."""
        self._pause_requested = False

    def _wait_if_paused(self) -> None:
        """Block the thread if a pause is requested, until resumed."""
        if self._pause_requested:
            console.print("[yellow]⏸️  Orchestrator is paused. Waiting for /resume...[/yellow]")
        while self._pause_requested and self._running:
            time.sleep(0.5)

    # ── Loop Modes ────────────────────────────────────────────────────────────

    def run_once(self) -> dict | None:
        """Run exactly one cycle and return the Expert AI decision."""
        console.print(Panel.fit(
            f"[bold cyan]Adelie — Single Run[/bold cyan]\nGoal: {self.goal}",
            border_style="cyan",
        ))
        self._start_mcp()
        self.run_cycle()
        self._stop_mcp()
        return self.last_expert_output

    def run_loop(self) -> None:
        """Run continuously until shutdown signal or SHUTDOWN action."""
        console.print(Panel.fit(
            f"[bold green]Adelie — Continuous Loop[/bold green]\n"
            f"Goal: {self.goal}\n"
            f"Interval: {LOOP_INTERVAL_SECONDS}s  •  Press Ctrl+C to stop",
            border_style="green",
        ))
        self._start_mcp()

        while self._running:
            try:
                self.run_cycle()
            except Exception as e:
                console.print(f"[red bold]💥 Unhandled error in loop: {e}[/red bold]")
                self._write_error_to_kb(e)
                self.last_error = str(e)
                self.state = LoopState.ERROR

            if not self._running:
                break

            if self.state == LoopState.MAINTENANCE:
                interval = self.scheduler.get_loop_interval(LOOP_INTERVAL_SECONDS, "maintenance")
                console.print(f"[yellow]⏸️  Maintenance pause — sleeping {interval}s…[/yellow]")
                time.sleep(interval)
                self.state = LoopState.NORMAL
            else:
                interval = self.scheduler.get_loop_interval(LOOP_INTERVAL_SECONDS, self.state.value)
                console.print(f"[dim]💤 Sleeping {interval}s before next cycle…[/dim]")
                time.sleep(interval)

        self._stop_mcp()
        console.print("[bold]✅ Adelie loop stopped cleanly.[/bold]")

    # ── MCP Helpers ──────────────────────────────────────────────────────────

    def _start_mcp(self) -> None:
        """Connect to configured MCP servers and register tools."""
        if not MCP_ENABLED:
            return
        try:
            from adelie.mcp_manager import McpManager
            from adelie.tool_registry import get_registry

            self._mcp_manager = McpManager()
            self._mcp_manager.load_config()

            if not self._mcp_manager.has_servers:
                return

            results = self._mcp_manager.start_all()
            connected = sum(1 for v in results.values() if v)

            if connected > 0:
                registry = get_registry()
                count = registry.register_mcp_tools(self._mcp_manager)
                console.print(
                    f"[bold cyan]🔌 MCP: {connected} server(s) connected, "
                    f"{count} tool(s) registered[/bold cyan]"
                )
            else:
                console.print("[dim]🔌 MCP: no servers connected[/dim]")

        except Exception as e:
            console.print(f"[yellow]⚠️ MCP startup error (non-fatal): {e}[/yellow]")

    def _stop_mcp(self) -> None:
        """Disconnect all MCP servers and remove tools."""
        if self._mcp_manager:
            try:
                from adelie.tool_registry import get_registry
                registry = get_registry()
                registry.remove_mcp_tools()
                self._mcp_manager.stop_all()
            except Exception as e:
                console.print(f"[dim]⚠️ MCP cleanup error: {e}[/dim]")
            self._mcp_manager = None
