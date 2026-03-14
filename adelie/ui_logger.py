"""
adelie/ui_logger.py

Structured logging bridge for the Adelie TUI dashboard.
Intercepts `console.print()` calls from various modules and routes them
to the appropriate TUI widgets based on automatic message categorization.
"""

from __future__ import annotations

import re
import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from rich.console import Console


# ── Log Categories ────────────────────────────────────────────────────────────

class LogCategory(str, Enum):
    AGENT_START   = "agent_start"
    AGENT_END     = "agent_end"
    AGENT_ERROR   = "agent_error"
    PROGRESS      = "progress"
    PHASE_CHANGE  = "phase_change"
    CYCLE_HEADER  = "cycle_header"
    CYCLE_SUMMARY = "cycle_summary"
    WARNING       = "warning"
    ERROR         = "error"
    INFO          = "info"
    DEBUG         = "debug"


# ── Agent State ───────────────────────────────────────────────────────────────

class AgentState(str, Enum):
    IDLE    = "idle"
    RUNNING = "running"
    DONE    = "done"
    ERROR   = "error"
    SKIPPED = "skipped"


@dataclass
class AgentInfo:
    name: str
    state: AgentState = AgentState.IDLE
    start_time: float = 0.0
    elapsed: float = 0.0
    detail: str = ""


# ── Cycle Metrics ─────────────────────────────────────────────────────────

@dataclass
class CycleMetrics:
    iteration: int = 0
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    llm_calls: int = 0
    files_written: int = 0
    tests_passed: int = 0
    tests_total: int = 0
    review_score: float = 0.0
    cycle_time: float = 0.0
    parallel_info: str = ""


# ── Pattern matchers for auto-categorization ──────────────────────────────────

_AGENT_START_PATTERNS = [
    (r"📝 Writer AI.*generating", "Writer"),
    (r"🧠 Expert AI.*situation=", "Expert"),
    (r"🧠 Expert AI.*generating decision", "Expert"),
    (r"🔍 Scanner AI", "Scanner"),
    (r"📡 Monitor AI", "Monitor"),
    (r"📋 Inform AI", "Inform"),
    (r"🔬 Research AI", "Research"),
    (r"━━━ Layer \d+ Coders ━━━", "Coder"),
    (r"⚡ Phase \d+[ab]?:", None),  # Parallel phase start
]

_AGENT_END_PATTERNS = [
    (r"📝 Writer AI.*done.*(\d+) file", "Writer"),
    (r"📊 Loop #\d+:", None),  # Cycle summary
]

_ERROR_PATTERNS = [
    r"❌",
    r"💥",
    r"LOOP DETECTED",
]

_WARNING_PATTERNS = [
    r"⚠️",
    r"🔄.*[Rr]etry",
    r"🔄.*[Rr]ecovery",
    r"Loop warning",
]

_PHASE_PATTERNS = [
    r"Phase transition",
    r"Auto Phase Transition",
    r"confirmed phase →",
]

_DEBUG_PATTERNS = [
    r"^\[dim\]",
    r"⏭.*Skipped",
    r"⏭.*Removed",
    r"Sleeping \d+s",
]


def _classify_message(text: str) -> tuple[LogCategory, Optional[str]]:
    """
    Auto-classify a rich-formatted message into a LogCategory.
    Returns (category, agent_name_or_none).
    """
    # Strip rich markup for pattern matching
    plain = re.sub(r"\[/?[^\]]*\]", "", text)

    # Agent start
    for pattern, agent_name in _AGENT_START_PATTERNS:
        if re.search(pattern, plain):
            return LogCategory.AGENT_START, agent_name

    # Agent end
    for pattern, agent_name in _AGENT_END_PATTERNS:
        if re.search(pattern, plain):
            if agent_name:
                return LogCategory.AGENT_END, agent_name
            return LogCategory.CYCLE_SUMMARY, None

    # Phase changes
    for pattern in _PHASE_PATTERNS:
        if re.search(pattern, plain):
            return LogCategory.PHASE_CHANGE, None

    # Errors
    for pattern in _ERROR_PATTERNS:
        if re.search(pattern, plain):
            return LogCategory.ERROR, None

    # Warnings
    for pattern in _WARNING_PATTERNS:
        if re.search(pattern, plain):
            return LogCategory.WARNING, None

    # Cycle header (Rule with "Loop #")
    if re.search(r"Loop #\d+.*state=", plain):
        return LogCategory.CYCLE_HEADER, None

    # Debug/dim messages
    for pattern in _DEBUG_PATTERNS:
        if re.search(pattern, text):  # Use original text for markup detection
            return LogCategory.DEBUG, None

    return LogCategory.INFO, None


# ── Main UILogger class ──────────────────────────────────────────────────────

# The list of tracked agents
TRACKED_AGENTS = [
    "Writer", "Expert", "Research", "Coder",
    "Reviewer", "Tester", "Runner", "Monitor", "Analyst",
]


