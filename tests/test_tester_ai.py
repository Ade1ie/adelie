"""tests/test_tester_ai.py — Tests for Tester AI (mocks LLM + subprocess)."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest


MOCK_TEST_SCRIPTS = {
    "test_scripts": [
        {
            "name": "test_math",
            "filename": "test_math.py",
            "language": "python",
            "content": "assert 1 + 1 == 2\nprint('PASSED')",
            "run_command": "python .adelie/tests/scripts/test_math.py",
            "test_layer": 0,
            "description": "Basic math test",
        }
    ]
}


@pytest.fixture
def tmp_workspace(tmp_path, monkeypatch):
    import adelie.config as cfg
    ws = tmp_path / ".adelie" / "kb"
    ws.mkdir(parents=True)
    monkeypatch.setattr(cfg, "WORKSPACE_PATH", ws)
    return tmp_path


class TestTesterAI:
    def test_command_whitelist(self):
        from adelie.agents.tester_ai import _is_command_allowed
        assert _is_command_allowed("python test.py") is True
        assert _is_command_allowed("pytest -v") is True
        assert _is_command_allowed("npm test") is True
        assert _is_command_allowed("rm -rf /") is False
        assert _is_command_allowed("sudo reboot") is False
        assert _is_command_allowed("shutdown now") is False

    def test_generates_and_saves_scripts(self, tmp_workspace, monkeypatch):
        import adelie.agents.tester_ai as t

        (tmp_workspace / "src").mkdir()
        (tmp_workspace / "src" / "math.py").write_text("def add(a,b): return a+b", encoding="utf-8")

        with patch("adelie.agents.tester_ai.generate") as mock_gen:
            mock_gen.return_value = json.dumps(MOCK_TEST_SCRIPTS)
            result = t.run_tests(
                source_files=[{"filepath": "src/math.py", "language": "python", "description": "Math"}],
                max_test_layer=2,
                workspace_root=tmp_workspace,
            )

        # Script should be saved
        script_path = tmp_workspace / ".adelie" / "tests" / "scripts" / "test_math.py"
        assert script_path.exists()
        assert result["total_tests"] == 1

    def test_skips_higher_layer_tests(self, tmp_workspace, monkeypatch):
        import adelie.agents.tester_ai as t

        scripts_with_layers = {
            "test_scripts": [
                {"name": "unit", "filename": "t0.py", "language": "python",
                 "content": "pass", "run_command": "python t0.py", "test_layer": 0, "description": ""},
                {"name": "e2e", "filename": "t2.py", "language": "python",
                 "content": "pass", "run_command": "python t2.py", "test_layer": 2, "description": ""},
            ]
        }

        with patch("adelie.agents.tester_ai.generate") as mock_gen:
            mock_gen.return_value = json.dumps(scripts_with_layers)
            result = t.run_tests(
                source_files=[{"filepath": "x.py", "language": "python", "description": ""}],
                max_test_layer=0,  # Only layer 0
                workspace_root=tmp_workspace,
            )

        # Only layer 0 test should run
        assert result["total_tests"] == 1

    def test_empty_source_returns_zero(self, tmp_workspace, monkeypatch):
        import adelie.agents.tester_ai as t
        result = t.run_tests(source_files=[], workspace_root=tmp_workspace)
        assert result["total_tests"] == 0
