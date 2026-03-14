"""
adelie/process_supervisor.py

Lightweight process supervisor for the Adelie orchestrator.
Monitors spawned subprocesses, enforces timeouts, and provides
cleanup on shutdown — preventing orphaned processes.

Inspired by openclaw's process supervisor pattern.
"""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from rich.console import Console

console = Console()


# ── Process Status ───────────────────────────────────────────────────────────


class ProcessStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    NO_OUTPUT_TIMEOUT = "no_output_timeout"  # Killed due to no output
    KILLED = "killed"


@dataclass
class ManagedProcess:
    """A process tracked by the supervisor."""

    pid: int
    name: str
    command: str
    started_at: float
    timeout: int = 300  # Default 5 minutes
    no_output_timeout: int = 0  # 0 = disabled; seconds with no stdout/stderr before kill
    scope_key: str = ""  # Group key for cancel_scope()
    status: ProcessStatus = ProcessStatus.RUNNING
    exit_code: Optional[int] = None
    last_output_time: float = 0.0  # Updated on each stdout/stderr chunk
    _process: Optional[subprocess.Popen] = field(default=None, repr=False)
    _output_thread: Optional[threading.Thread] = field(default=None, repr=False)
    stdout: str = field(default="", repr=False)
    stderr: str = field(default="", repr=False)

    @property
    def elapsed(self) -> float:
        return time.time() - self.started_at

    @property
    def timed_out(self) -> bool:
        return self.elapsed > self.timeout and self.status == ProcessStatus.RUNNING

    @property
    def no_output_timed_out(self) -> bool:
        """Check if process has exceeded the no-output timeout."""
        if self.no_output_timeout <= 0 or self.status != ProcessStatus.RUNNING:
            return False
        return (time.time() - self.last_output_time) > self.no_output_timeout


# ── Supervisor ───────────────────────────────────────────────────────────────


