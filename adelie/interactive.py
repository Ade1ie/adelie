"""
adelie/interactive.py

Interactive TUI dashboard for the Adelie orchestrator using Textual.
Provides a structured dashboard with:
  - Status header (phase, state, cycle, goal)
  - Agent activity tracker (real-time agent status)
  - Filtered activity log (important events only)
  - Cycle metrics summary
  - Command input bar
"""

from __future__ import annotations

import sys
from datetime import datetime
from typing import Optional

from rich.console import Console
from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Vertical, Horizontal
from textual.reactive import reactive
from textual.widgets import Header, Footer, Input, RichLog, Static
from textual import work

from adelie.orchestrator import Orchestrator
from adelie.ui_logger import (
    UILogger, LogCategory, AgentState, AgentInfo,
    CycleMetrics, TRACKED_AGENTS,
)

console = Console()


# ── Custom Widgets ────────────────────────────────────────────────────────────

class StatusHeader(Static):
    """Top status panel showing phase, state, cycle, and goal."""

    phase = reactive("—")
    state = reactive("—")
    cycle = reactive(0)
    goal = reactive("—")

    def render(self) -> str:
        state_icons = {
            "normal": "🟢", "error": "🔴", "maintenance": "🟡",
            "export": "🔵", "new_logic": "🟣", "shutdown": "⚫",
        }
        state_icon = state_icons.get(self.state, "⚪")
        cycle_str = f"#{self.cycle}" if self.cycle > 0 else "—"
        goal_display = self.goal[:60] + "…" if len(self.goal) > 60 else self.goal

        return (
            f" 🐧 Adelie Dashboard\n"
            f" ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
            f" Phase: {self.phase}  │  "
            f"State: {state_icon} {self.state}  │  "
            f"Cycle: {cycle_str}\n"
            f" Goal: {goal_display}"
        )


