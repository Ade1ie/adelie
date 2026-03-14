"""
adelie/interactive.py

Interactive REPL environment for the Adelie orchestrator.
Allows the user to issue commands (/feedback, /pause, /status) while the AI loop
runs continuously in a background thread. Outputs from the background thread are
patched so they don't break the user's input prompt.
"""

from __future__ import annotations

import sys
import threading
import time
from typing import Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.shortcuts import clear
from rich.console import Console

import adelie.config as cfg

console = Console()

class InteractiveSession:
    """Manages the interactive REPL and the background orchestrator thread."""

    def __init__(self, orchestrator):
        self.orchestrator = orchestrator
        self.session_thread: Optional[threading.Thread] = None
        self._stop_requested = False

    def start(self) -> None:
        """Start the orchestrator in the background and enter the interactive REPL."""
        console.print("[bold cyan]🐧 Adelie Interactive Session[/bold cyan]")
        console.print("[dim]Type '/help' for a list of commands. Press Ctrl+D to exit.[/dim]\n")

        # 1. Start Orchestrator in background
        self.session_thread = threading.Thread(
            target=self._run_orchestrator,
            name="AdelieOrchestratorThread",
            daemon=True,
        )
        self.session_thread.start()

        # 2. Start prompt loop in main thread
        try:
            self._prompt_loop()
        except (KeyboardInterrupt, EOFError):
            pass
        finally:
            self._shutdown()

    def _run_orchestrator(self) -> None:
        """Wrapper to run the orchestrator loop."""
        try:
            self.orchestrator.run_loop()
        except Exception as e:
            console.print(f"[bold red]❌ Orchestrator loop crashed: {e}[/bold red]")
        finally:
            # If orchestrator exits on its own, stop the interactive session
            if not self._stop_requested:
                console.print("\n[dim]Orchestrator loop finished. Press Enter to exit.[/dim]")

    def _prompt_loop(self) -> None:
        """The main REPL loop using prompt_toolkit."""
        session = PromptSession()

        while not self._stop_requested and self.orchestrator._running:
            with patch_stdout():
                try:
                    text = session.prompt("Adelie> ").strip()
                except (KeyboardInterrupt, EOFError):
                    break

                if not text:
                    continue

                if text.startswith("/"):
                    self._handle_command(text)
                else:
                    # Treat non-command text as feedback
                    self._handle_command(f"/feedback {text}")

    def _handle_command(self, text: str) -> None:
        """Parse and execute slash commands."""
        parts = text.split(" ", 1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if cmd in ("/quit", "/exit"):
            self._shutdown()
        elif cmd == "/help":
            self._cmd_help()
        elif cmd == "/status":
            self._cmd_status()
        elif cmd == "/pause":
            self._cmd_pause()
        elif cmd == "/resume":
            self._cmd_resume()
        elif cmd == "/clear":
            clear()
        elif cmd == "/feedback":
            self._cmd_feedback(args)
        else:
            print(f"Unknown command: {cmd}. Type /help for available commands.")

    def _cmd_help(self) -> None:
        help_text = """
Available Commands:
  /help                 Show this help message
  /status               Show current orchestrator status
  /pause                Pause the orchestrator loop before the next cycle
  /resume               Resume a paused orchestrator
  /feedback <message>   Send direct feedback to the AI
  /clear                Clear the terminal screen
  /exit, /quit          Stop the orchestrator and exit
"""
        print(help_text.strip())

    def _cmd_status(self) -> None:
        state = self.orchestrator.state.value if self.orchestrator.state else "unknown"
        phase = self.orchestrator.phase
        iteration = self.orchestrator.loop_iteration
        paused = "PAUSED" if getattr(self.orchestrator, "_pause_requested", False) else "RUNNING"
        
        console.print(f"[bold cyan]Status[/bold cyan]: {paused}")
        console.print(f"  [dim]Phase:[/dim]  {phase}")
        console.print(f"  [dim]State:[/dim]  {state}")
        console.print(f"  [dim]Cycle:[/dim]  {iteration}")

    def _cmd_pause(self) -> None:
        if getattr(self.orchestrator, "_pause_requested", False):
            print("Orchestrator is already paused (or pausing).")
        else:
            self.orchestrator.pause()
            print("Pause requested. Orchestrator will pause at the start of the next cycle.")

    def _cmd_resume(self) -> None:
        if not getattr(self.orchestrator, "_pause_requested", False):
            print("Orchestrator is not paused.")
        else:
            self.orchestrator.resume()
            print("Resuming orchestrator...")

    def _cmd_feedback(self, message: str) -> None:
        if not message.strip():
            print("Error: Feedback message cannot be empty.")
            return

        from adelie.cli import cmd_feedback
        import argparse
        
        # Borrow the logic from cli.cmd_feedback
        class FakeArgs(argparse.Namespace):
            def __init__(self, msg):
                self.message = msg
                self.priority = "normal"
                self.list_pending = False
                
        cmd_feedback(FakeArgs(message))
        console.print(f"[green]✅ Feedback recorded. AI will read it next cycle.[/green]")

    def _shutdown(self) -> None:
        """Gracefully shut down the orchestrator and exit."""
        if self._stop_requested:
            return
            
        self._stop_requested = True
        console.print("\n[yellow]Shutting down orchestrator... please wait.[/yellow]")
        
        self.orchestrator._running = False
        if getattr(self.orchestrator, "_pause_requested", False):
            self.orchestrator.resume()  # Unblock if paused
            
        if self.session_thread and self.session_thread.is_alive():
            # Wait up to a few seconds for graceful shutdown
            self.session_thread.join(timeout=3.0)
            
        console.print("[green]Goodbye![/green]")
        sys.exit(0)