class ProcessSupervisor:
    """
    Manages spawned subprocesses with timeout enforcement and cleanup.

    Usage:
        supervisor = ProcessSupervisor()
        proc = supervisor.spawn("build", "npm run build", timeout=120)
        supervisor.check_all()  # Called periodically
        supervisor.shutdown()   # On orchestrator exit
    """

    def __init__(self, max_concurrent: int = 5):
        self._processes: dict[int, ManagedProcess] = {}
        self._max_concurrent = max_concurrent
        self._history: list[ManagedProcess] = []

    def spawn(
        self,
        name: str,
        command: str,
        timeout: int = 300,
        no_output_timeout: int = 0,
        scope_key: str = "",
        cwd: str | None = None,
    ) -> ManagedProcess | None:
        """
        Spawn a command as a managed subprocess.

        Args:
            name:              Human-readable name for logging
            command:           Shell command to execute
            timeout:           Max seconds before kill
            no_output_timeout: Kill if no stdout/stderr for this many seconds (0=disabled)
            scope_key:         Group key for cancel_scope() bulk cancellation
            cwd:               Working directory (default: project root)

        Returns:
            ManagedProcess or None if at max concurrent limit.
        """
        active = [p for p in self._processes.values() if p.status == ProcessStatus.RUNNING]
        if len(active) >= self._max_concurrent:
            console.print(
                f"[yellow]⚠️  Max concurrent processes ({self._max_concurrent}) reached. "
                f"Cannot spawn '{name}'[/yellow]"
            )
            return None

        try:
            from adelie.config import PROJECT_ROOT
            work_dir = cwd or str(PROJECT_ROOT)

            proc = subprocess.Popen(
                command,
                shell=True,
                cwd=work_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid if os.name != "nt" else None,
            )

            now = time.time()
            managed = ManagedProcess(
                pid=proc.pid,
                name=name,
                command=command,
                started_at=now,
                timeout=timeout,
                no_output_timeout=no_output_timeout,
                scope_key=scope_key,
                last_output_time=now,
                _process=proc,
            )

            # Start output monitoring thread if we need to track output timing
            if no_output_timeout > 0:
                thread = threading.Thread(
                    target=self._monitor_output, args=(managed,), daemon=True
                )
                managed._output_thread = thread
                thread.start()

            self._processes[proc.pid] = managed
            scope_info = f", scope='{scope_key}'" if scope_key else ""
            no_out_info = f", no-output-timeout={no_output_timeout}s" if no_output_timeout else ""
            console.print(
                f"[dim]  🚀 Spawned '{name}' (PID {proc.pid}, timeout {timeout}s"
                f"{no_out_info}{scope_info})[/dim]"
            )
            return managed

        except Exception as e:
            console.print(f"[red]❌ Failed to spawn '{name}': {e}[/red]")
            return None

    @staticmethod
    def _monitor_output(managed: ManagedProcess) -> None:
        """Background thread: read stdout/stderr and update last_output_time."""
        proc = managed._process
        if proc is None or proc.stdout is None:
            return
        try:
            while managed.status == ProcessStatus.RUNNING:
                # Non-blocking read using a small poll interval
                if proc.poll() is not None:
                    break
                # Read available data from stdout
                data = proc.stdout.read1(4096) if hasattr(proc.stdout, 'read1') else b""
                if data:
                    managed.stdout += data.decode(errors="replace")
                    managed.last_output_time = time.time()
        except Exception:
            pass  # Thread exits silently on process cleanup

    def check_all(self) -> list[ManagedProcess]:
        """
        Check status of all managed processes.
        Kills timed-out processes (overall and no-output). Returns list of newly completed/failed.
        """
        changed: list[ManagedProcess] = []

        for pid, managed in list(self._processes.items()):
            if managed.status != ProcessStatus.RUNNING:
                continue

            proc = managed._process
            if proc is None:
                continue

            # Check if completed
            retcode = proc.poll()
            if retcode is not None:
                managed.exit_code = retcode
                managed.status = (
                    ProcessStatus.COMPLETED if retcode == 0 else ProcessStatus.FAILED
                )
                changed.append(managed)
                self._history.append(managed)
                console.print(
                    f"[dim]  {'✅' if retcode == 0 else '❌'} "
                    f"'{managed.name}' finished (exit={retcode}, "
                    f"{managed.elapsed:.1f}s)[/dim]"
                )
                continue

            # Check overall timeout
            if managed.timed_out:
                self._kill_process(managed)
                managed.status = ProcessStatus.TIMEOUT
                managed.exit_code = -1
                changed.append(managed)
                self._history.append(managed)
                console.print(
                    f"[yellow]⏰ '{managed.name}' timed out after "
                    f"{managed.timeout}s — killed[/yellow]"
                )
                continue

            # Check no-output timeout (openclaw pattern: noOutputTimeout)
            if managed.no_output_timed_out:
                self._kill_process(managed)
                managed.status = ProcessStatus.NO_OUTPUT_TIMEOUT
                managed.exit_code = -1
                changed.append(managed)
                self._history.append(managed)
                no_output_elapsed = time.time() - managed.last_output_time
                console.print(
                    f"[yellow]🔇 '{managed.name}' killed — no output for "
                    f"{no_output_elapsed:.0f}s (limit: {managed.no_output_timeout}s)[/yellow]"
                )

        # Cleanup completed from active list
        self._processes = {
            pid: p for pid, p in self._processes.items()
            if p.status == ProcessStatus.RUNNING
        }

        return changed

    def kill(self, pid: int) -> bool:
        """Kill a specific process by PID."""
        managed = self._processes.get(pid)
        if managed and managed.status == ProcessStatus.RUNNING:
            self._kill_process(managed)
            managed.status = ProcessStatus.KILLED
            self._history.append(managed)
            del self._processes[pid]
            return True
        return False

    def cancel_scope(self, scope_key: str) -> int:
        """
        Kill all running processes with the given scope_key.
        Inspired by openclaw's cancelScope pattern: related processes
        (e.g., all build steps) share a scope and can be cancelled together.

        Args:
            scope_key: The scope group key.

        Returns:
            Number of processes killed.
        """
        if not scope_key.strip():
            return 0

        killed = 0
        for pid, managed in list(self._processes.items()):
            if managed.scope_key == scope_key and managed.status == ProcessStatus.RUNNING:
                self._kill_process(managed)
                managed.status = ProcessStatus.KILLED
                self._history.append(managed)
                killed += 1
                console.print(f"[dim]  🛑 Scope-cancelled '{managed.name}' (scope: {scope_key})[/dim]")

        # Cleanup
        self._processes = {
            pid: p for pid, p in self._processes.items()
            if p.status == ProcessStatus.RUNNING
        }
        return killed

    def shutdown(self) -> int:
        """
        Kill all running processes. Called on orchestrator shutdown.
        Returns count of processes killed.
        """
        killed = 0
        for pid, managed in list(self._processes.items()):
            if managed.status == ProcessStatus.RUNNING:
                self._kill_process(managed)
                managed.status = ProcessStatus.KILLED
                self._history.append(managed)
                killed += 1
                console.print(f"[dim]  🛑 Killed '{managed.name}' (PID {pid})[/dim]")
        self._processes.clear()
        return killed

    def _kill_process(self, managed: ManagedProcess) -> None:
        """Kill a process and its process group."""
        proc = managed._process
        if proc is None:
            return
        try:
            if os.name != "nt":
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            else:
                proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    # ── Status ───────────────────────────────────────────────────────────────

    @property
    def active_count(self) -> int:
        return sum(1 for p in self._processes.values() if p.status == ProcessStatus.RUNNING)

    def get_status(self) -> dict:
        """Return current supervisor status."""
        active = [
            {"pid": p.pid, "name": p.name, "elapsed": f"{p.elapsed:.0f}s"}
            for p in self._processes.values()
            if p.status == ProcessStatus.RUNNING
        ]
        return {
            "active": active,
            "active_count": len(active),
            "max_concurrent": self._max_concurrent,
            "total_spawned": len(self._history) + len(self._processes),
            "total_completed": sum(1 for h in self._history if h.status == ProcessStatus.COMPLETED),
            "total_failed": sum(1 for h in self._history if h.status in (ProcessStatus.FAILED, ProcessStatus.TIMEOUT)),
        }