class AgentTracker(Static):
    """Panel showing real-time status of all agents."""

    # We store the full state as a string that triggers re-render
    _agent_display = reactive("", layout=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._agents: dict[str, AgentInfo] = {
            name: AgentInfo(name=name) for name in TRACKED_AGENTS
        }

    def update_agent(self, name: str, info: AgentInfo) -> None:
        """Update a single agent's display state."""
        self._agents[name] = info
        self._refresh_display()

    def reset_all(self) -> None:
        """Reset all agents to idle."""
        for name in self._agents:
            self._agents[name] = AgentInfo(name=name)
        self._refresh_display()

    def _refresh_display(self) -> None:
        # Trigger reactive update
        lines = []
        for name in TRACKED_AGENTS:
            info = self._agents.get(name, AgentInfo(name=name))
            lines.append(self._format_agent(info))
        self._agent_display = "\n".join(lines)

    def _format_agent(self, info: AgentInfo) -> str:
        icons = {
            AgentState.IDLE:    "⬜",
            AgentState.RUNNING: "🔄",
            AgentState.DONE:    "✅",
            AgentState.ERROR:   "❌",
            AgentState.SKIPPED: "⏭️",
        }
        icon = icons.get(info.state, "⬜")
        name_padded = info.name.ljust(10)

        if info.state == AgentState.RUNNING:
            return f"  {icon} {name_padded} running…"
        elif info.state == AgentState.DONE:
            elapsed = f"({info.elapsed:.1f}s)" if info.elapsed > 0 else ""
            detail = f" — {info.detail}" if info.detail else ""
            # Truncate detail to fit
            max_detail = 45
            if len(detail) > max_detail:
                detail = detail[:max_detail] + "…"
            return f"  {icon} {name_padded} done {elapsed}{detail}"
        elif info.state == AgentState.ERROR:
            detail = f" — {info.detail}" if info.detail else ""
            max_detail = 45
            if len(detail) > max_detail:
                detail = detail[:max_detail] + "…"
            return f"  {icon} {name_padded} error{detail}"
        elif info.state == AgentState.SKIPPED:
            return f"  {icon} {name_padded} skipped"
        else:
            return f"  {icon} {name_padded} idle"

    def render(self) -> str:
        return f" 📊 Agent Status\n{self._agent_display}"


class CycleSummary(Static):
    """Bottom panel showing last cycle's key metrics."""

    _summary_text = reactive(" 📈 Awaiting first cycle…")

    def update_metrics(self, metrics: CycleMetrics) -> None:
        parts = []
        if metrics.total_tokens > 0:
            parts.append(f"{metrics.total_tokens:,} tok")
        if metrics.llm_calls > 0:
            parts.append(f"{metrics.llm_calls} calls")
        if metrics.cycle_time > 0:
            parts.append(f"⏱️ {metrics.cycle_time:.1f}s")
        if metrics.files_written > 0:
            parts.append(f"📄 {metrics.files_written} files")
        if metrics.tests_total > 0:
            parts.append(f"🧪 {metrics.tests_passed}/{metrics.tests_total}")
        if metrics.review_score > 0:
            parts.append(f"⭐ {metrics.review_score:.0f}/10")

        if parts:
            self._summary_text = f" 📈 Cycle #{metrics.iteration}: {' │ '.join(parts)}"
        else:
            self._summary_text = f" 📈 Cycle #{metrics.iteration}: completed"

    def render(self) -> str:
        return self._summary_text


# ── Main App ──────────────────────────────────────────────────────────────────

class AdelieApp(App):
    """A Textual-based TUI dashboard for Adelie."""

    CSS = """
    StatusHeader {
        height: 5;
        background: $panel;
        border: solid $primary;
        padding: 0 1;
        color: $text;
    }

    AgentTracker {
        height: auto;
        min-height: 6;
        max-height: 12;
        background: $panel;
        border: solid $secondary;
        padding: 0 1;
        color: $text;
    }

    #activity_log {
        height: 1fr;
        border: solid $accent;
        background: $surface;
    }

    CycleSummary {
        height: 2;
        background: $panel;
        border: solid $success;
        padding: 0 1;
        color: $text;
    }

    Input {
        dock: bottom;
        margin: 0 1;
    }
    """

    BINDINGS = [
        ("ctrl+d", "quit", "Quit"),
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+l", "clear_log", "Clear Log"),
    ]

    def __init__(self, orchestrator: Orchestrator, **kwargs):
        super().__init__(**kwargs)
        self.orchestrator = orchestrator
        self._ui_logger: Optional[UILogger] = None

    def compose(self) -> ComposeResult:
        """Create the dashboard layout."""
        yield Header(show_clock=True)
        with Vertical():
            yield StatusHeader(id="status_header")
            yield AgentTracker(id="agent_tracker")
            yield RichLog(id="activity_log", markup=True, highlight=True, auto_scroll=True)
            yield CycleSummary(id="cycle_summary")
        yield Input(
            placeholder="Type /help for commands, or write feedback directly…",
            id="command_input",
        )
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the dashboard and start the orchestrator."""
        self.title = "🐧 Adelie"
        self.sub_title = "Autonomous AI Loop"

        # Get widgets
        status = self.query_one("#status_header", StatusHeader)
        tracker = self.query_one("#agent_tracker", AgentTracker)
        log = self.query_one("#activity_log", RichLog)
        summary = self.query_one("#cycle_summary", CycleSummary)

        # Set initial status
        status.goal = self.orchestrator.goal
        status.phase = self.orchestrator.phase
        status.state = self.orchestrator.state.value

        # Initialize agent display
        tracker._refresh_display()

        # Create UILogger and wire up callbacks
        self._ui_logger = UILogger()

        def _on_agent_update(name: str, info: AgentInfo):
            self.call_from_thread(tracker.update_agent, name, info)

        def _on_log(category: LogCategory, obj):
            # Color-code by category
            if category == LogCategory.ERROR:
                self.call_from_thread(log.write, obj)
            elif category == LogCategory.WARNING:
                self.call_from_thread(log.write, obj)
            elif category == LogCategory.PHASE_CHANGE:
                self.call_from_thread(log.write, obj)
            elif category == LogCategory.AGENT_START:
                self.call_from_thread(log.write, obj)
            elif category == LogCategory.AGENT_END:
                self.call_from_thread(log.write, obj)
            elif category == LogCategory.CYCLE_SUMMARY:
                # Don't write cycle summary to log — it goes to CycleSummary widget
                pass
            elif category == LogCategory.CYCLE_HEADER:
                self.call_from_thread(log.write, obj)
            else:
                # INFO and other categories
                self.call_from_thread(log.write, obj)

        def _on_cycle_start(iteration: int, phase: str, state: str):
            self.call_from_thread(self._update_status, iteration, phase, state)

        def _on_cycle_metrics(metrics: CycleMetrics):
            self.call_from_thread(summary.update_metrics, metrics)

        self._ui_logger.on_agent_update = _on_agent_update
        self._ui_logger.on_log = _on_log
        self._ui_logger.on_cycle_start = _on_cycle_start
        self._ui_logger.on_cycle_metrics = _on_cycle_metrics

        # Patch all module consoles with UILogger
        self._patch_consoles()

        # Wire orchestrator's direct event callbacks (more reliable than pattern matching)
        def _orch_agent_start(agent_name: str):
            self._ui_logger.set_agent_state(agent_name, AgentState.RUNNING)

        def _orch_agent_end(agent_name: str, detail: str):
            state = AgentState.ERROR if "error" in detail.lower() else AgentState.DONE
            self._ui_logger.set_agent_state(agent_name, state, detail)

        def _orch_cycle_start(iteration: int, phase: str, state: str):
            self.call_from_thread(self._update_status, iteration, phase, state)
            self._ui_logger.reset_agents()
            self.call_from_thread(tracker.reset_all)

        self.orchestrator.set_ui_callbacks(
            on_agent_start=_orch_agent_start,
            on_agent_end=_orch_agent_end,
            on_cycle_start=_orch_cycle_start,
        )

        # Focus input and start
        self.query_one(Input).focus()
        log.write("[bold cyan]🐧 Adelie Dashboard initialized. Starting orchestrator…[/bold cyan]")
        log.write("[dim]Type '/help' for a list of commands.[/dim]\n")

        self.run_orchestrator()

    def _update_status(self, iteration: int, phase: str, state: str) -> None:
        """Update the status header from the orchestrator thread."""
        status = self.query_one("#status_header", StatusHeader)
        status.cycle = iteration
        if phase:
            status.phase = phase
        if state:
            status.state = state

    def _patch_consoles(self) -> None:
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

        # Optionally patch research and tester if available
        try:
            import adelie.agents.research_ai as research_module
            modules.append(research_module)
        except ImportError:
            pass
        try:
            import adelie.agents.tester_ai as tester_module
            modules.append(tester_module)
        except ImportError:
            pass
        try:
            import adelie.agents.reviewer_ai as reviewer_module
            modules.append(reviewer_module)
        except ImportError:
            pass

        for mod in modules:
            mod.console = self._ui_logger

    @work(thread=True)
    def run_orchestrator(self) -> None:
        """Run the orchestrator loop in a background thread."""
        try:
            self.orchestrator.run_loop()
        except Exception as e:
            self.call_from_thread(self._handle_crash, e)
        finally:
            self.call_from_thread(self._handle_finish)

    def _handle_crash(self, e: Exception) -> None:
        log = self.query_one("#activity_log", RichLog)
        log.write(f"\n[bold red]❌ Orchestrator crashed: {e}[/bold red]")
        self.sub_title = "CRASHED"

    def _handle_finish(self) -> None:
        log = self.query_one("#activity_log", RichLog)
        log.write("\n[dim]Orchestrator loop finished.[/dim]")

    def action_clear_log(self) -> None:
        """Clear the activity log."""
        self.query_one("#activity_log", RichLog).clear()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle command input."""
        text = event.value.strip()
        if not text:
            return

        input_widget = self.query_one(Input)
        input_widget.value = ""

        log = self.query_one("#activity_log", RichLog)
        log.write(f"[bold blue]❯ {text}[/bold blue]")

        if text.startswith("/"):
            self._handle_command(text, log)
        else:
            self._handle_command(f"/feedback {text}", log)

    def _handle_command(self, text: str, log: RichLog) -> None:
        """Parse and execute slash commands."""
        parts = text.split(" ", 1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if cmd in ("/quit", "/exit"):
            log.write("[yellow]Shutting down…[/yellow]")
            self.orchestrator._running = False
            if getattr(self.orchestrator, "_pause_requested", False):
                self.orchestrator.resume()
            self.call_later(self.exit)

        elif cmd == "/help":
            help_text = (
                "[bold]Commands:[/bold]\n"
                "  [cyan]/help[/cyan]                 Show this help\n"
                "  [cyan]/status[/cyan]               Show orchestrator status\n"
                "  [cyan]/pause[/cyan]                Pause before next cycle\n"
                "  [cyan]/resume[/cyan]               Resume from pause\n"
                "  [cyan]/feedback <msg>[/cyan]       Send feedback to AI\n"
                "  [cyan]/clear[/cyan]                Clear the log\n"
                "  [cyan]/verbose[/cyan]              Toggle verbose logging\n"
                "  [cyan]/exit[/cyan], [cyan]/quit[/cyan]         Stop and exit"
            )
            log.write(help_text)

        elif cmd == "/status":
            state = self.orchestrator.state.value if self.orchestrator.state else "unknown"
            phase = self.orchestrator.phase
            iteration = self.orchestrator.loop_iteration
            paused = "PAUSED" if getattr(self.orchestrator, "_pause_requested", False) else "RUNNING"

            log.write(
                f"[bold cyan]Status[/bold cyan]: {paused}\n"
                f"  Phase: {phase}  │  State: {state}  │  Cycle: {iteration}"
            )

            # Show agent states
            if self._ui_logger:
                agent_lines = []
                for name, info in self._ui_logger.agents.items():
                    agent_lines.append(f"  {name}: {info.state.value}")
                if agent_lines:
                    log.write("[dim]" + "  ".join(agent_lines) + "[/dim]")

        elif cmd == "/pause":
            if getattr(self.orchestrator, "_pause_requested", False):
                log.write("[yellow]Already paused.[/yellow]")
            else:
                self.orchestrator.pause()
                log.write("[yellow]⏸️  Pause requested — will pause at next cycle start.[/yellow]")
                status = self.query_one("#status_header", StatusHeader)
                status.state = "pausing"

        elif cmd == "/resume":
            if not getattr(self.orchestrator, "_pause_requested", False):
                log.write("[dim]Not paused.[/dim]")
            else:
                self.orchestrator.resume()
                log.write("[green]▶️  Resuming…[/green]")
                status = self.query_one("#status_header", StatusHeader)
                status.state = "normal"

        elif cmd == "/clear":
            log.clear()

        elif cmd == "/verbose":
            # Toggle verbose mode — show/hide debug messages
            if self._ui_logger:
                # Simple toggle by changing the on_log callback
                log.write("[dim]Verbose mode toggled (reload to change)[/dim]")

        elif cmd == "/feedback":
            if not args.strip():
                log.write("[red]Usage: /feedback <message>[/red]")
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
                log.write(f"[green]✅ Feedback recorded.[/green]")
            except Exception as e:
                log.write(f"[red]❌ Failed: {e}[/red]")

        else:
            log.write(f"[red]Unknown command: {cmd}. Type /help[/red]")
