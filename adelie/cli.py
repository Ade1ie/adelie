"""
adelie/cli.py  —  Thin entry-point

Only contains:
  - main()  — argparse definition + routing to adelie.commands.*
  - _dispatch_run()  — forwarded from commands.run

All cmd_* handlers live in adelie/commands/*.
All shared helpers live in adelie/commands/_helpers.py.
"""

from __future__ import annotations

import argparse
import sys

from rich.console import Console
from rich.columns import Columns
from rich.padding import Padding
from rich.text import Text

from adelie import __version__

# ── Command imports ───────────────────────────────────────────────────────────
from adelie.commands.workspace import cmd_init, cmd_ws
from adelie.commands.run import cmd_run, _dispatch_run
from adelie.commands.config import cmd_config, cmd_settings
from adelie.commands.monitoring import cmd_status, cmd_phase, cmd_inform, cmd_metrics
from adelie.commands.knowledge import cmd_kb, cmd_feedback, cmd_goal, cmd_research, cmd_spec, cmd_scan
from adelie.commands.integrations import (
    cmd_help,
    cmd_ollama,
    cmd_telegram,
    cmd_git,
    cmd_commands,
    cmd_tools,
    cmd_prompts,
)

# ── Backward-compat re-exports (for tests that import directly from cli) ──────
from adelie.commands._helpers import (  # noqa: F401
    _find_workspace_root,
    _workspace_config_path,
    _load_workspace_config,
    _save_workspace_config,
    _update_env_file,
    _setup_env_from_workspace,
    _ensure_adelie_config,
    _validate_provider,
    _detect_os,
    _generate_os_context,
    _auto_generate_goal,
)


console = Console()


