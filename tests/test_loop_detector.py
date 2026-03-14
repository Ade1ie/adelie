"""tests/test_loop_detector.py — Tests for cycle-level loop detection."""
from __future__ import annotations

import pytest

from adelie.loop_detector import (
    LoopDetector,
    LoopDetectorConfig,
    LoopLevel,
    fingerprint_expert_output,
    fingerprint_expert_result,
    fingerprint_writer_output,
)


# ── Fingerprinting ──────────────────────────────────────────────────────────


class TestFingerprinting:
    def test_expert_same_decision_same_hash(self):
        d1 = {"action": "CONTINUE", "next_situation": "normal", "commands": ["a", "b"]}
        d2 = {"action": "CONTINUE", "next_situation": "normal", "commands": ["b", "a"]}
        assert fingerprint_expert_output(d1) == fingerprint_expert_output(d2)

    def test_expert_different_action_different_hash(self):
        d1 = {"action": "CONTINUE", "next_situation": "normal"}
        d2 = {"action": "NEW_LOGIC", "next_situation": "new_logic"}
        assert fingerprint_expert_output(d1) != fingerprint_expert_output(d2)

    def test_expert_ignores_reasoning_text(self):
        d1 = {"action": "CONTINUE", "next_situation": "normal", "reasoning": "reason A"}
        d2 = {"action": "CONTINUE", "next_situation": "normal", "reasoning": "reason B"}
        assert fingerprint_expert_output(d1) == fingerprint_expert_output(d2)

    def test_expert_none_returns_empty(self):
        assert fingerprint_expert_output(None) == "empty"

    def test_writer_same_files_same_hash(self):
        w1 = [{"path": "skills/a.md"}, {"path": "logic/b.md"}]
        w2 = [{"path": "logic/b.md"}, {"path": "skills/a.md"}]
        assert fingerprint_writer_output(w1) == fingerprint_writer_output(w2)

    def test_writer_none_returns_empty(self):
        assert fingerprint_writer_output(None) == "empty"


# ── Expert Result Fingerprinting (full content hash) ────────────────────────


class TestFingerprintExpertResult:
    def test_same_full_result_same_hash(self):
        d1 = {"action": "CONTINUE", "next_situation": "normal", "commands": ["a"],
               "coder_tasks": [{"name": "t1", "layer": 0, "task": "do X"}]}
        d2 = {"action": "CONTINUE", "next_situation": "normal", "commands": ["a"],
               "coder_tasks": [{"name": "t1", "layer": 0, "task": "do X"}]}
        assert fingerprint_expert_result(d1) == fingerprint_expert_result(d2)

    def test_different_task_content_different_hash(self):
        """Same action/structure but different coder task content → different hash."""
        d1 = {"action": "CONTINUE", "next_situation": "normal",
               "coder_tasks": [{"name": "t1", "layer": 0, "task": "implement feature A"}]}
        d2 = {"action": "CONTINUE", "next_situation": "normal",
               "coder_tasks": [{"name": "t1", "layer": 0, "task": "implement feature B"}]}
        assert fingerprint_expert_result(d1) != fingerprint_expert_result(d2)

    def test_structural_hash_ignores_task_content(self):
        """fingerprint_expert_output should NOT distinguish task content."""
        d1 = {"action": "CONTINUE", "next_situation": "normal",
               "coder_tasks": [{"name": "t1", "layer": 0, "task": "implement feature A"}]}
        d2 = {"action": "CONTINUE", "next_situation": "normal",
               "coder_tasks": [{"name": "t1", "layer": 0, "task": "implement feature B"}]}
        # Structural fingerprint treats these as same (same count)
        assert fingerprint_expert_output(d1) == fingerprint_expert_output(d2)

    def test_result_hash_ignores_reasoning(self):
        d1 = {"action": "CONTINUE", "reasoning": "reason A", "commands": ["x"]}
        d2 = {"action": "CONTINUE", "reasoning": "reason B", "commands": ["x"]}
        assert fingerprint_expert_result(d1) == fingerprint_expert_result(d2)

    def test_none_returns_empty(self):
        assert fingerprint_expert_result(None) == "empty"


