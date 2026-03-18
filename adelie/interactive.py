"""
adelie/interactive.py

Gemini CLI-inspired interactive REPL for the Adelie orchestrator.

NO alternate screen buffer — output flows naturally in the terminal.
Text is scrollable and copyable like a normal CLI tool.

Layout:
  1. ASCII header printed once at startup
  2. Orchestrator events print inline as they happen (Rich markup)
  3. Simple threaded input loop with '>' prompt for commands
"""

from __future__ import annotations

try:
    import readline  # noqa: F401 — enables arrow-key editing in input()
except ImportError:
    try:
        import pyreadline3  # noqa: F401 — Windows alternative
    except ImportError:
        pass  # arrow-key editing won't work, but no crash
import shutil
import signal
import sys
import threading
import time
from typing import Optional

from rich.console import Console
from rich.text import Text

from adelie.orchestrator import Orchestrator
from adelie.ui_logger import (
    UILogger, LogCategory, AgentState, AgentInfo,
    CycleMetrics, TRACKED_AGENTS,
)
from adelie.command_loader import get_command, load_commands

console = Console()

# ── Agent color map ───────────────────────────────────────────────────────────

AGENT_COLORS = {
    "Writer":   "blue",
    "Expert":   "cyan",
    "Scanner":  "magenta",
    "Coder:0":  "green",
    "Coder:1":  "green",
    "Coder:2":  "green",
    "Reviewer": "yellow",
    "Tester":   "red",
    "Runner":   "bright_green",
    "Monitor":  "bright_cyan",
    "Analyst":  "bright_magenta",
    "Inform":   "bright_blue",
    "Research": "bright_yellow",
}


# ── Header ────────────────────────────────────────────────────────────────────

def print_header(goal: str, phase: str, model: str, workspace: str):
    """Print the startup header — gemini-cli style ASCII icon + info."""
    width = shutil.get_terminal_size((80, 24)).columns

    console.print()
    console.print("  [cyan]▝▜▄[/cyan]    [bold]Adelie[/bold] [dim]v0.1.0[/dim]")
    console.print(f"    [cyan]▝▜▄[/cyan]  [dim]{model}[/dim]")
    console.print(f"   [cyan]▗▟▀[/cyan]  [dim]Phase:[/dim] {phase}")
    console.print(f"  [cyan]▝▀[/cyan]")
    console.print()

    # Goal
    if goal:
        goal_max = width - 4
        goal_display = (goal[:goal_max] + "…") if len(goal) > goal_max else goal
        console.print(f"  [dim]Goal:[/dim] {goal_display}")

    # Workspace
    if workspace:
        ws_display = workspace
        if ws_display.startswith("/Users/"):
            parts = ws_display.split("/")
            if len(parts) > 3:
                ws_display = "~/" + "/".join(parts[3:])
        console.print(f"  [dim]Workspace:[/dim] {ws_display}")

    console.print(f"  [dim]{'─' * (width - 4)}[/dim]")
    console.print()


# ── Footer / Status line ─────────────────────────────────────────────────────

def print_cycle_header(iteration: int, phase: str, state: str):
    """Print a cycle separator."""
    width = shutil.get_terminal_size((80, 24)).columns
    console.print()
    console.print(f"  [dim]{'─' * (width - 4)}[/dim]")
    console.print(f"  [bold cyan]Cycle #{iteration}[/bold cyan] [dim]| {phase} | {state}[/dim]")
    console.print()


def print_cycle_metrics(metrics: CycleMetrics):
    """Print compact cycle metrics inline."""
    parts = []
    if metrics.total_tokens > 0:
        parts.append(f"{metrics.total_tokens:,} tok")
    if metrics.llm_calls > 0:
        parts.append(f"{metrics.llm_calls} calls")
    if metrics.cycle_time > 0:
        parts.append(f"{metrics.cycle_time:.1f}s")
    if metrics.files_written > 0:
        parts.append(f"{metrics.files_written} files")
    if metrics.tests_total > 0:
        parts.append(f"test {metrics.tests_passed}/{metrics.tests_total}")
    if metrics.review_score > 0:
        parts.append(f"{metrics.review_score:.0f}/10")

    if parts:
        console.print(f"  [dim]{' · '.join(parts)}[/dim]")


