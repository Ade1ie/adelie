"""tests/test_staging_verify.py — Tests for staging file verification."""
from __future__ import annotations

import json

import pytest


@pytest.fixture
def orchestrator_env(tmp_path, monkeypatch):
    """Set up a minimal orchestrator environment."""
    import adelie.config as cfg
    import adelie.orchestrator as orch_mod
    ws = tmp_path / ".adelie" / "kb"
    ws.mkdir(parents=True)
    monkeypatch.setattr(cfg, "WORKSPACE_PATH", ws)
    monkeypatch.setattr(cfg, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(cfg, "ADELIE_ROOT", tmp_path / ".adelie")
    # Also patch module-level ADELIE_ROOT in orchestrator
    monkeypatch.setattr(orch_mod, "ADELIE_ROOT", tmp_path / ".adelie")

    staging = tmp_path / ".adelie" / "staging"
    staging.mkdir(parents=True)
    return tmp_path, staging


class TestVerifyStagedFiles:
    def test_valid_python_passes(self, orchestrator_env):
        _, staging = orchestrator_env
        (staging / "main.py").write_text("print('hello world')")

        from adelie.orchestrator import Orchestrator
        orch = Orchestrator.__new__(Orchestrator)

        passed, failed = orch._verify_staged_files(
            [{"filepath": "main.py"}]
        )

        assert len(passed) == 1
        assert len(failed) == 0

    def test_invalid_python_fails(self, orchestrator_env):
        _, staging = orchestrator_env
        (staging / "bad.py").write_text("def foo(\n  invalid syntax here")

        from adelie.orchestrator import Orchestrator
        orch = Orchestrator.__new__(Orchestrator)

        passed, failed = orch._verify_staged_files(
            [{"filepath": "bad.py"}]
        )

        assert len(passed) == 0
        assert len(failed) == 1
        assert "error" in failed[0]

    def test_valid_json_passes(self, orchestrator_env):
        _, staging = orchestrator_env
        (staging / "data.json").write_text('{"key": "value"}')

        from adelie.orchestrator import Orchestrator
        orch = Orchestrator.__new__(Orchestrator)

        passed, failed = orch._verify_staged_files(
            [{"filepath": "data.json"}]
        )

        assert len(passed) == 1

    def test_invalid_json_fails(self, orchestrator_env):
        _, staging = orchestrator_env
        (staging / "bad.json").write_text("{invalid json")

        from adelie.orchestrator import Orchestrator
        orch = Orchestrator.__new__(Orchestrator)

        passed, failed = orch._verify_staged_files(
            [{"filepath": "bad.json"}]
        )

        assert len(passed) == 0
        assert len(failed) == 1

    def test_unknown_ext_passes_through(self, orchestrator_env):
        _, staging = orchestrator_env
        (staging / "style.css").write_text("body { color: red; }")

        from adelie.orchestrator import Orchestrator
        orch = Orchestrator.__new__(Orchestrator)

        passed, failed = orch._verify_staged_files(
            [{"filepath": "style.css"}]
        )

        assert len(passed) == 1
        assert len(failed) == 0
