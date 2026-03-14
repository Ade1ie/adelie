"""
adelie/loop_detector.py

Cycle-level loop detection for the Adelie orchestrator.
Detects when the AI agents are producing repetitive outputs
that indicate they're stuck, and provides escalating interventions.

Inspired by openclaw's tool-loop-detection.ts, adapted for
Adelie's cycle-based (not tool-call-based) architecture.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from rich.console import Console

console = Console()


# ── Detection Result ─────────────────────────────────────────────────────────


class LoopLevel(str, Enum):
    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class LoopDetectionResult:
    """Result of a loop detection check."""

    level: LoopLevel = LoopLevel.OK
    detector: str = ""
    count: int = 0
    message: str = ""

    @property
    def stuck(self) -> bool:
        return self.level != LoopLevel.OK


# ── Configuration ────────────────────────────────────────────────────────────


@dataclass
class LoopDetectorConfig:
    """Tunable thresholds for loop detection."""

    # How many recent cycles to track
    history_size: int = 20

    # Expert AI: consecutive identical decisions
    expert_warning_threshold: int = 3
    expert_critical_threshold: int = 5

    # Writer AI: consecutive cycles writing the same files
    writer_warning_threshold: int = 3
    writer_critical_threshold: int = 5

    # State: consecutive cycles in the same state without progress
    state_warning_threshold: int = 5
    state_critical_threshold: int = 8

    # Ping-pong: alternating between two states
    pingpong_warning_threshold: int = 4
    pingpong_critical_threshold: int = 6

    # No-progress: consecutive cycles with identical result content
    # (openclaw pattern: hash input + output to detect true stagnation)
    no_progress_warning_threshold: int = 4
    no_progress_critical_threshold: int = 7


DEFAULT_CONFIG = LoopDetectorConfig()


# ── Cycle Record ─────────────────────────────────────────────────────────────


@dataclass
class CycleRecord:
    """Snapshot of one orchestrator cycle for pattern matching."""

    iteration: int
    timestamp: float
    state: str  # LoopState value
    expert_hash: str  # Hash of expert AI decision (structural)
    expert_action: str  # Action type (CONTINUE, NEW_LOGIC, etc.)
    expert_next_situation: str  # Next situation from expert
    writer_hash: str  # Hash of writer AI output (files written)
    kb_file_count: int  # Total KB files at end of cycle
    expert_result_hash: str = ""  # Hash of full Expert AI result content (for no-progress detection)


# ── Fingerprinting ───────────────────────────────────────────────────────────


def _stable_hash(data: Any) -> str:
    """Create a stable hash of structured data for comparison."""
    try:
        serialized = json.dumps(data, sort_keys=True, default=str)
    except (TypeError, ValueError):
        serialized = str(data)
    return hashlib.sha256(serialized.encode()).hexdigest()[:16]


def fingerprint_expert_output(decision: dict | None) -> str:
    """
    Create a fingerprint of expert AI output for repetition detection.
    Focuses on the structural decision, ignoring volatile fields like reasoning text.
    """
    if not decision:
        return "empty"

    # Extract the decision-relevant fields (not reasoning text, which varies)
    key_fields = {
        "action": decision.get("action", ""),
        "next_situation": decision.get("next_situation", ""),
        "commands": sorted(decision.get("commands", [])),
        "coder_tasks_count": len(decision.get("coder_tasks", [])),
        "kb_updates_needed": sorted(
            [u.get("filename", "") for u in decision.get("kb_updates_needed", [])
             if isinstance(u, dict)]
        ),
    }
    return _stable_hash(key_fields)


def fingerprint_expert_result(decision: dict | None) -> str:
    """
    Create a fingerprint of the FULL expert AI result content.
    Unlike fingerprint_expert_output (structural only), this includes
    the actual content of commands, coder tasks, and KB updates —
    detecting 'no progress' even when the action type stays the same.

    Inspired by openclaw's hashToolOutcome — hashing both input and output.
    """
    if not decision:
        return "empty"

    # Include everything except volatile reasoning text
    result_fields = {
        "action": decision.get("action", ""),
        "next_situation": decision.get("next_situation", ""),
        "commands": sorted(decision.get("commands", [])),
        "coder_tasks": sorted(
            [
                {"name": t.get("name", ""), "layer": t.get("layer", 0), "task": t.get("task", "")}
                for t in decision.get("coder_tasks", [])
                if isinstance(t, dict)
            ],
            key=lambda t: t.get("name", ""),
        ),
        "kb_updates_needed": sorted(
            [
                {"filename": u.get("filename", ""), "content_hint": u.get("content", "")[:100]}
                for u in decision.get("kb_updates_needed", [])
                if isinstance(u, dict)
            ],
            key=lambda u: u.get("filename", ""),
        ),
        "suggested_phase": decision.get("suggested_phase", ""),
    }
    return _stable_hash(result_fields)


def fingerprint_writer_output(written_files: list[dict] | None) -> str:
    """Create a fingerprint of writer AI output (which files were written)."""
    if not written_files:
        return "empty"
    paths = sorted(f.get("path", "") for f in written_files if isinstance(f, dict))
    return _stable_hash(paths)


# ── Loop Detector ────────────────────────────────────────────────────────────


class LoopDetector:
    """
    Tracks orchestrator cycle history and detects stuck patterns.

    Usage:
        detector = LoopDetector()
        # After each cycle:
        detector.record_cycle(iteration, state, expert_output, writer_output, kb_count)
        result = detector.check()
        if result.stuck:
            # Handle: inject intervention, force state change, etc.
    """

    def __init__(self, config: LoopDetectorConfig | None = None):
        self.config = config or DEFAULT_CONFIG
        self._history: deque[CycleRecord] = deque(maxlen=self.config.history_size)
        self._interventions_given: int = 0
        self._last_warning_key: str = ""  # Dedup: suppress identical consecutive warnings

    def record_cycle(
        self,
        iteration: int,
        state: str,
        expert_output: dict | None,
        writer_output: list[dict] | None = None,
        kb_file_count: int = 0,
    ) -> None:
        """Record one completed cycle for pattern analysis."""
        record = CycleRecord(
            iteration=iteration,
            timestamp=time.time(),
            state=state,
            expert_hash=fingerprint_expert_output(expert_output),
            expert_action=expert_output.get("action", "") if expert_output else "",
            expert_next_situation=expert_output.get("next_situation", "") if expert_output else "",
            writer_hash=fingerprint_writer_output(writer_output),
            kb_file_count=kb_file_count,
            expert_result_hash=fingerprint_expert_result(expert_output),
        )
        self._history.append(record)

    def check(self) -> LoopDetectionResult:
        """
        Run all detectors against current history.
        Returns the most severe result found.
        Deduplicates: if the same warning_key fires twice in a row,
        the second is suppressed (returns OK).
        """
        if len(self._history) < 2:
            return LoopDetectionResult()

        detectors = [
            self._detect_no_progress,
            self._detect_expert_repetition,
            self._detect_state_stagnation,
            self._detect_pingpong,
            self._detect_writer_repetition,
        ]

        worst = LoopDetectionResult()
        for detect_fn in detectors:
            result = detect_fn()
            if result.stuck and (
                not worst.stuck
                or (result.level == LoopLevel.CRITICAL and worst.level != LoopLevel.CRITICAL)
                or (result.count > worst.count and result.level == worst.level)
            ):
                worst = result

        # Warning dedup: suppress identical consecutive warnings
        if worst.stuck:
            warning_key = f"{worst.detector}:{worst.level.value}:{worst.count}"
            if warning_key == self._last_warning_key:
                return LoopDetectionResult()  # Suppress duplicate
            self._last_warning_key = warning_key
        else:
            self._last_warning_key = ""  # Reset on OK

        return worst

    def get_intervention_prompt(self, result: LoopDetectionResult) -> str:
        """
        Generate a prompt injection to break the AI out of a loop.
        This gets prepended to the Expert AI's next prompt.
        """
        self._interventions_given += 1

        if result.level == LoopLevel.CRITICAL:
            return (
                "\n\n⚠️ CRITICAL SYSTEM ALERT — LOOP DETECTED ⚠️\n"
                f"The system has detected a stuck loop: {result.message}\n"
                "You MUST take a DIFFERENT action from your previous responses.\n"
                "If you've been returning the same action, try a completely different approach.\n"
                "If stuck in 'new_logic', transition to 'normal'.\n"
                "If stuck in 'error', transition to 'normal' and archive errors.\n"
                "DO NOT repeat your previous decision.\n"
            )
        else:
            return (
                "\n\n⚠️ WARNING — Repetitive pattern detected ⚠️\n"
                f"{result.message}\n"
                "Consider changing your approach or action.\n"
            )

    @property
    def interventions_given(self) -> int:
        return self._interventions_given

    @property
    def history_length(self) -> int:
        return len(self._history)

    def get_stats(self) -> dict:
        """Return current detection statistics for debugging."""
        if not self._history:
            return {"cycles_tracked": 0}

        history = list(self._history)
        actions = [r.expert_action for r in history]
        states = [r.state for r in history]

        return {
            "cycles_tracked": len(history),
            "interventions_given": self._interventions_given,
            "recent_actions": actions[-5:],
            "recent_states": states[-5:],
            "unique_expert_hashes": len(set(r.expert_hash for r in history)),
            "unique_writer_hashes": len(set(r.writer_hash for r in history)),
        }

    def reset(self) -> None:
        """Clear all history (e.g., after a successful state change)."""
        self._history.clear()
        self._interventions_given = 0
        self._last_warning_key = ""

    # ── Detectors ────────────────────────────────────────────────────────────

    def _detect_no_progress(self) -> LoopDetectionResult:
        """
        Detect when Expert AI returns identical FULL results consecutively.
        Unlike expert_repetition (structural decision hash), this hashes the
        actual content — commands, coder tasks, KB updates. Catches cases where
        the agent picks the same action with the same content each cycle.

        Inspired by openclaw's hashToolOutcome + getNoProgressStreak.
        """
        history = list(self._history)
        if len(history) < 3:
            return LoopDetectionResult()

        latest_hash = history[-1].expert_result_hash
        if latest_hash == "empty":
            return LoopDetectionResult()

        streak = 0
        for record in reversed(history):
            if record.expert_result_hash == latest_hash:
                streak += 1
            else:
                break

        if streak >= self.config.no_progress_critical_threshold:
            return LoopDetectionResult(
                level=LoopLevel.CRITICAL,
                detector="no_progress",
                count=streak,
                message=(
                    f"CIRCUIT BREAKER: Expert AI has produced identical results "
                    f"for {streak} consecutive cycles with no progress. "
                    f"The system is stuck in an infinite loop. "
                    f"Forcing a completely different approach."
                ),
            )

        if streak >= self.config.no_progress_warning_threshold:
            return LoopDetectionResult(
                level=LoopLevel.WARNING,
                detector="no_progress",
                count=streak,
                message=(
                    f"Expert AI has produced the same full result {streak} times. "
                    f"No actual progress is being made. Try a different approach."
                ),
            )

        return LoopDetectionResult()

    def _detect_expert_repetition(self) -> LoopDetectionResult:
        """Detect when Expert AI returns identical decisions consecutively."""
        history = list(self._history)
        if len(history) < 2:
            return LoopDetectionResult()

        latest_hash = history[-1].expert_hash
        streak = 0
        for record in reversed(history):
            if record.expert_hash == latest_hash:
                streak += 1
            else:
                break

        if streak >= self.config.expert_critical_threshold:
            return LoopDetectionResult(
                level=LoopLevel.CRITICAL,
                detector="expert_repetition",
                count=streak,
                message=(
                    f"Expert AI has returned identical decisions for {streak} "
                    f"consecutive cycles (action: {history[-1].expert_action}, "
                    f"next: {history[-1].expert_next_situation}). "
                    f"The system appears stuck."
                ),
            )

        if streak >= self.config.expert_warning_threshold:
            return LoopDetectionResult(
                level=LoopLevel.WARNING,
                detector="expert_repetition",
                count=streak,
                message=(
                    f"Expert AI has returned the same decision {streak} times "
                    f"(action: {history[-1].expert_action}). "
                    f"Consider varying your approach."
                ),
            )

        return LoopDetectionResult()

    def _detect_state_stagnation(self) -> LoopDetectionResult:
        """Detect when the orchestrator stays in the same state without KB growth."""
        history = list(self._history)
        if len(history) < 3:
            return LoopDetectionResult()

        latest_state = history[-1].state
        latest_kb = history[-1].kb_file_count
        streak = 0

        for record in reversed(history):
            if record.state == latest_state and record.kb_file_count == latest_kb:
                streak += 1
            else:
                break

        if streak >= self.config.state_critical_threshold:
            return LoopDetectionResult(
                level=LoopLevel.CRITICAL,
                detector="state_stagnation",
                count=streak,
                message=(
                    f"System has been in '{latest_state}' state for {streak} cycles "
                    f"with no KB growth (stuck at {latest_kb} files). "
                    f"The loop is not making progress."
                ),
            )

        if streak >= self.config.state_warning_threshold:
            return LoopDetectionResult(
                level=LoopLevel.WARNING,
                detector="state_stagnation",
                count=streak,
                message=(
                    f"System has been in '{latest_state}' state for {streak} cycles "
                    f"with no KB growth. Consider changing approach."
                ),
            )

        return LoopDetectionResult()

    def _detect_pingpong(self) -> LoopDetectionResult:
        """Detect alternating state patterns (A→B→A→B)."""
        history = list(self._history)
        if len(history) < 4:
            return LoopDetectionResult()

        # Check for alternating pattern in states
        states = [r.state for r in history]
        alternating_count = self._count_alternating_tail(states)

        if alternating_count >= self.config.pingpong_critical_threshold:
            last_two = states[-2:]
            return LoopDetectionResult(
                level=LoopLevel.CRITICAL,
                detector="pingpong",
                count=alternating_count,
                message=(
                    f"System is ping-ponging between states "
                    f"'{last_two[0]}' and '{last_two[1]}' "
                    f"({alternating_count} alternations). Breaking the cycle."
                ),
            )

        if alternating_count >= self.config.pingpong_warning_threshold:
            last_two = states[-2:]
            return LoopDetectionResult(
                level=LoopLevel.WARNING,
                detector="pingpong",
                count=alternating_count,
                message=(
                    f"Possible ping-pong between '{last_two[0]}' and '{last_two[1]}' "
                    f"({alternating_count} alternations)."
                ),
            )

        return LoopDetectionResult()

    def _detect_writer_repetition(self) -> LoopDetectionResult:
        """Detect when Writer AI keeps writing the same files."""
        history = list(self._history)
        if len(history) < 2:
            return LoopDetectionResult()

        latest_hash = history[-1].writer_hash
        if latest_hash == "empty":
            return LoopDetectionResult()

        streak = 0
        for record in reversed(history):
            if record.writer_hash == latest_hash:
                streak += 1
            else:
                break

        if streak >= self.config.writer_critical_threshold:
            return LoopDetectionResult(
                level=LoopLevel.CRITICAL,
                detector="writer_repetition",
                count=streak,
                message=(
                    f"Writer AI has written identical files for {streak} "
                    f"consecutive cycles. The content generation is stuck."
                ),
            )

        if streak >= self.config.writer_warning_threshold:
            return LoopDetectionResult(
                level=LoopLevel.WARNING,
                detector="writer_repetition",
                count=streak,
                message=(
                    f"Writer AI has written the same files {streak} times. "
                    f"Consider requesting different content."
                ),
            )

        return LoopDetectionResult()

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _count_alternating_tail(values: list[str]) -> int:
        """Count how many values at the end form an alternating A-B-A-B pattern."""
        if len(values) < 2:
            return 0

        a = values[-1]
        b = values[-2]
        if a == b:
            return 0

        count = 0
        for i in range(len(values) - 1, -1, -1):
            expected = a if count % 2 == 0 else b
            if values[i] != expected:
                break
            count += 1

        return count if count >= 2 else 0
