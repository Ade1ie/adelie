"""
adelie/scheduler.py

Flexible scheduling for the Adelie orchestrator.
Supports per-agent execution frequencies, time-of-day schedules,
and adaptive intervals based on system activity.

Inspired by openclaw's cron scheduling — adapted as a lightweight
Python scheduler (no external cron dependency).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from rich.console import Console

console = Console()


# ── Schedule Types ───────────────────────────────────────────────────────────


class Frequency(str, Enum):
    """How often an agent should run."""
    EVERY_CYCLE = "every_cycle"        # Every orchestrator loop
    EVERY_N_CYCLES = "every_n_cycles"  # Every N loops
    INTERVAL = "interval"              # Time-based (every N seconds)
    ONCE = "once"                      # Run once, then never again
    MANUAL = "manual"                  # Only when explicitly triggered


@dataclass
class AgentSchedule:
    """Schedule configuration for one agent."""

    agent_name: str
    frequency: Frequency = Frequency.EVERY_CYCLE
    cycle_interval: int = 1           # For EVERY_N_CYCLES: run every N cycles
    time_interval: int = 60           # For INTERVAL: run every N seconds
    enabled: bool = True

    # Runtime tracking
    last_run_cycle: int = 0
    last_run_time: float = 0.0
    total_runs: int = 0
    has_run_once: bool = False


# ── Default Schedules ────────────────────────────────────────────────────────


def default_schedules() -> dict[str, AgentSchedule]:
    """Create default per-agent schedules."""
    return {
        # Core agents — run every cycle
        "writer": AgentSchedule(
            agent_name="writer",
            frequency=Frequency.EVERY_CYCLE,
        ),
        "expert": AgentSchedule(
            agent_name="expert",
            frequency=Frequency.EVERY_CYCLE,
        ),

        # Quality agents — run less frequently
        "reviewer": AgentSchedule(
            agent_name="reviewer",
            frequency=Frequency.EVERY_N_CYCLES,
            cycle_interval=3,
        ),
        "tester": AgentSchedule(
            agent_name="tester",
            frequency=Frequency.EVERY_N_CYCLES,
            cycle_interval=3,
        ),

        # Utility agents
        "scanner": AgentSchedule(
            agent_name="scanner",
            frequency=Frequency.ONCE,  # Only on bootstrap
        ),
        "monitor": AgentSchedule(
            agent_name="monitor",
            frequency=Frequency.EVERY_N_CYCLES,
            cycle_interval=5,
        ),
        "analyst": AgentSchedule(
            agent_name="analyst",
            frequency=Frequency.EVERY_N_CYCLES,
            cycle_interval=5,
        ),

        # Notification agents
        "inform": AgentSchedule(
            agent_name="inform",
            frequency=Frequency.EVERY_N_CYCLES,
            cycle_interval=10,
        ),
        "research": AgentSchedule(
            agent_name="research",
            frequency=Frequency.EVERY_CYCLE,  # Only fires when Expert requests it
        ),
    }


# ── Scheduler ────────────────────────────────────────────────────────────────


class Scheduler:
    """
    Manages per-agent execution scheduling.

    Usage:
        scheduler = Scheduler()
        if scheduler.should_run("reviewer", current_cycle):
            reviewer_ai.run(...)
            scheduler.mark_ran("reviewer", current_cycle)
    """

    def __init__(self, schedules: dict[str, AgentSchedule] | None = None):
        self._schedules = schedules or default_schedules()
        self._adaptive_interval: int | None = None

    def should_run(self, agent_name: str, current_cycle: int) -> bool:
        """
        Check if an agent should run in this cycle.

        Args:
            agent_name:    Name of the agent
            current_cycle: Current loop iteration number

        Returns:
            True if the agent should execute this cycle.
        """
        schedule = self._schedules.get(agent_name)
        if schedule is None:
            return True  # Unknown agent → always run (safe default)
        if not schedule.enabled:
            return False

        now = time.time()

        if schedule.frequency == Frequency.EVERY_CYCLE:
            return True

        elif schedule.frequency == Frequency.EVERY_N_CYCLES:
            cycles_since = current_cycle - schedule.last_run_cycle
            return cycles_since >= schedule.cycle_interval

        elif schedule.frequency == Frequency.INTERVAL:
            elapsed = now - schedule.last_run_time
            return elapsed >= schedule.time_interval

        elif schedule.frequency == Frequency.ONCE:
            return not schedule.has_run_once

        elif schedule.frequency == Frequency.MANUAL:
            return False

        return True

    def mark_ran(self, agent_name: str, current_cycle: int) -> None:
        """Record that an agent has executed."""
        schedule = self._schedules.get(agent_name)
        if schedule is None:
            return
        schedule.last_run_cycle = current_cycle
        schedule.last_run_time = time.time()
        schedule.total_runs += 1
        schedule.has_run_once = True

    def trigger(self, agent_name: str) -> None:
        """Manually trigger an agent to run on the next cycle."""
        schedule = self._schedules.get(agent_name)
        if schedule:
            # Reset last_run so should_run returns True
            schedule.last_run_cycle = 0
            schedule.last_run_time = 0.0
            if schedule.frequency == Frequency.ONCE:
                schedule.has_run_once = False

    def set_enabled(self, agent_name: str, enabled: bool) -> None:
        """Enable or disable an agent."""
        schedule = self._schedules.get(agent_name)
        if schedule:
            schedule.enabled = enabled

    def set_frequency(
        self,
        agent_name: str,
        frequency: Frequency,
        cycle_interval: int | None = None,
        time_interval: int | None = None,
    ) -> None:
        """Update an agent's schedule at runtime."""
        schedule = self._schedules.get(agent_name)
        if schedule is None:
            schedule = AgentSchedule(agent_name=agent_name, frequency=frequency)
            self._schedules[agent_name] = schedule
        else:
            schedule.frequency = frequency
        if cycle_interval is not None:
            schedule.cycle_interval = cycle_interval
        if time_interval is not None:
            schedule.time_interval = time_interval

    # ── Adaptive Interval ────────────────────────────────────────────────────

    def get_loop_interval(self, base_interval: int, current_state: str) -> int:
        """
        Calculate adaptive loop interval based on system state.
        More active states → shorter intervals. Idle states → longer.
        """
        if self._adaptive_interval is not None:
            return self._adaptive_interval

        multiplier = {
            "error": 0.5,       # Faster when recovering
            "new_logic": 0.75,  # Faster when bootstrapping
            "normal": 1.0,      # Default
            "maintenance": 2.0, # Slower during maintenance
            "export": 1.0,      # Default for export
            "shutdown": 1.0,    # Default
        }.get(current_state, 1.0)

        return max(5, int(base_interval * multiplier))

    def set_adaptive_interval(self, seconds: int | None) -> None:
        """Override the adaptive interval (None = auto)."""
        self._adaptive_interval = seconds

    # ── Status ───────────────────────────────────────────────────────────────

    def get_status(self) -> dict[str, dict]:
        """Return current schedule status for all agents."""
        status = {}
        for name, schedule in self._schedules.items():
            status[name] = {
                "frequency": schedule.frequency.value,
                "enabled": schedule.enabled,
                "total_runs": schedule.total_runs,
                "last_run_cycle": schedule.last_run_cycle,
            }
            if schedule.frequency == Frequency.EVERY_N_CYCLES:
                status[name]["cycle_interval"] = schedule.cycle_interval
            elif schedule.frequency == Frequency.INTERVAL:
                status[name]["time_interval_seconds"] = schedule.time_interval
        return status

    def get_agents_due(self, current_cycle: int) -> list[str]:
        """Return list of agent names that should run this cycle."""
        return [
            name for name in self._schedules
            if self.should_run(name, current_cycle)
        ]

    def reset(self) -> None:
        """Reset all schedules to initial state."""
        self._schedules = default_schedules()
        self._adaptive_interval = None
