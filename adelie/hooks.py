"""
adelie/hooks.py

Event-driven hooks/plugin system for the Adelie orchestrator.
Allows registering callbacks for lifecycle events — e.g., before/after
each cycle, on state change, on error, on KB update.

Inspired by openclaw's hooks system — adapted as a simple,
synchronous event emitter.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional

from rich.console import Console

console = Console()


# ── Hook Events ──────────────────────────────────────────────────────────────


class HookEvent(str, Enum):
    """Lifecycle events that plugins can hook into."""

    # Cycle lifecycle
    BEFORE_CYCLE = "before_cycle"
    AFTER_CYCLE = "after_cycle"

    # Agent lifecycle
    BEFORE_AGENT = "before_agent"
    AFTER_AGENT = "after_agent"

    # State changes
    STATE_CHANGE = "state_change"
    PHASE_CHANGE = "phase_change"

    # KB events
    KB_FILE_WRITTEN = "kb_file_written"
    KB_FILE_DELETED = "kb_file_deleted"

    # Error handling
    ON_ERROR = "on_error"
    ON_RECOVERY = "on_recovery"

    # System lifecycle
    ON_STARTUP = "on_startup"
    ON_SHUTDOWN = "on_shutdown"

    # Loop detection
    LOOP_DETECTED = "loop_detected"

    # Production bridge
    PRODUCTION_ALERT = "production_alert"


# ── Hook Callback Type ───────────────────────────────────────────────────────

# Callbacks receive (event_name: str, context: dict) -> None
HookCallback = Callable[[str, dict], None]


@dataclass
class HookRegistration:
    """A registered hook callback."""

    event: HookEvent
    callback: HookCallback
    name: str
    priority: int = 0  # Lower = runs first
    plugin_name: str = ""


# ── Hook Manager ─────────────────────────────────────────────────────────────


class HookManager:
    """
    Central event bus for the Adelie orchestrator.

    Usage:
        hooks = HookManager()
        hooks.register(HookEvent.AFTER_CYCLE, my_callback, name="logger")
        hooks.emit(HookEvent.AFTER_CYCLE, {"iteration": 42})
    """

    def __init__(self):
        self._hooks: dict[HookEvent, list[HookRegistration]] = defaultdict(list)
        self._emit_count: int = 0
        self._error_count: int = 0

    def register(
        self,
        event: HookEvent,
        callback: HookCallback,
        name: str = "",
        priority: int = 0,
        plugin_name: str = "",
    ) -> None:
        """
        Register a callback for an event.

        Args:
            event:       Which event to hook into
            callback:    Function(event_name, context) to call
            name:        Human-readable name for this hook
            priority:    Lower numbers run first
            plugin_name: Which plugin registered this
        """
        reg = HookRegistration(
            event=event,
            callback=callback,
            name=name or f"hook_{len(self._hooks[event])}",
            priority=priority,
            plugin_name=plugin_name,
        )
        self._hooks[event].append(reg)
        # Keep sorted by priority
        self._hooks[event].sort(key=lambda r: r.priority)

    def unregister(self, event: HookEvent, name: str) -> bool:
        """Remove a named hook. Returns True if found."""
        before = len(self._hooks[event])
        self._hooks[event] = [
            r for r in self._hooks[event] if r.name != name
        ]
        return len(self._hooks[event]) < before

    def emit(self, event: HookEvent, context: dict | None = None) -> int:
        """
        Emit an event, calling all registered callbacks.

        Args:
            event:   The event to emit
            context: Data dict passed to callbacks

        Returns:
            Number of callbacks executed.
        """
        hooks = self._hooks.get(event, [])
        if not hooks:
            return 0

        ctx = context or {}
        ctx["event"] = event.value
        ctx["timestamp"] = time.time()
        executed = 0

        for reg in hooks:
            try:
                reg.callback(event.value, ctx)
                executed += 1
            except Exception as e:
                self._error_count += 1
                console.print(
                    f"[dim]⚠️  Hook '{reg.name}' error on {event.value}: {e}[/dim]"
                )

        self._emit_count += executed
        return executed

    def has_hooks(self, event: HookEvent) -> bool:
        """Check if any hooks are registered for an event."""
        return len(self._hooks.get(event, [])) > 0

    def clear(self, event: HookEvent | None = None) -> None:
        """Clear hooks for a specific event, or all hooks."""
        if event:
            self._hooks[event].clear()
        else:
            self._hooks.clear()

    def get_status(self) -> dict:
        """Return current hook registration status."""
        return {
            "total_hooks": sum(len(hooks) for hooks in self._hooks.values()),
            "total_emits": self._emit_count,
            "total_errors": self._error_count,
            "events": {
                event.value: [r.name for r in hooks]
                for event, hooks in self._hooks.items()
                if hooks
            },
        }


# ── Pre-built Plugin Helpers ─────────────────────────────────────────────────


def cycle_logger_plugin(hooks: HookManager) -> None:
    """Plugin that logs cycle start/end times."""

    def on_before(event: str, ctx: dict) -> None:
        ctx["_cycle_start"] = time.time()

    def on_after(event: str, ctx: dict) -> None:
        start = ctx.get("_cycle_start", time.time())
        elapsed = time.time() - start
        iteration = ctx.get("iteration", "?")
        console.print(f"[dim]⏱️  Cycle #{iteration} took {elapsed:.1f}s[/dim]")

    hooks.register(HookEvent.BEFORE_CYCLE, on_before, name="cycle_logger_start", plugin_name="cycle_logger")
    hooks.register(HookEvent.AFTER_CYCLE, on_after, name="cycle_logger_end", plugin_name="cycle_logger")


def error_counter_plugin(hooks: HookManager) -> None:
    """Plugin that tracks error frequency."""
    error_times: list[float] = []

    def on_error(event: str, ctx: dict) -> None:
        error_times.append(time.time())
        # Keep last 20
        while len(error_times) > 20:
            error_times.pop(0)

        # Alert if high error rate (3+ in 60 seconds)
        recent = [t for t in error_times if time.time() - t < 60]
        if len(recent) >= 3:
            console.print(
                f"[bold red]🚨 High error rate: {len(recent)} errors in last 60s[/bold red]"
            )

    hooks.register(HookEvent.ON_ERROR, on_error, name="error_counter", plugin_name="error_counter")


def state_change_notifier_plugin(hooks: HookManager) -> None:
    """Plugin that logs state transitions."""

    def on_state_change(event: str, ctx: dict) -> None:
        old = ctx.get("old_state", "?")
        new = ctx.get("new_state", "?")
        console.print(f"[dim]🔀 State: {old} → {new}[/dim]")

    hooks.register(HookEvent.STATE_CHANGE, on_state_change, name="state_notifier", plugin_name="state_notifier")
