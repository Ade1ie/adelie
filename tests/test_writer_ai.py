"""tests/test_writer_ai.py — Integration test for Writer AI (mocks LLM client)."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest


MOCK_RESPONSE = [
    {
        "category": "skills",
        "filename": "test_skill.md",
        "tags": ["test", "skill"],
        "summary": "A test skill file",
        "content": "# Test Skill\nThis is a test.",
    }
]


@pytest.fixture
def tmp_workspace(tmp_path, monkeypatch):
    import adelie.config as cfg
    import adelie.kb.retriever as r
    monkeypatch.setattr(cfg, "WORKSPACE_PATH", tmp_path)
    monkeypatch.setattr(r, "WORKSPACE_PATH", tmp_path)
    monkeypatch.setattr(r, "INDEX_FILE", tmp_path / "index.json")
    r.ensure_workspace()
    return tmp_path


class TestWriterAI:
    def test_writes_kb_file_on_valid_response(self, tmp_workspace, monkeypatch):
        import adelie.kb.retriever as r
        monkeypatch.setattr(r, "WORKSPACE_PATH", tmp_workspace)
        monkeypatch.setattr(r, "INDEX_FILE", tmp_workspace / "index.json")

        with patch("adelie.agents.writer_ai.generate") as mock_generate:
            mock_generate.return_value = json.dumps(MOCK_RESPONSE)
            import adelie.agents.writer_ai as w
            # Patch workspace path in writer_ai too
            monkeypatch.setattr("adelie.agents.writer_ai.WORKSPACE_PATH", tmp_workspace)
            written = w.run(
                system_state={"situation": "normal", "loop_iteration": 1},
                expert_output=None,
                loop_iteration=1,
            )

        assert len(written) == 1
        assert written[0]["path"] == "skills/test_skill.md"
        assert (tmp_workspace / "skills" / "test_skill.md").exists()

    def test_handles_invalid_json_gracefully(self, tmp_workspace, monkeypatch):
        with patch("adelie.agents.writer_ai.generate") as mock_generate:
            mock_generate.return_value = "NOT JSON"
            import adelie.agents.writer_ai as w
            monkeypatch.setattr("adelie.agents.writer_ai.WORKSPACE_PATH", tmp_workspace)
            written = w.run(
                system_state={"situation": "normal"},
                expert_output=None,
                loop_iteration=1,
            )

        assert written == []
