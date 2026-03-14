"""tests/test_hooks.py — Tests for the hooks/plugin system."""
from __future__ import annotations

import pytest
from adelie.hooks import (
    HookEvent,
    HookManager,
    cycle_logger_plugin,
    error_counter_plugin,
    state_change_notifier_plugin,
)


class TestHookManager:
    def test_register_and_emit(self):
        hooks = HookManager()
        results = []
        hooks.register(HookEvent.AFTER_CYCLE, lambda e, c: results.append(c.get("iteration")), name="test")
        hooks.emit(HookEvent.AFTER_CYCLE, {"iteration": 42})
        assert results == [42]

    def test_multiple_hooks_same_event(self):
        hooks = HookManager()
        order = []
        hooks.register(HookEvent.AFTER_CYCLE, lambda e, c: order.append("a"), name="a")
        hooks.register(HookEvent.AFTER_CYCLE, lambda e, c: order.append("b"), name="b")
        hooks.emit(HookEvent.AFTER_CYCLE, {})
        assert order == ["a", "b"]

    def test_priority_ordering(self):
        hooks = HookManager()
        order = []
        hooks.register(HookEvent.AFTER_CYCLE, lambda e, c: order.append("low"), name="low", priority=10)
        hooks.register(HookEvent.AFTER_CYCLE, lambda e, c: order.append("high"), name="high", priority=1)
        hooks.emit(HookEvent.AFTER_CYCLE, {})
        assert order == ["high", "low"]

    def test_unregister(self):
        hooks = HookManager()
        hooks.register(HookEvent.AFTER_CYCLE, lambda e, c: None, name="test")
        assert hooks.has_hooks(HookEvent.AFTER_CYCLE)
        hooks.unregister(HookEvent.AFTER_CYCLE, "test")
        assert not hooks.has_hooks(HookEvent.AFTER_CYCLE)

    def test_emit_no_hooks(self):
        hooks = HookManager()
        count = hooks.emit(HookEvent.ON_SHUTDOWN, {})
        assert count == 0

    def test_error_in_hook_doesnt_crash(self):
        hooks = HookManager()
        hooks.register(HookEvent.AFTER_CYCLE, lambda e, c: 1 / 0, name="bad")
        hooks.register(HookEvent.AFTER_CYCLE, lambda e, c: None, name="good")
        count = hooks.emit(HookEvent.AFTER_CYCLE, {})
        assert count == 1  # good ran, bad failed

    def test_clear_specific_event(self):
        hooks = HookManager()
        hooks.register(HookEvent.AFTER_CYCLE, lambda e, c: None, name="a")
        hooks.register(HookEvent.ON_ERROR, lambda e, c: None, name="b")
        hooks.clear(HookEvent.AFTER_CYCLE)
        assert not hooks.has_hooks(HookEvent.AFTER_CYCLE)
        assert hooks.has_hooks(HookEvent.ON_ERROR)

    def test_clear_all(self):
        hooks = HookManager()
        hooks.register(HookEvent.AFTER_CYCLE, lambda e, c: None, name="a")
        hooks.register(HookEvent.ON_ERROR, lambda e, c: None, name="b")
        hooks.clear()
        assert not hooks.has_hooks(HookEvent.AFTER_CYCLE)
        assert not hooks.has_hooks(HookEvent.ON_ERROR)

    def test_get_status(self):
        hooks = HookManager()
        hooks.register(HookEvent.AFTER_CYCLE, lambda e, c: None, name="logger")
        status = hooks.get_status()
        assert status["total_hooks"] == 1
        assert "after_cycle" in status["events"]


class TestPlugins:
    def test_cycle_logger_plugin(self):
        hooks = HookManager()
        cycle_logger_plugin(hooks)
        assert hooks.has_hooks(HookEvent.BEFORE_CYCLE)
        assert hooks.has_hooks(HookEvent.AFTER_CYCLE)

    def test_error_counter_plugin(self):
        hooks = HookManager()
        error_counter_plugin(hooks)
        assert hooks.has_hooks(HookEvent.ON_ERROR)
        # Should not crash when emitting
        hooks.emit(HookEvent.ON_ERROR, {"error": "test"})

    def test_state_change_plugin(self):
        hooks = HookManager()
        state_change_notifier_plugin(hooks)
        assert hooks.has_hooks(HookEvent.STATE_CHANGE)