class UILogger:
    """
    Structured logging bridge that intercepts console.print() calls
    and routes them to appropriate TUI widgets.

    Usage:
        logger = UILogger()
        # Replace module consoles:
        some_module.console = logger
        # Register widget handlers:
        logger.on_agent_update = my_agent_widget.update
        logger.on_log = my_log_widget.write
        logger.on_cycle_metrics = my_summary_widget.update
    """

    def __init__(self):
        self._agents: dict[str, AgentInfo] = {
            name: AgentInfo(name=name) for name in TRACKED_AGENTS
        }
        self._current_cycle = CycleMetrics()
        self._last_cycle = CycleMetrics()

        # Callbacks — set by the TUI app
        self.on_agent_update: Optional[Callable[[str, AgentInfo], None]] = None
        self.on_log: Optional[Callable[[LogCategory, Any], None]] = None
        self.on_cycle_start: Optional[Callable[[int, str, str], None]] = None
        self.on_cycle_metrics: Optional[Callable[[CycleMetrics], None]] = None
        self.on_phase_change: Optional[Callable[[str], None]] = None

    @property
    def agents(self) -> dict[str, AgentInfo]:
        return self._agents

    @property
    def last_cycle(self) -> CycleMetrics:
        return self._last_cycle

    def reset_agents(self):
        """Reset all agents to idle at the start of a new cycle."""
        for agent in self._agents.values():
            agent.state = AgentState.IDLE
            agent.detail = ""
            agent.elapsed = 0.0

    def set_agent_state(self, name: str, state: AgentState, detail: str = ""):
        """Manually set an agent's state."""
        if name in self._agents:
            agent = self._agents[name]
            if state == AgentState.RUNNING:
                agent.start_time = time.time()
            elif state in (AgentState.DONE, AgentState.ERROR):
                if agent.start_time > 0:
                    agent.elapsed = time.time() - agent.start_time
            agent.state = state
            agent.detail = detail
            if self.on_agent_update:
                try:
                    self.on_agent_update(name, agent)
                except Exception:
                    pass

    def print(self, *objects, **kwargs):
        """
        Drop-in replacement for console.print().
        Classifies the message and routes to the appropriate handler.
        """
        for obj in objects:
            text = str(obj)
            category, agent_name = _classify_message(text)

            # Update agent state based on category
            if category == LogCategory.AGENT_START and agent_name:
                self.set_agent_state(agent_name, AgentState.RUNNING)
            elif category == LogCategory.AGENT_END and agent_name:
                # Extract detail from the message
                plain = re.sub(r"\[/?[^\]]*\]", "", text)
                self.set_agent_state(agent_name, AgentState.DONE, detail=plain.strip())
            elif category == LogCategory.ERROR:
                # Try to identify which agent errored
                plain = re.sub(r"\[/?[^\]]*\]", "", text)
                for name in TRACKED_AGENTS:
                    if name.lower() in plain.lower():
                        self.set_agent_state(name, AgentState.ERROR, detail=plain.strip()[:60])
                        break

            # Parse cycle summary metrics
            if category == LogCategory.CYCLE_SUMMARY:
                self._parse_cycle_summary(text)

            # Parse cycle header for cycle start
            if category == LogCategory.CYCLE_HEADER:
                self._parse_cycle_header(text)

            # Route to log widget — skip DEBUG by default
            if self.on_log and category != LogCategory.DEBUG:
                try:
                    self.on_log(category, obj)
                except Exception:
                    pass

    def _parse_cycle_header(self, text: str):
        """Extract cycle info from the cycle header Rule."""
        plain = re.sub(r"\[/?[^\]]*\]", "", text)
        m = re.search(r"Loop #(\d+)", plain)
        if m:
            iteration = int(m.group(1))
            self._current_cycle = CycleMetrics(iteration=iteration)
            self.reset_agents()

            state_m = re.search(r"state=(\w+)", plain)
            phase_m = re.search(r"phase=(.+?)(?:\s*$)", plain)
            state = state_m.group(1) if state_m else "normal"
            phase = phase_m.group(1).strip() if phase_m else ""

            if self.on_cycle_start:
                try:
                    self.on_cycle_start(iteration, phase, state)
                except Exception:
                    pass

    def _parse_cycle_summary(self, text: str):
        """Extract metrics from the cycle summary line."""
        plain = re.sub(r"\[/?[^\]]*\]", "", text)

        m = re.search(r"([\d,]+)\s*tok", plain)
        if m:
            self._current_cycle.total_tokens = int(m.group(1).replace(",", ""))

        m = re.search(r"↑([\d,]+)", plain)
        if m:
            self._current_cycle.prompt_tokens = int(m.group(1).replace(",", ""))

        m = re.search(r"↓([\d,]+)", plain)
        if m:
            self._current_cycle.completion_tokens = int(m.group(1).replace(",", ""))

        m = re.search(r"(\d+)\s*calls", plain)
        if m:
            self._current_cycle.llm_calls = int(m.group(1))

        m = re.search(r"⏱️\s*([\d.]+)s", plain)
        if m:
            self._current_cycle.cycle_time = float(m.group(1))

        m = re.search(r"📄\s*(\d+)\s*files", plain)
        if m:
            self._current_cycle.files_written = int(m.group(1))

        m = re.search(r"🧪\s*(\d+)/(\d+)", plain)
        if m:
            self._current_cycle.tests_passed = int(m.group(1))
            self._current_cycle.tests_total = int(m.group(2))

        m = re.search(r"⭐\s*([\d.]+)/10", plain)
        if m:
            self._current_cycle.review_score = float(m.group(1))

        # Finalize
        self._last_cycle = self._current_cycle
        if self.on_cycle_metrics:
            try:
                self.on_cycle_metrics(self._last_cycle)
            except Exception:
                pass
