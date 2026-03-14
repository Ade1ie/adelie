"""tests/test_scheduler.py — Tests for per-agent scheduling."""
from __future__ import annotations

import time
import pytest
from adelie.scheduler import Scheduler, Frequency, AgentSchedule, default_schedules


class TestDefaultSchedules:
    def test_has_expected_agents(self):
        schedules = default_schedules()
        assert "writer" in schedules
        assert "expert" in schedules
        assert "reviewer" in schedules
        assert "scanner" in schedules

    def test_core_agents_every_cycle(self):
        schedules = default_schedules()
        assert schedules["writer"].frequency == Frequency.EVERY_CYCLE
        assert schedules["expert"].frequency == Frequency.EVERY_CYCLE

    def test_scanner_runs_once(self):
        schedules = default_schedules()
        assert schedules["scanner"].frequency == Frequency.ONCE


class TestScheduler:
    def test_every_cycle_always_runs(self):
        scheduler = Scheduler()
        assert scheduler.should_run("writer", 1) is True
        assert scheduler.should_run("writer", 100) is True

    def test_every_n_cycles(self):
        scheduler = Scheduler()
        # Reviewer runs every 3 cycles, starts with last_run=0
        assert scheduler.should_run("reviewer", 1) is False  # 1-0=1 < 3
        assert scheduler.should_run("reviewer", 3) is True   # 3-0=3 >= 3
        scheduler.mark_ran("reviewer", 3)
        assert scheduler.should_run("reviewer", 4) is False  # 4-3=1 < 3
        assert scheduler.should_run("reviewer", 5) is False  # 5-3=2 < 3
        assert scheduler.should_run("reviewer", 6) is True   # 6-3=3 >= 3

    def test_once_runs_only_first_time(self):
        scheduler = Scheduler()
        assert scheduler.should_run("scanner", 1) is True
        scheduler.mark_ran("scanner", 1)
        assert scheduler.should_run("scanner", 2) is False
        assert scheduler.should_run("scanner", 100) is False

    def test_manual_never_runs(self):
        scheduler = Scheduler()
        scheduler.set_frequency("writer", Frequency.MANUAL)
        assert scheduler.should_run("writer", 1) is False

    def test_trigger_forces_run(self):
        scheduler = Scheduler()
        scheduler.mark_ran("scanner", 1)  # Mark as run
        assert scheduler.should_run("scanner", 2) is False
        scheduler.trigger("scanner")
        assert scheduler.should_run("scanner", 2) is True

    def test_set_enabled(self):
        scheduler = Scheduler()
        scheduler.set_enabled("writer", False)
        assert scheduler.should_run("writer", 1) is False
        scheduler.set_enabled("writer", True)
        assert scheduler.should_run("writer", 1) is True

    def test_unknown_agent_always_runs(self):
        scheduler = Scheduler()
        assert scheduler.should_run("nonexistent", 1) is True

    def test_get_agents_due(self):
        scheduler = Scheduler()
        due = scheduler.get_agents_due(1)
        assert "writer" in due
        assert "expert" in due

    def test_get_status(self):
        scheduler = Scheduler()
        status = scheduler.get_status()
        assert "writer" in status
        assert status["writer"]["frequency"] == "every_cycle"


class TestAdaptiveInterval:
    def test_normal_uses_base(self):
        scheduler = Scheduler()
        assert scheduler.get_loop_interval(30, "normal") == 30

    def test_error_runs_faster(self):
        scheduler = Scheduler()
        interval = scheduler.get_loop_interval(30, "error")
        assert interval < 30

    def test_maintenance_runs_slower(self):
        scheduler = Scheduler()
        interval = scheduler.get_loop_interval(30, "maintenance")
        assert interval > 30

    def test_manual_override(self):
        scheduler = Scheduler()
        scheduler.set_adaptive_interval(10)
        assert scheduler.get_loop_interval(30, "normal") == 10
        scheduler.set_adaptive_interval(None)
        assert scheduler.get_loop_interval(30, "normal") == 30

    def test_minimum_interval(self):
        scheduler = Scheduler()
        assert scheduler.get_loop_interval(5, "error") >= 5