def print_agent_event(name: str, info: AgentInfo):
    """Print an agent state change inline."""
    color = AGENT_COLORS.get(name, "white")
    if info.state == AgentState.RUNNING:
        console.print(f"  [{color}]{name}[/{color}] [dim]running…[/dim]")
    elif info.state == AgentState.DONE:
        elapsed = f" ({info.elapsed:.1f}s)" if info.elapsed > 0 else ""
        detail = f" — {info.detail}" if info.detail else ""
        console.print(f"  [{color}]{name}[/{color}] done{elapsed}{detail}")
    elif info.state == AgentState.ERROR:
        console.print(f"  [red]{name}[/red] [bold red]error[/bold red]: {info.detail}")
    elif info.state == AgentState.SKIPPED:
        console.print(f"  [dim]{name} skipped[/dim]")


# ── Help text ─────────────────────────────────────────────────────────────────

HELP_TEXT = """\
[bold]Commands:[/bold]
  [cyan]/help[/cyan]                 Show this help
  [cyan]/status[/cyan]               Show orchestrator status
  [cyan]/pause[/cyan]                Pause before next cycle
  [cyan]/resume[/cyan]               Resume from pause
  [cyan]/feedback <msg>[/cyan]       Send feedback to AI
  [cyan]/commands[/cyan]             List custom commands
  [cyan]/plan[/cyan]                 Show pending plan (Plan Mode)
  [cyan]/approve[/cyan]              Approve pending plan
  [cyan]/reject [reason][/cyan]      Reject pending plan
  [cyan]/exit[/cyan], [cyan]/quit[/cyan]         Stop and exit\
"""


# ── Main REPL ─────────────────────────────────────────────────────────────────

