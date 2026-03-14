"""
adelie/interactive.py

Interactive TUI environment for the Adelie orchestrator using Textual.
Provides a clear dashboard UI with a RichLog for background orchestrator 
output and a bottom Input bar for issuing slash commands.
"""

from __future__ import annotations

import sys
import threading
from typing import Optional

from rich.console import Console, RenderableType
from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Header, Footer, Input, RichLog
from textual import work

from adelie.orchestrator import Orchestrator


class ConsoleRedirector:
    """Redirects rich.console.Console prints to a Textual RichLog."""
    def __init__(self, log_widget: RichLog, original_console: Console):
        self.log_widget = log_widget
        self.original_console = original_console

    def print(self, *objects, **kwargs):
        """Intercepts console.print() and sends it to the RichLog via app.call_from_thread."""
        
        # We need to render the objects first, because RichLog expects strings or Renderables
        # Passing multiple objects to RichLog directly isn't as clean as what Console does.
        # But for Adelie, we almost always pass a single Renderable (string, Panel, Table, etc.)
        
        # Send each object to the RichLog
        for obj in objects:
            try:
                # Use call_from_thread to safely write to the UI from the background worker
                self.log_widget.app.call_from_thread(self.log_widget.write, obj)
            except Exception:
                # If app is shutting down, just print to normal stdout
                pass


