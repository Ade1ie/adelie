"""tests/test_parallel_execution.py — Tests for parallel agent execution."""
from __future__ import annotations

import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import patch, MagicMock

import pytest


class TestThreadPoolExecution:
    """Test the ThreadPoolExecutor pattern used in orchestrator parallel phases."""

    def test_parallel_agents_run_concurrently(self):
        """Verify that two tasks actually run in parallel (not sequentially)."""
        execution_log = []

        def slow_agent_a():
            execution_log.append(("a_start", time.time()))
            time.sleep(0.3)
            execution_log.append(("a_end", time.time()))
            return {"agent": "a", "result": "ok"}

        def slow_agent_b():
            execution_log.append(("b_start", time.time()))
            time.sleep(0.3)
            execution_log.append(("b_end", time.time()))
            return {"agent": "b", "result": "ok"}

        start = time.time()
        results = {}
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="test-parallel") as pool:
            futures = {
                pool.submit(slow_agent_a): "a",
                pool.submit(slow_agent_b): "b",
            }
            for future in as_completed(futures, timeout=5):
                name = futures[future]
                results[name] = future.result()

        elapsed = time.time() - start

        # If truly parallel, total time should be ~0.3s, not ~0.6s
        assert elapsed < 0.55, f"Should run in parallel, but took {elapsed:.2f}s"
        assert "a" in results
        assert "b" in results
        assert results["a"]["result"] == "ok"
        assert results["b"]["result"] == "ok"

    def test_one_agent_failure_doesnt_block_others(self):
        """Verify partial failure: one agent crashing doesn't prevent others from completing."""
        def failing_agent():
            raise RuntimeError("Agent crashed!")

        def successful_agent():
            time.sleep(0.1)
            return {"status": "ok"}

        results = {}
        errors = {}
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = {
                pool.submit(failing_agent): "failing",
                pool.submit(successful_agent): "success",
            }
            for future in as_completed(futures, timeout=5):
                name = futures[future]
                try:
                    results[name] = future.result()
                except Exception as e:
                    errors[name] = str(e)

        assert "success" in results
        assert results["success"]["status"] == "ok"
        assert "failing" in errors
        assert "crashed" in errors["failing"]

    def test_single_agent_runs_without_pool_overhead(self):
        """When only one agent needs to run, ThreadPoolExecutor still works efficiently."""
        def single_agent():
            return {"total_files": 3}

        with ThreadPoolExecutor(max_workers=1) as pool:
            futures = {pool.submit(single_agent): "coder"}
            for future in as_completed(futures, timeout=5):
                result = future.result()

        assert result["total_files"] == 3

    def test_timeout_handling(self):
        """Verify that as_completed timeout actually raises TimeoutError."""
        def very_slow_agent():
            time.sleep(10)
            return {"status": "done"}

        with ThreadPoolExecutor(max_workers=1) as pool:
            futures = {pool.submit(very_slow_agent): "slow"}
            with pytest.raises(TimeoutError):
                for future in as_completed(futures, timeout=0.2):
                    future.result()

    def test_results_collected_from_multiple_parallel_agents(self):
        """Simulate Phase 2a: Research + Coder running in parallel."""
        def mock_research():
            time.sleep(0.1)
            return [{"query": "test", "result": "found"}]

        def mock_coder():
            time.sleep(0.15)
            return {"total_files": 2, "files": ["a.py", "b.py"]}

        loop_metrics = {
            "research_queries": 0,
            "research_results": 0,
            "files_written": 0,
        }

        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="adelie-p2") as pool:
            futures = {
                pool.submit(mock_research): "research",
                pool.submit(mock_coder): "coder",
            }
            for future in as_completed(futures, timeout=5):
                agent_name = futures[future]
                try:
                    result = future.result()
                    if agent_name == "research":
                        loop_metrics["research_queries"] = 1
                        loop_metrics["research_results"] = len(result)
                    elif agent_name == "coder":
                        loop_metrics["files_written"] = result["total_files"]
                except Exception:
                    pass

        assert loop_metrics["research_results"] == 1
        assert loop_metrics["files_written"] == 2


class TestParallelPhaseMetrics:
    """Test the parallel_phases metrics tracking."""

    def test_metrics_format(self):
        """Verify parallel phase metrics have expected structure."""
        loop_metrics = {
            "parallel_phases": [],
        }

        # Simulate recording Phase 2a metrics
        parallel_names = ["Research", "Coder"]
        phase_elapsed = 1.5
        loop_metrics["parallel_phases"].append({
            "phase": "2a",
            "agents": parallel_names,
            "time": round(phase_elapsed, 1),
        })

        assert len(loop_metrics["parallel_phases"]) == 1
        entry = loop_metrics["parallel_phases"][0]
        assert entry["phase"] == "2a"
        assert "Research" in entry["agents"]
        assert "Coder" in entry["agents"]
        assert entry["time"] == 1.5

    def test_multiple_phases_tracked(self):
        """Verify that multiple parallel phases are tracked independently."""
        loop_metrics = {"parallel_phases": []}

        loop_metrics["parallel_phases"].append({"phase": "2a", "agents": ["Research", "Coder"], "time": 2.0})
        loop_metrics["parallel_phases"].append({"phase": "3", "agents": ["Tester", "Runner"], "time": 5.0})
        loop_metrics["parallel_phases"].append({"phase": "4", "agents": ["Monitor", "Analyst"], "time": 1.0})

        assert len(loop_metrics["parallel_phases"]) == 3
        phases = [p["phase"] for p in loop_metrics["parallel_phases"]]
        assert phases == ["2a", "3", "4"]

    def test_metrics_display_string(self):
        """Verify the metrics display string matches expected format."""
        parallel_phases = [
            {"phase": "2a", "agents": ["Research", "Coder"], "time": 1.5},
            {"phase": "3", "agents": ["Tester"], "time": 3.2},
        ]
        parts = []
        for pp in parallel_phases:
            parts.append(f"⚡P{pp['phase']}:{pp['time']}s")

        assert parts == ["⚡P2a:1.5s", "⚡P3:3.2s"]
