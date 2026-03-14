"""tests/test_monitor_ai.py — Tests for Monitor AI."""
from __future__ import annotations

import json
import os

import pytest


@pytest.fixture
def tmp_workspace(tmp_path, monkeypatch):
    import adelie.config as cfg
    ws = tmp_path / ".adelie" / "kb"
    ws.mkdir(parents=True)
    monkeypatch.setattr(cfg, "WORKSPACE_PATH", ws)
    return tmp_path


class TestMonitorAI:
    def test_http_check_down(self, tmp_workspace, monkeypatch):
        from adelie.agents.monitor_ai import _check_http
        # Non-existent endpoint should return "down"
        result = _check_http("http://127.0.0.1:19999", timeout=1)
        assert result["status"] == "down"
        assert result["url"] == "http://127.0.0.1:19999"

    def test_process_check(self):
        from adelie.agents.monitor_ai import _check_process
        # Current process should be alive
        assert _check_process(os.getpid()) is True
        # Non-existent PID should be dead
        assert _check_process(99999999) is False

    def test_health_check_saves_report(self, tmp_workspace, monkeypatch):
        import adelie.agents.monitor_ai as m
        monitor_root = tmp_workspace / ".adelie" / "monitor"
        monkeypatch.setattr(m, "MONITOR_ROOT", monitor_root)
        monkeypatch.setattr(m, "ALERTS_DIR", monitor_root / "alerts")
        monkeypatch.setattr(m, "RUNNER_ROOT", tmp_workspace / ".adelie" / "runner")
        monkeypatch.setattr(m, "WORKSPACE_PATH", tmp_workspace / ".adelie" / "kb")

        result = m.run_health_check(
            endpoints=["http://127.0.0.1:19999"],
            workspace_root=tmp_workspace,
        )

        assert "overall" in result
        assert monitor_root.exists()
        reports = list(monitor_root.glob("health_*.md"))
        assert len(reports) == 1

    def test_log_error_scan(self, tmp_workspace):
        from adelie.agents.monitor_ai import _scan_log_errors
        # Create a log with errors
        log_dir = tmp_workspace / "logs"
        log_dir.mkdir()
        (log_dir / "app.log").write_text(
            "INFO: started\nERROR: database connection failed\nINFO: retrying\n",
            encoding="utf-8",
        )

        errors = _scan_log_errors(tmp_workspace)
        assert len(errors) == 1
        assert "database connection failed" in errors[0]
