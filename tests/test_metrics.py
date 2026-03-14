"""tests/test_metrics.py — Tests for persistent metrics recording and analysis."""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from adelie.metrics import (
    record_cycle,
    read_cycles,
    summary_table,
    agent_summary_table,
    trend_summary,
    get_stats_summary,
)


@pytest.fixture
def temp_metrics_dir(tmp_path):
    """Redirect metrics to a temp directory."""
    import adelie.metrics as m
    old_fn = m._get_metrics_dir

    def _mock_dir():
        d = tmp_path / "metrics"
        d.mkdir(exist_ok=True)
        return d

    m._get_metrics_dir = _mock_dir
    yield tmp_path / "metrics"
    m._get_metrics_dir = old_fn


class TestRecordCycle:
    def test_creates_jsonl_file(self, temp_metrics_dir):
        record_cycle(
            iteration=1,
            phase="initial",
            state="normal",
            cycle_time=5.0,
            agent_metrics={"writer": {"tokens": 100, "calls": 1}},
            token_usage={"prompt_tokens": 500, "completion_tokens": 200, "total_tokens": 700, "calls": 2},
            loop_metrics={"files_written": 0, "tests_passed": 0, "tests_total": 0, "review_scores": [], "parallel_phases": []},
        )

        cycles_file = temp_metrics_dir / "cycles.jsonl"
        assert cycles_file.exists()
        lines = cycles_file.read_text().strip().split("\n")
        assert len(lines) == 1

        record = json.loads(lines[0])
        assert record["cycle"] == 1
        assert record["phase"] == "initial"
        assert record["cycle_time"] == 5.0
        assert record["tokens"]["total"] == 700

    def test_appends_multiple_records(self, temp_metrics_dir):
        for i in range(3):
            record_cycle(
                iteration=i + 1,
                phase="mid",
                state="normal",
                cycle_time=10.0 + i,
                agent_metrics={},
                token_usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "calls": 0},
                loop_metrics={"files_written": 0, "tests_passed": 0, "tests_total": 0, "review_scores": [], "parallel_phases": []},
            )

        records = read_cycles()
        assert len(records) == 3
        assert records[0]["cycle"] == 1
        assert records[2]["cycle"] == 3

    def test_records_agent_metrics(self, temp_metrics_dir):
        record_cycle(
            iteration=1,
            phase="mid",
            state="normal",
            cycle_time=8.0,
            agent_metrics={
                "writer": {"tokens": 3000, "calls": 1},
                "expert": {"tokens": 4500, "calls": 1},
                "coder": {"tokens": 2000, "calls": 2},
            },
            token_usage={"prompt_tokens": 6000, "completion_tokens": 3500, "total_tokens": 9500, "calls": 4},
            loop_metrics={"files_written": 2, "tests_passed": 0, "tests_total": 0, "review_scores": [], "parallel_phases": []},
        )

        records = read_cycles()
        assert "writer" in records[0]["agents"]
        assert records[0]["agents"]["writer"]["tokens"] == 3000


class TestReadCycles:
    def test_empty_file_returns_empty(self, temp_metrics_dir):
        records = read_cycles()
        assert records == []

    def test_last_n_filter(self, temp_metrics_dir):
        for i in range(10):
            record_cycle(
                iteration=i + 1, phase="mid", state="normal", cycle_time=5.0,
                agent_metrics={}, token_usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "calls": 0},
                loop_metrics={"files_written": 0, "tests_passed": 0, "tests_total": 0, "review_scores": [], "parallel_phases": []},
            )
        records = read_cycles(last_n=3)
        assert len(records) == 3
        assert records[0]["cycle"] == 8
        assert records[2]["cycle"] == 10

    def test_since_filter(self, temp_metrics_dir):
        # Write a record
        record_cycle(
            iteration=1, phase="mid", state="normal", cycle_time=5.0,
            agent_metrics={}, token_usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "calls": 0},
            loop_metrics={"files_written": 0, "tests_passed": 0, "tests_total": 0, "review_scores": [], "parallel_phases": []},
        )
        # Read with since=now-1h (should include the record)
        since = datetime.now() - timedelta(hours=1)
        records = read_cycles(since=since)
        assert len(records) == 1

        # Read with since=future (should exclude)
        future = datetime.now() + timedelta(hours=1)
        records = read_cycles(since=future)
        assert len(records) == 0


