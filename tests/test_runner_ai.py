"""tests/test_runner_ai.py — Tests for Runner AI (mocks LLM + subprocess)."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest


@pytest.fixture
def tmp_workspace(tmp_path, monkeypatch):
    import adelie.config as cfg
    ws = tmp_path / ".adelie" / "kb"
    ws.mkdir(parents=True)
    monkeypatch.setattr(cfg, "WORKSPACE_PATH", ws)
    return tmp_path


class TestRunnerAI:
    def test_command_whitelist_by_tier(self):
        from adelie.agents.runner_ai import _is_allowed
        # Build tier
        assert _is_allowed("pip install flask", "build") is True
        assert _is_allowed("npm install", "build") is True
        assert _is_allowed("rm -rf /", "build") is False

        # Run tier (superset of build)
        assert _is_allowed("node server.js", "run") is True
        assert _is_allowed("uvicorn main:app", "run") is True

        # Deploy tier (superset of run)
        assert _is_allowed("docker build .", "deploy") is True
        assert _is_allowed("shutdown now", "deploy") is False

    def test_process_tracking(self, tmp_workspace, monkeypatch):
        from adelie.agents.runner_ai import _save_process, RUNNER_ROOT
        runner_root = tmp_workspace / ".adelie" / "runner"
        import adelie.agents.runner_ai as rn
        monkeypatch.setattr(rn, "RUNNER_ROOT", runner_root)
        monkeypatch.setattr(rn, "PROCESS_FILE", runner_root / "processes.json")

        _save_process(12345, "python server.py", "Test server")

        proc_file = runner_root / "processes.json"
        assert proc_file.exists()
        data = json.loads(proc_file.read_text())
        assert len(data) == 1
        assert data[0]["pid"] == 12345

    def test_handles_invalid_json(self, tmp_workspace, monkeypatch):
        import adelie.agents.runner_ai as rn
        monkeypatch.setattr(rn, "WORKSPACE_PATH", tmp_workspace / ".adelie" / "kb")
        monkeypatch.setattr(rn, "RUNNER_ROOT", tmp_workspace / ".adelie" / "runner")

        with patch("adelie.agents.runner_ai.generate") as mock_gen:
            mock_gen.return_value = "NOT JSON"
            result = rn.run_pipeline(
                source_files=[{"filepath": "x.py"}],
                max_tier="build",
                workspace_root=tmp_workspace,
            )

        assert result["executed"] == 0