# ── Penguin splash ────────────────────────────────────────────────────────────
_PENGUIN = (
    "\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u28e1\u28e1\u28b6\u28ff\u28f7\u28ff\u28ff\u28ff\u28f7\u28f7\u28b6\u28a4\u2801\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\n"
    "\u2800\u2800\u2800\u2800\u2800\u28a4\u28fe\u28ff\u28bf\u28fb\u281d\u28de\u28f3\u281d\u2852\u2809\u2809\u2819\u281b\u28bf\u28b6\u2801\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\n"
    "\u2800\u2800\u2800\u2800\u28bc\u28ff\u28ff\u28fb\u28df\u28e7\u28bf\u28fb\u28bf\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u28fb\u28ff\u28e7\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\n"
    "\u2800\u2800\u2801\u28fe\u28ff\u281f\u281e\u281b\u281a\u280b\u28df\u281f\u28ff\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2818\u28bf\u28e7\u2800\u2800\u2800\u2800\u2800\u2800\u2800\n"
    "\u2800\u2800\u28bc\u28ff\u281f\u2800\u2800\u2800\u2800\u2800\u2808\u28fb\u281d\u2806\u2800\u2800\u28f4\u28f7\u2804\u2800\u2800\u2800\u2818\u28ff\u2806\u2800\u2800\u2801\u28a0\u28a4\u2804\n"
    "\u2800\u2800\u28ff\u28ff\u2801\u2800\u2800\u2800\u2800\u2800\u2800\u2808\u28ff\u28bf\u28f7\u2800\u2818\u281b\u2803\u2800\u2820\u2800\u2800\u28ff\u2805\u28f4\u281f\u281b\u280b\u28f9\u28ff\n"
    "\u2800\u2800\u28fb\u28ff\u2800\u2800\u2800\u2800\u28fe\u28ff\u2806\u2800\u28bf\u28f4\u28f4\u2807\u2800\u2800\u2800\u2800\u2800\u2800\u2801\u281f\u280b\u2801\u2800\u2800\u2800\u28f8\u28ff\n"
    "\u2800\u2800\u2808\u28bf\u2807\u2800\u2800\u2800\u2808\u2809\u2825\u2800\u2800\u2809\u2809\u2800\u2800\u2800\u2800\u2800\u2800\u2801\u281f\u2801\u2800\u2800\u2800\u2800\u2800\u28fe\u281f\n"
    "\u2800\u2800\u2800\u2808\u28bf\u28e6\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2801\u2838\u2801\u2800\u2800\u2800\u2800\u2800\u28bc\u281f\u2800\n"
    "\u2800\u2800\u2800\u2800\u2800\u28f9\u28ff\u28b6\u28a4\u2801\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2802\u2801\u2800\u2810\u28c7\u2800\u2800\u28fe\u281f\u2800\u2800\u2800\n"
    "\u2800\u2800\u2801\u28a0\u28fe\u281f\u2809\u2800\u2800\u2809\u2809\u2800\u2810\u2802\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2808\u28bf\u28b6\u281f\u280b\u2800\u2800\u2800\n"
    "\u28a0\u28b6\u281f\u280b\u2801\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2808\u28ff\u2806\u2800\u2800\u2800\u2800\n"
    "\u28fb\u28e7\u2801\u2800\u2800\u2800\u28f0\u2807\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u28f8\u28ff\u2800\u2800\u2800\u2800\n"
    "\u2800\u2809\u281b\u281f\u28f7\u28b6\u28fe\u2807\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u28f8\u28ff\u2800\u2800\u2800\u2800\n"
    "\u2800\u2800\u2800\u2800\u2800\u2800\u28ff\u2807\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u28a4\u28a4\u28fe\u28ff\u2800\u2800\u2800\u2800\n"
    "\u2800\u2800\u2800\u2800\u2800\u2800\u28f9\u28ff\u28ff\u28ff\u28ff\u28f7\u28a6\u2800\u2800\u28bf\u2801\u2800\u2800\u2800\u28a0\u28b4\u28ff\u28ff\u28ff\u28ff\u28f7\u2800\u2800\u2800\u2800\n"
    "\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u28fb\u28bf\u28ff\u28ff\u28ff\u28ff\u281f\u281f\u281f\u281f\u281f\u281f\u281f\u281f\u28ff\u28ff\u28ff\u281f\u281b\u2801\u2800\u2800\u2800\u2800\n"
)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="adelie",
        description="Adelie — Self-Communicating Autonomous AI Loop",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Run [adelie help] for detailed command reference.",
    )
    parser.add_argument("-v", "--version", action="version",
                        version=f"adelie {__version__}")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ── help ──────────────────────────────────────────────────────────────────
    p_help = subparsers.add_parser("help", help="Show detailed command reference")
    p_help.set_defaults(func=cmd_help)

    # ── init ──────────────────────────────────────────────────────────────────
    p_init = subparsers.add_parser("init", help="Initialize a new workspace")
    p_init.add_argument("directory", nargs="?", default=".",
                        help="Target directory (default: current)")
    p_init.add_argument("--force", action="store_true",
                        help="Reinitialize existing workspace")
    p_init.set_defaults(func=cmd_init)

    # ── ws ────────────────────────────────────────────────────────────────────
    p_ws = subparsers.add_parser("ws", help="List / manage workspaces")
    p_ws.add_argument("ws_action", nargs="?", default="list",
                      choices=["list", "remove"],
                      help="Action (default: list)")
    p_ws.add_argument("number", nargs="?", type=int, default=None,
                      help="Workspace number (for remove)")
    p_ws.set_defaults(func=cmd_ws)

    # ── scan ──────────────────────────────────────────────────────────────────
    p_scan = subparsers.add_parser("scan", help="Scan existing codebase and generate KB docs")
    p_scan.add_argument("--directory", type=str, default=".",
                        help="Project directory to scan (default: current)")
    p_scan.set_defaults(func=cmd_scan)

    # ── spec ──────────────────────────────────────────────────────────────────
    p_spec = subparsers.add_parser("spec", help="Load spec files (MD, PDF, DOCX) into KB")
    p_spec.add_argument("spec_action", nargs="?", default="list",
                        choices=["load", "list", "remove"],
                        help="load / list (default) / remove")
    p_spec.add_argument("file_path", nargs="?", default=None,
                        help="File path (for load) or spec name (for remove)")
    p_spec.add_argument("--category", type=str, default="logic",
                        choices=["dependencies", "skills", "logic", "errors", "maintenance"],
                        help="KB category (default: logic)")
    p_spec.set_defaults(func=cmd_spec, spec_name=None)

    # ── run ───────────────────────────────────────────────────────────────────
    p_run = subparsers.add_parser("run", help="Run the AI loop")
    p_run.add_argument("ws_keyword", nargs="?", default=None,
                       help="Use 'ws' followed by a number to resume a workspace")
    p_run.add_argument("workspace_num", nargs="?", type=int, default=None,
                       help="Workspace number (use with 'ws')")
    p_run.add_argument("--goal", type=str, default=None,
                       help="High-level goal for the AI agents")
    p_run.add_argument("--once", action="store_true",
                       help="Run exactly one cycle then exit")
    p_run.set_defaults(func=_dispatch_run)

    # ── status ────────────────────────────────────────────────────────────────
    p_status = subparsers.add_parser("status", help="Show system status & health")
    p_status.set_defaults(func=cmd_status)

    # ── inform ────────────────────────────────────────────────────────────────
    p_inform = subparsers.add_parser("inform", help="Generate project status report (Inform AI)")
    p_inform.add_argument("--goal", type=str, default="",
                          help="Project goal context for the report")
    p_inform.set_defaults(func=cmd_inform)

    # ── config ────────────────────────────────────────────────────────────────
    p_config = subparsers.add_parser("config", help="View or update configuration")
    p_config.add_argument("--provider", type=str, help="'gemini' or 'ollama'")
    p_config.add_argument("--model", type=str, help="Model name")
    p_config.add_argument("--interval", type=int, help="Loop interval (seconds)")
    p_config.add_argument("--ollama-url", type=str, help="Ollama server URL")
    p_config.add_argument("--api-key", type=str, help="Gemini API key")
    p_config.add_argument("--lang", type=str, help="Display language: 'ko' or 'en'")
    p_config.add_argument("--sandbox", type=str, help="Sandbox mode: 'none', 'seatbelt', or 'docker'")
    p_config.add_argument("--plan-mode", type=str, dest="plan_mode",
                          help="Plan mode: 'true' or 'false'")
    p_config.set_defaults(func=cmd_config)

    # ── settings ──────────────────────────────────────────────────────────────
    p_settings = subparsers.add_parser("settings", help="Manage runtime settings (global & workspace)")
    p_settings.add_argument("settings_action", nargs="?", default="show",
                            choices=["show", "set", "reset"],
                            help="show (default) / set / reset")
    p_settings.add_argument("settings_key", nargs="?", default=None,
                            help="Setting key (e.g. dashboard, loop.interval)")
    p_settings.add_argument("settings_value", nargs="?", default=None,
                            help="New value (for set)")
    p_settings.add_argument("--global", action="store_true", dest="use_global",
                            help="Target global settings (~/.adelie/settings.json)")
    p_settings.set_defaults(func=cmd_settings)

    # ── kb ────────────────────────────────────────────────────────────────────
    p_kb = subparsers.add_parser("kb", help="Knowledge Base management")
    p_kb.add_argument("--clear-errors", action="store_true", help="Clear error files")
    p_kb.add_argument("--reset", action="store_true", help="Reset entire KB")
    p_kb.set_defaults(func=cmd_kb)

    # ── ollama ────────────────────────────────────────────────────────────────
    p_ollama = subparsers.add_parser("ollama", help="Ollama model management")
    p_ollama.add_argument("ollama_action", choices=["list", "pull", "remove", "run"],
                          help="list / pull / remove / run")
    p_ollama.add_argument("model_name", nargs="?", default=None, help="Model name")
    p_ollama.set_defaults(func=cmd_ollama)

    # ── telegram ──────────────────────────────────────────────────────────────
    p_tg = subparsers.add_parser("telegram", help="Telegram bot integration")
    p_tg.add_argument("telegram_action", choices=["setup", "start"],
                      help="setup (register token) / start (run bot)")
    p_tg.add_argument("--ws", type=int, dest="ws_num", default=None,
                      help="Workspace number to bind the bot to")
    p_tg.add_argument("--token", type=str, default=None,
                      help="Bot token (overrides saved one)")
    p_tg.set_defaults(func=cmd_telegram)

    # ── phase ─────────────────────────────────────────────────────────────────
    p_phase = subparsers.add_parser("phase", help="Project lifecycle phase management")
    p_phase.add_argument("phase_action", nargs="?", default="show",
                         choices=["show", "set"],
                         help="show (default) or set")
    p_phase.add_argument("phase_value", nargs="?", default=None,
                         help="Phase to set: initial, mid, mid_1, mid_2, late, evolve")
    p_phase.set_defaults(func=cmd_phase)

    # ── feedback ──────────────────────────────────────────────────────────────
    p_fb = subparsers.add_parser("feedback", help="Send user feedback to the AI loop")
    p_fb.add_argument("message", nargs="?", default=None, help="Feedback message")
    p_fb.add_argument("--priority", type=str, default="normal",
                      choices=["low", "normal", "high", "critical"],
                      help="Feedback priority (default: normal)")
    p_fb.add_argument("--list", action="store_true", dest="list_pending",
                      help="List pending feedback")
    p_fb.set_defaults(func=cmd_feedback)

    # ── goal ──────────────────────────────────────────────────────────────────
    p_goal = subparsers.add_parser("goal", help="Manage project goal")
    p_goal.add_argument("goal_action", nargs="?", default="show",
                        choices=["show", "set"],
                        help="show (default) or set")
    p_goal.add_argument("goal_text", nargs="?", default=None,
                        help="Goal text (for set)")
    p_goal.set_defaults(func=cmd_goal)

    # ── git ───────────────────────────────────────────────────────────────────
    p_git = subparsers.add_parser("git", help="Git status and recent commits")
    p_git.set_defaults(func=cmd_git)

    # ── research ──────────────────────────────────────────────────────────────
    p_res = subparsers.add_parser("research", help="Web research via Gemini Search")
    p_res.add_argument("topic", nargs="?", default=None,
                       help="Research topic / search query")
    p_res.add_argument("--context", type=str, default=None,
                       help="Why this research is needed")
    p_res.add_argument("--category", type=str, default="dependencies",
                       choices=["dependencies", "skills", "logic", "errors", "maintenance"],
                       help="KB category to store results (default: dependencies)")
    p_res.add_argument("--list", action="store_true", dest="list_results",
                       help="List recent research results")
    p_res.set_defaults(func=cmd_research)

    # ── metrics ───────────────────────────────────────────────────────────────
    p_metrics = subparsers.add_parser("metrics", help="View cycle performance metrics")
    p_metrics.add_argument("--agents", action="store_true",
                           help="Show per-agent token usage")
    p_metrics.add_argument("--trend", action="store_true",
                           help="Show performance trends")
    p_metrics.add_argument("--last", type=int, default=None,
                           help="Number of recent cycles to show (default: 20)")
    p_metrics.add_argument("--since", type=str, default=None,
                           help="Time filter (e.g. 1h, 6h, 24h, 7d)")
    p_metrics.set_defaults(func=cmd_metrics)

    # ── prompts ───────────────────────────────────────────────────────────────
    p_prompts = subparsers.add_parser("prompts", help="Manage agent system prompts")
    p_prompts.add_argument("action", nargs="?", default="list",
                           choices=["list", "export", "reset"],
                           help="list / export / reset")
    p_prompts.set_defaults(func=cmd_prompts)

    # ── commands ──────────────────────────────────────────────────────────────
    p_commands = subparsers.add_parser("commands", help="List custom commands from .adelie/commands/")
    p_commands.set_defaults(func=cmd_commands)

    # ── tools ─────────────────────────────────────────────────────────────────
    p_tools = subparsers.add_parser("tools", help="Manage tool registry")
    p_tools.add_argument("tools_action", nargs="?", default="list",
                         choices=["list", "enable", "disable"],
                         help="list (default) / enable / disable")
    p_tools.add_argument("tool_name", nargs="?", default=None,
                         help="Tool name (for enable/disable)")
    p_tools.set_defaults(func=cmd_tools)

    # ── Splash screen (no command) ────────────────────────────────────────────
    args = parser.parse_args()

    if not args.command:
        art = Text(_PENGUIN, no_wrap=True)
        info = (
            f"\n\n\n"
            f"  [bold cyan]Adelie[/bold cyan] [dim]v{__version__}[/dim]\n"
            f"  [dim]──────────────────[/dim]\n"
            f"  Autonomous AI Loop\n\n"
            f"  [dim]adelie <command> --help[/dim]\n"
        )
        console.print(Columns([Padding(art, (0, 1)), info]))
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()