class TestAnalysisTables:
    @pytest.fixture
    def sample_records(self, temp_metrics_dir):
        for i in range(5):
            record_cycle(
                iteration=i + 1, phase="mid" if i < 3 else "mid_1",
                state="normal", cycle_time=10.0 + i * 2,
                agent_metrics={
                    "writer": {"tokens": 3000 + i * 100, "calls": 1, "time": 2.0},
                    "expert": {"tokens": 4000 + i * 200, "calls": 1, "time": 3.0},
                },
                token_usage={"prompt_tokens": 5000, "completion_tokens": 2000, "total_tokens": 7000 + i * 300, "calls": 2 + i},
                loop_metrics={
                    "files_written": i, "tests_passed": i, "tests_total": i + 1,
                    "review_scores": [7 + i] if i > 0 else [],
                    "parallel_phases": [{"phase": "2a", "agents": ["Research", "Coder"], "time": 1.5}],
                },
            )
        return read_cycles()

    def test_summary_table_has_correct_columns(self, sample_records):
        table = summary_table(sample_records)
        assert table.title == "📊 Cycle Metrics"
        assert len(table.rows) == 5

    def test_agent_summary_table(self, sample_records):
        table = agent_summary_table(sample_records)
        assert table.title == "🤖 Agent Token Usage"
        assert len(table.rows) >= 2  # writer + expert

    def test_trend_summary_table(self, sample_records):
        table = trend_summary(sample_records)
        assert table.title == "📈 Performance Trend"
        assert len(table.rows) >= 2  # cycle_time + tokens

    def test_get_stats_summary(self, sample_records):
        stats = get_stats_summary(sample_records)
        assert stats["total_cycles"] == 5
        assert stats["avg_cycle_time"] > 0
        assert stats["min_cycle_time"] == 10.0
        assert stats["max_cycle_time"] == 18.0
        assert stats["total_tokens_used"] > 0


class TestAgentUsageTracking:
    """Test the per-agent token tracking in llm_client."""

    def test_set_current_agent_thread_safety(self):
        """Test that thread-local agent tagging works."""
        import threading
        from adelie.llm_client import set_current_agent, _get_current_agent

        results = {}

        def worker(name):
            set_current_agent(name)
            import time
            time.sleep(0.05)  # Small delay to test thread isolation
            results[name] = _get_current_agent()

        threads = [
            threading.Thread(target=worker, args=("writer",)),
            threading.Thread(target=worker, args=("expert",)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert results["writer"] == "writer"
        assert results["expert"] == "expert"

    def test_agent_usage_tracking(self):
        """Test that _record_usage properly tracks per-agent stats."""
        from adelie.llm_client import reset_usage, set_current_agent, get_agent_usage, _record_usage

        reset_usage()
        set_current_agent("writer")
        _record_usage(100, 50)
        _record_usage(200, 100)

        set_current_agent("expert")
        _record_usage(300, 150)

        usage = get_agent_usage()
        assert "writer" in usage
        assert usage["writer"]["total_tokens"] == 450
        assert usage["writer"]["calls"] == 2
        assert "expert" in usage
        assert usage["expert"]["total_tokens"] == 450
        assert usage["expert"]["calls"] == 1

    def test_reset_clears_agent_usage(self):
        """Test that reset_usage() clears per-agent data."""
        from adelie.llm_client import reset_usage, set_current_agent, get_agent_usage, _record_usage

        set_current_agent("test_agent")
        _record_usage(100, 50)
        assert len(get_agent_usage()) > 0

        reset_usage()
        assert len(get_agent_usage()) == 0
