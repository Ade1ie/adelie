"""tests/test_context_compactor.py — Tests for context compaction."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from adelie.context_compactor import (
    CycleHistory,
    ContextBudget,
    SAFETY_MARGIN,
    compact_expert_output,
    compact_kb_content,
    compact_system_state,
    estimate_tokens,
    summarize_with_llm,
    truncate_to_budget,
)


class TestTokenEstimation:
    def test_basic_estimate(self):
        assert estimate_tokens("abcd") == 1
        assert estimate_tokens("a" * 400) == 100

    def test_empty_returns_one(self):
        assert estimate_tokens("") == 1

    def test_safe_mode_applies_margin(self):
        raw = estimate_tokens("a" * 400)
        safe = estimate_tokens("a" * 400, safe=True)
        assert safe > raw
        assert safe == int(raw * SAFETY_MARGIN)

    def test_safe_mode_on_short_text(self):
        raw = estimate_tokens("hello")
        safe = estimate_tokens("hello", safe=True)
        assert safe >= raw


class TestTruncateToBudget:
    def test_no_truncation_if_within_budget(self):
        text = "short text"
        result = truncate_to_budget(text, 100)
        assert result == text

    def test_truncation_adds_note(self):
        text = "x" * 10000
        result = truncate_to_budget(text, 100)
        assert "truncated" in result
        assert len(result) < len(text)

    def test_safety_margin_causes_earlier_truncation(self):
        """With margin, text that's borderline over budget gets truncated."""
        # 400 chars = 100 raw tokens, but 120 safe tokens
        text = "a" * 400
        # Budget = 105: raw says OK (100 < 105), but safe says truncate (120 > 105)
        result = truncate_to_budget(text, 105)
        assert "truncated" in result


class TestCycleHistory:
    def test_records_and_returns_context(self):
        history = CycleHistory(detail_window=3)
        history.record(1, "normal", {"action": "CONTINUE", "reasoning": "test"}, files_written=1, kb_total=5)
        ctx = history.get_context()
        assert "Loop #1" in ctx
        assert "CONTINUE" in ctx

    def test_compresses_old_cycles(self):
        history = CycleHistory(detail_window=2, max_summary_tokens=500)
        for i in range(5):
            history.record(i + 1, "normal", {"action": "CONTINUE", "reasoning": f"round {i}"})
        ctx = history.get_context()
        # Should have prior history section + recent section
        assert "Prior History" in ctx
        assert "Recent Cycles" in ctx
        # Only last 2 should be in recent
        assert "Loop #5" in ctx
        assert "Loop #4" in ctx

    def test_total_cycles_tracked(self):
        history = CycleHistory(detail_window=2)
        for i in range(10):
            history.record(i, "normal", {"action": "A"})
        assert history.total_cycles == 10

    def test_reset_clears_everything(self):
        history = CycleHistory()
        history.record(1, "normal", {"action": "A"})
        history.reset()
        assert history.total_cycles == 0
        assert history.get_context() == ""


class TestCompactSystemState:
    def test_small_state_passes_through(self):
        state = {"goal": "test", "phase": "initial", "situation": "normal"}
        result = compact_system_state(state, 1000)
        assert "test" in result

    def test_large_state_trims_project_tree(self):
        state = {
            "goal": "test",
            "project_tree": "file1\n" * 2000,
            "source_stats": {"files": 100},
        }
        result = compact_system_state(state, 200)
        # Should be truncated
        assert estimate_tokens(result) <= 250  # some margin


class TestCompactKBContent:
    def test_small_content_passes_through(self):
        content = "## File A\nSome content"
        result = compact_kb_content(content, 1000)
        assert result == content

    def test_large_content_truncates_sections(self):
        sections = [f"## Section {i}\n{'content ' * 200}" for i in range(10)]
        content = "\n---\n".join(sections)
        result = compact_kb_content(content, 500)
        assert "omitted" in result
        assert estimate_tokens(result) < estimate_tokens(content)


class TestCompactExpertOutput:
    def test_none_returns_first_run(self):
        result = compact_expert_output(None, 1000)
        assert "first run" in result

    def test_small_output_passes_through(self):
        output = {"action": "CONTINUE", "reasoning": "all good"}
        result = compact_expert_output(output, 1000)
        assert "CONTINUE" in result

    def test_large_output_truncates(self):
        output = {
            "action": "CONTINUE",
            "reasoning": "x" * 5000,
            "commands": [f"cmd{i}" for i in range(20)],
            "coder_tasks": [{"name": f"t{i}", "layer": 0, "task": "x" * 500} for i in range(10)],
        }
        result = compact_expert_output(output, 200)
        assert estimate_tokens(result) < 300


class TestSummarizeWithLLM:
    def test_short_text_passes_through(self):
        """If text is already within budget, return as-is."""
        short = "Cycles 1-5: all normal, KB grew from 0 to 5 files."
        result = summarize_with_llm(short, max_tokens=500)
        assert result == short

    def test_fallback_on_no_api(self):
        """When LLM fails, falls back to truncation."""
        long_text = "cycle data\n" * 1000  # Very long history
        with patch("adelie.llm_client.generate", side_effect=RuntimeError("No API key")):
            result = summarize_with_llm(long_text, max_tokens=50)
        # Should not raise, should return truncated text
        assert len(result) < len(long_text)
        assert "truncated" in result
