"""tests/test_coder_ai.py — Tests for Coder AI and Coder Manager (mocks LLM)."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest


MOCK_CODER_RESPONSE = [
    {
        "filepath": "src/auth.py",
        "language": "python",
        "content": "def login(user, pw):\n    return True\n",
        "description": "Login function",
    }
]


@pytest.fixture
def tmp_workspace(tmp_path, monkeypatch):
    import adelie.config as cfg
    import adelie.kb.retriever as r

    ws = tmp_path / ".adelie" / "kb"
    ws.mkdir(parents=True)
    monkeypatch.setattr(cfg, "WORKSPACE_PATH", ws)
    monkeypatch.setattr(r, "WORKSPACE_PATH", ws)
    monkeypatch.setattr(r, "INDEX_FILE", ws / "index.json")
    r.ensure_workspace()
    return tmp_path


class TestCoderAI:
    def test_writes_source_file(self, tmp_workspace, monkeypatch):
        import adelie.agents.coder_ai as c

        staging_root = tmp_workspace / ".adelie" / "staging"
        monkeypatch.setattr(c, "WORKSPACE_PATH", tmp_workspace / ".adelie" / "kb")
        monkeypatch.setattr(c, "CODER_ROOT", tmp_workspace / ".adelie" / "coder")
        monkeypatch.setattr(c, "STAGING_ROOT", staging_root)

        with patch("adelie.agents.coder_ai.generate") as mock_gen:
            mock_gen.return_value = json.dumps(MOCK_CODER_RESPONSE)
            result = c.run_coder(
                coder_name="test_coder",
                layer=0,
                task="Create login",
                context="Use Python",
                workspace_root=tmp_workspace,
            )

        assert len(result) == 1
        assert result[0]["filepath"] == "src/auth.py"
        assert result[0].get("staged") is True
        # Files are now written to staging, not project root
        assert (staging_root / "src" / "auth.py").exists()
        content = (staging_root / "src" / "auth.py").read_text()
        assert "def login" in content

    def test_writes_coder_log(self, tmp_workspace, monkeypatch):
        import adelie.agents.coder_ai as c

        coder_root = tmp_workspace / ".adelie" / "coder"
        monkeypatch.setattr(c, "WORKSPACE_PATH", tmp_workspace / ".adelie" / "kb")
        monkeypatch.setattr(c, "CODER_ROOT", coder_root)

        with patch("adelie.agents.coder_ai.generate") as mock_gen:
            mock_gen.return_value = json.dumps(MOCK_CODER_RESPONSE)
            c.run_coder(
                coder_name="backend_login",
                layer=0,
                task="Build login",
                context="FastAPI",
                workspace_root=tmp_workspace,
            )

        log_path = coder_root / "layer" / "0" / "backend_login" / "log.md"
        assert log_path.exists()
        log_content = log_path.read_text()
        assert "src/auth.py" in log_content

    def test_rejects_unsafe_paths(self, tmp_workspace, monkeypatch):
        import adelie.agents.coder_ai as c

        monkeypatch.setattr(c, "WORKSPACE_PATH", tmp_workspace / ".adelie" / "kb")
        monkeypatch.setattr(c, "CODER_ROOT", tmp_workspace / ".adelie" / "coder")

        evil_response = [{"filepath": "../../../etc/passwd", "language": "", "content": "hacked", "description": ""}]
        with patch("adelie.agents.coder_ai.generate") as mock_gen:
            mock_gen.return_value = json.dumps(evil_response)
            result = c.run_coder(
                coder_name="evil",
                layer=0,
                task="hack",
                context="",
                workspace_root=tmp_workspace,
            )

        assert len(result) == 0
        assert not (tmp_workspace.parent.parent.parent / "etc" / "passwd").exists()

    def test_handles_invalid_json(self, tmp_workspace, monkeypatch):
        import adelie.agents.coder_ai as c

        monkeypatch.setattr(c, "WORKSPACE_PATH", tmp_workspace / ".adelie" / "kb")
        monkeypatch.setattr(c, "CODER_ROOT", tmp_workspace / ".adelie" / "coder")

        with patch("adelie.agents.coder_ai.generate") as mock_gen:
            mock_gen.return_value = "NOT JSON AT ALL"
            result = c.run_coder(
                coder_name="broken",
                layer=0,
                task="nothing",
                context="",
                workspace_root=tmp_workspace,
            )

        assert result == []

    def test_reads_lower_layer_logs(self, tmp_workspace, monkeypatch):
        import adelie.agents.coder_ai as c

        coder_root = tmp_workspace / ".adelie" / "coder"
        monkeypatch.setattr(c, "CODER_ROOT", coder_root)

        # Create a Layer 0 log
        l0_dir = coder_root / "layer" / "0" / "feature_x"
        l0_dir.mkdir(parents=True)
        (l0_dir / "log.md").write_text("# Feature X Log\nDid stuff.", encoding="utf-8")

        logs = c._read_lower_layer_logs(layer=1)
        assert "Feature X" in logs
        assert "feature_x" in logs

        # Layer 0 shouldn't read lower layers
        logs_l0 = c._read_lower_layer_logs(layer=0)
        assert logs_l0 == ""