class AdelieApp:
    """
    Non-TUI interactive REPL for the Adelie orchestrator.

    Output flows naturally in the terminal — scrollable and copyable.
    The orchestrator runs in a background thread while the main thread
    reads commands via input().
    """

    def __init__(self, orchestrator: Orchestrator):
        self.orchestrator = orchestrator
        self._ui_logger: Optional[UILogger] = None
        self._running = True
        self._orch_thread: Optional[threading.Thread] = None

    def run(self):
        """Start the orchestrator and enter the command loop."""
        import adelie.config as cfg

        # Determine model string
        if cfg.LLM_PROVIDER == "gemini":
            model_str = f"gemini · {cfg.GEMINI_MODEL}"
        else:
            model_str = f"ollama · {cfg.OLLAMA_MODEL}"

        # Print header
        print_header(
            goal=self.orchestrator.goal,
            phase=self.orchestrator.phase,
            model=model_str,
            workspace=str(cfg.PROJECT_ROOT),
        )

        # Setup UILogger
        self._setup_logger()

        # Patch consoles
        self._patch_consoles()

        # Wire orchestrator callbacks
        self._wire_orchestrator()

        console.print("[dim]Type '/help' for a list of commands.[/dim]")
        console.print()

        # Start orchestrator in background
        self._orch_thread = threading.Thread(
            target=self._run_orchestrator, daemon=True
        )
        self._orch_thread.start()

        # Handle Ctrl+C gracefully
        original_sigint = signal.getsignal(signal.SIGINT)

        def _sigint_handler(signum, frame):
            console.print("\n[yellow]Shutting down…[/yellow]")
            self._shutdown()

        signal.signal(signal.SIGINT, _sigint_handler)

        # Command input loop
        try:
            while self._running:
                try:
                    text = input("> ").strip()
                except EOFError:
                    break

                if not text:
                    continue

                if text.startswith("/"):
                    self._handle_command(text)
                else:
                    # Treat bare text as feedback
                    self._handle_command(f"/feedback {text}")
        except KeyboardInterrupt:
            pass
        finally:
            signal.signal(signal.SIGINT, original_sigint)
            self._shutdown()

    def _setup_logger(self):
        """Create UILogger and wire callbacks."""
        self._ui_logger = UILogger()

        self._ui_logger.on_agent_update = lambda name, info: print_agent_event(name, info)
        self._ui_logger.on_log = lambda category, obj: console.print(obj)
        self._ui_logger.on_cycle_start = lambda it, ph, st: print_cycle_header(it, ph, st)
        self._ui_logger.on_cycle_metrics = lambda m: print_cycle_metrics(m)

    def _wire_orchestrator(self):
        """Wire orchestrator event callbacks."""
        def _on_agent_start(agent_name: str):
            self._ui_logger.set_agent_state(agent_name, AgentState.RUNNING)

        def _on_agent_end(agent_name: str, detail: str):
            state = AgentState.ERROR if "error" in detail.lower() else AgentState.DONE
            self._ui_logger.set_agent_state(agent_name, state, detail)

        def _on_cycle_start(iteration: int, phase: str, state: str):
            print_cycle_header(iteration, phase, state)
            self._ui_logger.reset_agents()

        self.orchestrator.set_ui_callbacks(
            on_agent_start=_on_agent_start,
            on_agent_end=_on_agent_end,
            on_cycle_start=_on_cycle_start,
        )

    def _patch_consoles(self):
        """Replace console objects in all Adelie modules with UILogger."""
        import adelie.orchestrator as orch_module
        import adelie.agents.writer_ai as writer_module
        import adelie.agents.expert_ai as expert_module
        import adelie.agents.coder_ai as coder_module
        import adelie.agents.coder_manager as coder_manager_module
        import adelie.agents.runner_ai as runner_module
        import adelie.agents.monitor_ai as monitor_module
        import adelie.agents.analyst_ai as analyst_module
        import adelie.interactive as interactive_module

        modules = [
            orch_module, writer_module, expert_module,
            coder_module, coder_manager_module,
            runner_module, monitor_module, analyst_module,
            interactive_module,
        ]

        for mod_name in (
            "adelie.agents.research_ai",
            "adelie.agents.tester_ai",
            "adelie.agents.reviewer_ai",
        ):
            try:
                import importlib
                mod = importlib.import_module(mod_name)
                modules.append(mod)
            except ImportError:
                pass

        for mod in modules:
            mod.console = self._ui_logger

    def _run_orchestrator(self):
        """Run the orchestrator loop (called in background thread)."""
        try:
            self.orchestrator.run_loop()
        except Exception as e:
            console.print(f"\n[bold red]ERROR: Orchestrator crashed: {e}[/bold red]")
        finally:
            console.print("\n[dim]Orchestrator loop finished.[/dim]")
            self._running = False
            # Print a newline so the input prompt doesn't hang
            print()

    def _shutdown(self):
        """Gracefully stop the orchestrator."""
        self._running = False
        self.orchestrator._running = False
        if getattr(self.orchestrator, "_pause_requested", False):
            self.orchestrator.resume()

    def _handle_command(self, text: str):
        """Parse and execute slash commands."""
        parts = text.split(" ", 1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if cmd in ("/quit", "/exit"):
            console.print("[yellow]Shutting down…[/yellow]")
            self._shutdown()

        elif cmd == "/help":
            console.print(HELP_TEXT)

        elif cmd == "/status":
            state = self.orchestrator.state.value if self.orchestrator.state else "unknown"
            phase = self.orchestrator.phase
            iteration = self.orchestrator.loop_iteration
            paused = "PAUSED" if getattr(self.orchestrator, "_pause_requested", False) else "RUNNING"

            console.print(
                f"[bold cyan]Status[/bold cyan]: {paused}\n"
                f"  Phase: {phase}  |  State: {state}  |  Cycle: {iteration}"
            )

            if self._ui_logger:
                agent_parts = []
                for name, info in self._ui_logger.agents.items():
                    if info.state != AgentState.IDLE:
                        color = AGENT_COLORS.get(name, "white")
                        agent_parts.append(f"[{color}]{name}[/{color}]: {info.state.value}")
                if agent_parts:
                    console.print("  " + "  ".join(agent_parts))

        elif cmd == "/pause":
            if getattr(self.orchestrator, "_pause_requested", False):
                console.print("[yellow]Already paused.[/yellow]")
            else:
                self.orchestrator.pause()
                console.print("[yellow]Pause requested — will pause at next cycle start.[/yellow]")

        elif cmd == "/resume":
            if not getattr(self.orchestrator, "_pause_requested", False):
                console.print("[dim]Not paused.[/dim]")
            else:
                self.orchestrator.resume()
                console.print("[green]Resuming…[/green]")

        elif cmd == "/feedback":
            if not args.strip():
                console.print("[red]Usage: /feedback <message>[/red]")
                return

            from adelie.cli import cmd_feedback
            import argparse

            class FakeArgs(argparse.Namespace):
                def __init__(self, msg):
                    self.message = msg
                    self.priority = "normal"
                    self.list_pending = False

            try:
                cmd_feedback(FakeArgs(args))
                console.print("[green]Feedback recorded.[/green]")
            except Exception as e:
                console.print(f"[red]ERROR: Failed: {e}[/red]")

        elif cmd == "/commands":
            cmds = load_commands()
            if not cmds:
                console.print("[dim]No custom commands found. Create .adelie/commands/<name>.md[/dim]")
            else:
                console.print("[bold]Custom Commands:[/bold]")
                for c in cmds:
                    console.print(f"  [cyan]/{c.name}[/cyan]  {c.description}")

        elif cmd == "/plan":
            # Plan Mode: show pending plan
            from adelie.plan_mode import PlanManager
            plan_mgr = PlanManager()
            pending = plan_mgr.get_pending()
            if pending:
                console.print(f"\n[bold cyan]Pending Plan: {pending.plan_id}[/bold cyan]")
                console.print(f"  Cycle: #{pending.cycle}  |  Created: {pending.created_at}")
                if pending.expert_reasoning:
                    console.print(f"  Reasoning: {pending.expert_reasoning[:200]}")
                console.print(f"  Tasks ({len(pending.coder_tasks)}):")
                for i, task in enumerate(pending.coder_tasks, 1):
                    name = task.get('name', f'task_{i}')
                    desc = task.get('task', task.get('description', ''))[:100]
                    console.print(f"    {i}. [bold]{name}[/bold]: {desc}")
                console.print(f"\n  [dim]/approve to execute, /reject [reason] to reject[/dim]")
            else:
                console.print("[dim]No pending plans.[/dim]")

        elif cmd == "/approve":
            from adelie.plan_mode import PlanManager
            plan_mgr = PlanManager()
            pending = plan_mgr.get_pending()
            if pending:
                plan_mgr.approve(pending.plan_id)
                console.print(f"[green]✅ Plan approved: {pending.plan_id} — will execute next cycle[/green]")
            else:
                console.print("[dim]No pending plans to approve.[/dim]")

        elif cmd == "/reject":
            from adelie.plan_mode import PlanManager
            plan_mgr = PlanManager()
            pending = plan_mgr.get_pending()
            if pending:
                reason = args.strip() if args else "Rejected by user"
                plan_mgr.reject(pending.plan_id, reason)
                console.print(f"[yellow]❌ Plan rejected: {pending.plan_id}[/yellow]")
                # Send rejection as feedback
                try:
                    from adelie.cli import cmd_feedback
                    import argparse
                    class FakeArgs(argparse.Namespace):
                        def __init__(self, msg):
                            self.message = msg
                            self.priority = "high"
                            self.list_pending = False
                    cmd_feedback(FakeArgs(f"Plan rejected: {reason}"))
                except Exception:
                    pass
            else:
                console.print("[dim]No pending plans to reject.[/dim]")

        else:
            # Check if it's a custom command
            cmd_name = cmd.lstrip("/")
            custom = get_command(cmd_name)
            if custom:
                rendered = custom.render(args)
                console.print(f"[cyan]Running custom command: {cmd_name}[/cyan]")
                # Inject as feedback/intervention
                from adelie.cli import cmd_feedback
                import argparse

                class FakeArgs(argparse.Namespace):
                    def __init__(self, msg):
                        self.message = msg
                        self.priority = "high"
                        self.list_pending = False

                try:
                    cmd_feedback(FakeArgs(rendered))
                    console.print(f"[green]Command dispatched.[/green]")
                except Exception as e:
                    console.print(f"[red]ERROR: {e}[/red]")
            else:
                console.print(f"[red]Unknown command: {cmd}. Type /help[/red]")