# ── Expert Repetition Detection ─────────────────────────────────────────────


class TestExpertRepetition:
    def test_no_repetition(self):
        detector = LoopDetector(LoopDetectorConfig(expert_warning_threshold=3))
        for i in range(3):
            detector.record_cycle(i, "normal", {"action": f"ACTION_{i}", "next_situation": "normal"})
        result = detector.check()
        assert not result.stuck

    def test_warning_on_repeated_decisions(self):
        cfg = LoopDetectorConfig(expert_warning_threshold=3, expert_critical_threshold=5)
        detector = LoopDetector(cfg)
        decision = {"action": "CONTINUE", "next_situation": "normal", "commands": ["x"]}
        for i in range(3):
            detector.record_cycle(i, "normal", decision)
        result = detector.check()
        assert result.stuck
        assert result.level == LoopLevel.WARNING
        assert result.detector == "expert_repetition"

    def test_critical_on_many_repeated_decisions(self):
        cfg = LoopDetectorConfig(expert_warning_threshold=3, expert_critical_threshold=5)
        detector = LoopDetector(cfg)
        decision = {"action": "CONTINUE", "next_situation": "normal", "commands": ["x"]}
        for i in range(5):
            detector.record_cycle(i, "normal", decision)
        result = detector.check()
        assert result.stuck
        assert result.level == LoopLevel.CRITICAL

    def test_streak_broken_by_different_decision(self):
        cfg = LoopDetectorConfig(expert_warning_threshold=3, state_warning_threshold=99)
        detector = LoopDetector(cfg)
        # 2 same, 1 different, 2 same = streak of 2 (below threshold)
        detector.record_cycle(1, "normal", {"action": "CONTINUE", "next_situation": "normal"}, kb_file_count=1)
        detector.record_cycle(2, "normal", {"action": "CONTINUE", "next_situation": "normal"}, kb_file_count=2)
        detector.record_cycle(3, "normal", {"action": "RECOVER", "next_situation": "error"}, kb_file_count=3)
        detector.record_cycle(4, "normal", {"action": "CONTINUE", "next_situation": "normal"}, kb_file_count=4)
        detector.record_cycle(5, "normal", {"action": "CONTINUE", "next_situation": "normal"}, kb_file_count=5)
        result = detector.check()
        assert not result.stuck


# ── No-Progress Detection ───────────────────────────────────────────────────


class TestNoProgress:
    def test_no_progress_detected(self):
        """Identical full results for N cycles → no-progress warning."""
        cfg = LoopDetectorConfig(no_progress_warning_threshold=4, no_progress_critical_threshold=7,
                                  expert_warning_threshold=99, expert_critical_threshold=99)
        detector = LoopDetector(cfg)
        decision = {"action": "CONTINUE", "next_situation": "normal",
                     "commands": ["build"], "coder_tasks": [{"name": "t1", "layer": 0, "task": "same task"}]}
        for i in range(4):
            detector.record_cycle(i, "normal", decision, kb_file_count=i)
        result = detector.check()
        assert result.stuck
        assert result.detector == "no_progress"
        assert result.level == LoopLevel.WARNING

    def test_no_progress_critical_circuit_breaker(self):
        """After many identical results → circuit breaker fires."""
        cfg = LoopDetectorConfig(no_progress_warning_threshold=4, no_progress_critical_threshold=7,
                                  expert_warning_threshold=99, expert_critical_threshold=99)
        detector = LoopDetector(cfg)
        decision = {"action": "CONTINUE", "commands": ["x"],
                     "coder_tasks": [{"name": "t", "layer": 0, "task": "same"}]}
        for i in range(7):
            detector.record_cycle(i, "normal", decision, kb_file_count=i)
            detector.check()  # consume dedup
        result = detector.check()
        # After dedup consumed, re-record to get fresh check
        detector.record_cycle(8, "normal", decision, kb_file_count=8)
        result = detector.check()
        assert result.stuck
        assert result.level == LoopLevel.CRITICAL
        assert "CIRCUIT BREAKER" in result.message

    def test_different_results_no_detection(self):
        """When results differ each cycle, no-progress should NOT fire."""
        cfg = LoopDetectorConfig(no_progress_warning_threshold=3, no_progress_critical_threshold=5)
        detector = LoopDetector(cfg)
        for i in range(5):
            decision = {"action": "CONTINUE", "commands": [f"cmd_{i}"],
                         "coder_tasks": [{"name": f"task_{i}", "layer": 0, "task": f"do thing {i}"}]}
            detector.record_cycle(i, "normal", decision, kb_file_count=i)
        result = detector.check()
        assert result.detector != "no_progress" or not result.stuck