class AdelieApp(App):
    """A Textual App for Adelie."""
    
    CSS = """
    RichLog {
        height: 1fr;
        border: solid cyan;
        background: $surface;
    }
    Input {
        dock: bottom;
        margin: 1 1;
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
        self._original_console: Optional[Console] = None

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header(show_clock=True)
        with Vertical():
            yield RichLog(id="main_log", markup=True, highlight=True, auto_scroll=True)
        yield Input(placeholder="Type /help for commands, or write feedback directly...", id="command_input")
        yield Footer()

    def on_mount(self) -> None:
        """Set up the environment and start the background orchestrator."""
        self.title = "🐧 Adelie Autonomous AI Loop"
        self.sub_title = f"Goal: {self.orchestrator.goal[:40]}..."
        
        # Set up log redirection
        log_widget = self.query_one(RichLog)
        
        # We must patch the global console used by Adelie's components
        import adelie.orchestrator as orch_module
        import adelie.agents.writer_ai as writer_module
        import adelie.agents.expert_ai as expert_module
        import adelie.agents.research_ai as research_module
        import adelie.agents.coder_ai as coder_module
        import adelie.agents.coder_manager as coder_manager_module
        import adelie.agents.tester_ai as tester_module
        import adelie.agents.runner_ai as runner_module
        import adelie.agents.monitor_ai as monitor_module
        import adelie.agents.analyst_ai as analyst_module
        import adelie.interactive as interactive_module

        self._original_console = orch_module.console
        redirector = ConsoleRedirector(log_widget, self._original_console)

        # Patch consoles in all modules that might print
        orch_module.console = redirector
        writer_module.console = redirector
        expert_module.console = redirector
        research_module.console = redirector
        coder_module.console = redirector
        coder_manager_module.console = redirector
        tester_module.console = redirector
        runner_module.console = redirector
        monitor_module.console = redirector
        analyst_module.console = redirector
        interactive_module.console = redirector

        # Focus input and start worker
        self.query_one(Input).focus()
        log_widget.write("[bold cyan]🐧 Adelie UI Initialized. Starting orchestrator loop...[/bold cyan]")
        log_widget.write("[dim]Type '/help' below for a list of available commands.[/dim]\n")
        
        self.run_orchestrator()

    @work(thread=True)
    def run_orchestrator(self) -> None:
        """Run the orchestrator loop in a background thread."""
        try:
            self.orchestrator.run_loop()
        except Exception as e:
            self.call_from_thread(self._handle_orchestrator_crash, e)
        finally:
            self.call_from_thread(self._handle_orchestrator_finish)

    def _handle_orchestrator_crash(self, e: Exception) -> None:
        log_widget = self.query_one(RichLog)
        log_widget.write(f"\n[bold red]❌ Orchestrator loop crashed: {e}[/bold red]")
        self.sub_title = "CRASHED"

    def _handle_orchestrator_finish(self) -> None:
        log_widget = self.query_one(RichLog)
        log_widget.write("\n[dim]Orchestrator loop finished. You can close this window now.[/dim]")
        
    def action_clear_log(self) -> None:
        """Action to clear the log."""
        self.query_one(RichLog).clear()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle when the user hits Enter in the input box."""
        text = event.value.strip()
        if not text:
            return

        # Clear the input
        input_widget = self.query_one(Input)
        input_widget.value = ""

        # Print what the user typed
        log_widget = self.query_one(RichLog)
        log_widget.write(f"[bold blue]Adelie> {text}[/bold blue]")

        # Process command
        if text.startswith("/"):
            self._handle_command(text, log_widget)
        else:
            self._handle_command(f"/feedback {text}", log_widget)

    def _handle_command(self, text: str, log_widget: RichLog) -> None:
        """Parse and execute slash commands."""
        parts = text.split(" ", 1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if cmd in ("/quit", "/exit"):
            log_widget.write("[yellow]Shutting down... please wait.[/yellow]")
            self.orchestrator._running = False
            if getattr(self.orchestrator, "_pause_requested", False):
                self.orchestrator.resume()  # unblock if paused
            
            # Use call_after_refresh so it pushes the text before quitting
            self.call_later(self.exit)

        elif cmd == "/help":
            help_text = """
[bold]Available Commands:[/bold]
  [cyan]/help[/cyan]                 Show this help message
  [cyan]/status[/cyan]               Show current orchestrator status
  [cyan]/pause[/cyan]                Pause the orchestrator loop before the next cycle
  [cyan]/resume[/cyan]               Resume a paused orchestrator
  [cyan]/feedback <msg>[/cyan]       Send direct feedback to the AI
  [cyan]/clear[/cyan]                Clear the log window
  [cyan]/exit[/cyan], [cyan]/quit[/cyan]         Stop the orchestrator and exit
"""
            log_widget.write(help_text.strip())

        elif cmd == "/status":
            state = self.orchestrator.state.value if self.orchestrator.state else "unknown"
            phase = self.orchestrator.phase
            iteration = self.orchestrator.loop_iteration
            paused = "PAUSED" if getattr(self.orchestrator, "_pause_requested", False) else "RUNNING"
            
            log_widget.write(f"[bold cyan]Status[/bold cyan]: {paused}")
            log_widget.write(f"  [dim]Phase:[/dim]  {phase}")
            log_widget.write(f"  [dim]State:[/dim]  {state}")
            log_widget.write(f"  [dim]Cycle:[/dim]  {iteration}")

        elif cmd == "/pause":
            if getattr(self.orchestrator, "_pause_requested", False):
                log_widget.write("[yellow]Orchestrator is already paused (or pausing).[/yellow]")
            else:
                self.orchestrator.pause()
                log_widget.write("[yellow]Pause requested. Orchestrator will pause at the start of the next cycle.[/yellow]")
                self.sub_title = "PAUSING..."

        elif cmd == "/resume":
            if not getattr(self.orchestrator, "_pause_requested", False):
                log_widget.write("[dim]Orchestrator is not paused.[/dim]")
            else:
                self.orchestrator.resume()
                log_widget.write("[green]Resuming orchestrator...[/green]")
                self.sub_title = f"Goal: {self.orchestrator.goal[:40]}..."

        elif cmd == "/clear":
            log_widget.clear()

        elif cmd == "/feedback":
            if not args.strip():
                log_widget.write("[red]Error: Feedback message cannot be empty.[/red]")
                return

            # Avoid circular import at top level
            from adelie.cli import cmd_feedback
            import argparse
            
            class FakeArgs(argparse.Namespace):
                def __init__(self, msg):
                    self.message = msg
                    self.priority = "normal"
                    self.list_pending = False
                    
            try:
                cmd_feedback(FakeArgs(args))
                log_widget.write(f"[green]✅ Feedback recorded. AI will read it next cycle.[/green]")
            except Exception as e:
                log_widget.write(f"[red]❌ Failed to save feedback: {e}[/red]")

        else:
            log_widget.write(f"[red]Unknown command: {cmd}. Type /help for available commands.[/red]")