# ── Warning Dedup ────────────────────────────────────────────────────────────


class TestWarningDedup:
    def test_same_warning_suppressed(self):
        """Identical warning fired twice in a row → second is suppressed."""
        cfg = LoopDetectorConfig(expert_warning_threshold=2, expert_critical_threshold=99)
        detector = LoopDetector(cfg)
        decision = {"action": "CONTINUE", "next_situation": "normal"}
        detector.record_cycle(1, "normal", decision)
        detector.record_cycle(2, "normal", decision)

        result1 = detector.check()
        assert result1.stuck  # First warning fires

        # Same state, calling check again without new data
        result2 = detector.check()
        assert not result2.stuck  # Should be suppressed

    def test_different_warning_not_suppressed(self):
        """Warnings with different keys are NOT suppressed."""
        cfg = LoopDetectorConfig(expert_warning_threshold=2, expert_critical_threshold=99,
                                  state_warning_threshold=99)
        detector = LoopDetector(cfg)
        decision = {"action": "CONTINUE", "next_situation": "normal"}
        detector.record_cycle(1, "normal", decision)
        detector.record_cycle(2, "normal", decision)

        result1 = detector.check()
        assert result1.stuck

        # Add one more cycle — count changes, so warning key changes
        detector.record_cycle(3, "normal", decision)
        result2 = detector.check()
        assert result2.stuck  # Different count → new warning key

    def test_dedup_resets_on_ok(self):
        """After a non-stuck check, dedup resets."""
        cfg = LoopDetectorConfig(expert_warning_threshold=2, expert_critical_threshold=99,
                                  state_warning_threshold=99)
        detector = LoopDetector(cfg)
        decision = {"action": "CONTINUE", "next_situation": "normal"}
        detector.record_cycle(1, "normal", decision)
        detector.record_cycle(2, "normal", decision)

        result1 = detector.check()
        assert result1.stuck

        # Break the streak
        detector.record_cycle(3, "normal", {"action": "DIFFERENT", "next_situation": "new"}, kb_file_count=1)
        result2 = detector.check()
        assert not result2.stuck  # OK resets dedup

        # Start same streak again
        detector.record_cycle(4, "normal", decision)
        detector.record_cycle(5, "normal", decision)
        result3 = detector.check()
        assert result3.stuck  # Can fire again after reset


# ── State Stagnation Detection ──────────────────────────────────────────────


class TestStateStagnation:
    def test_no_stagnation_with_kb_growth(self):
        cfg = LoopDetectorConfig(state_warning_threshold=3, expert_warning_threshold=99, expert_critical_threshold=99,
                                  no_progress_warning_threshold=99, no_progress_critical_threshold=99)
        detector = LoopDetector(cfg)
        for i in range(5):
            detector.record_cycle(i, "normal", {"action": "CONTINUE", "next_situation": "normal"}, kb_file_count=i + 1)
        result = detector.check()
        # Different kb_file_count each time → not stagnating
        assert not result.stuck

    def test_stagnation_detected(self):
        cfg = LoopDetectorConfig(state_warning_threshold=3, state_critical_threshold=6)
        detector = LoopDetector(cfg)
        for i in range(4):
            detector.record_cycle(i, "new_logic", {"action": f"A{i}", "next_situation": "new_logic"}, kb_file_count=0)
        result = detector.check()
        assert result.stuck
        assert result.detector == "state_stagnation"


# ── Ping-Pong Detection ─────────────────────────────────────────────────────


class TestPingPong:
    def test_detects_alternating_states(self):
        cfg = LoopDetectorConfig(pingpong_warning_threshold=4)
        detector = LoopDetector(cfg)
        states = ["normal", "error", "normal", "error", "normal", "error"]
        for i, state in enumerate(states):
            detector.record_cycle(i, state, {"action": f"A{i}", "next_situation": state})
        result = detector.check()
        assert result.stuck
        assert result.detector == "pingpong"

    def test_no_pingpong_with_same_state(self):
        cfg = LoopDetectorConfig(pingpong_warning_threshold=4)
        detector = LoopDetector(cfg)
        for i in range(6):
            detector.record_cycle(i, "normal", {"action": f"A{i}", "next_situation": "normal"})
        # Same state → not ping-pong
        result = detector.check()
        assert result.detector != "pingpong" or not result.stuck


# ── Writer Repetition Detection ─────────────────────────────────────────────


class TestWriterRepetition:
    def test_detects_repeated_writes(self):
        cfg = LoopDetectorConfig(writer_warning_threshold=3)
        detector = LoopDetector(cfg)
        same_output = [{"path": "skills/a.md"}, {"path": "logic/b.md"}]
        for i in range(3):
            detector.record_cycle(i, "normal", {"action": f"A{i}", "next_situation": "normal"}, writer_output=same_output, kb_file_count=i)
        result = detector.check()
        assert result.stuck
        assert result.detector == "writer_repetition"

    def test_no_detection_on_empty_writes(self):
        cfg = LoopDetectorConfig(writer_warning_threshold=3)
        detector = LoopDetector(cfg)
        for i in range(5):
            detector.record_cycle(i, "normal", {"action": f"A{i}", "next_situation": "normal"}, writer_output=None, kb_file_count=i)
        result = detector.check()
        assert result.detector != "writer_repetition" or not result.stuck


# ── Intervention Prompt ──────────────────────────────────────────────────────


class TestIntervention:
    def test_warning_prompt(self):
        cfg = LoopDetectorConfig(expert_warning_threshold=2)
        detector = LoopDetector(cfg)
        decision = {"action": "CONTINUE", "next_situation": "normal"}
        for i in range(2):
            detector.record_cycle(i, "normal", decision)
        result = detector.check()
        prompt = detector.get_intervention_prompt(result)
        assert "WARNING" in prompt
        assert detector.interventions_given == 1

    def test_critical_prompt(self):
        cfg = LoopDetectorConfig(expert_warning_threshold=2, expert_critical_threshold=3)
        detector = LoopDetector(cfg)
        decision = {"action": "CONTINUE", "next_situation": "normal"}
        for i in range(3):
            detector.record_cycle(i, "normal", decision)
        result = detector.check()
        prompt = detector.get_intervention_prompt(result)
        assert "CRITICAL" in prompt
        assert "MUST" in prompt


# ── Stats & Reset ────────────────────────────────────────────────────────────


class TestStatsAndReset:
    def test_stats(self):
        detector = LoopDetector()
        detector.record_cycle(1, "normal", {"action": "CONTINUE", "next_situation": "normal"})
        detector.record_cycle(2, "normal", {"action": "CONTINUE", "next_situation": "normal"})
        stats = detector.get_stats()
        assert stats["cycles_tracked"] == 2

    def test_reset(self):
        detector = LoopDetector()
        detector.record_cycle(1, "normal", {"action": "CONTINUE", "next_situation": "normal"})
        detector.reset()
        assert detector.history_length == 0
