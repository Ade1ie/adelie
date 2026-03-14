"""tests/test_expert_ai.py — Integration test for Expert AI (mocks LLM client)."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

MOCK_DECISION = {
    "action": "CONTINUE",
    "reasoning": "Everything looks good.",
    "commands": ["proceed"],
    "kb_updates_needed": [],
    "next_situation": "normal",
    "export_data": None,
}


@pytest.fixture
def tmp_workspace(tmp_path, monkeypatch):
    import adelie.config as cfg
    import adelie.kb.retriever as r
    monkeypatch.setattr(cfg, "WORKSPACE_PATH", tmp_path)
    monkeypatch.setattr(r, "WORKSPACE_PATH", tmp_path)
    monkeypatch.setattr(r, "INDEX_FILE", tmp_path / "index.json")
    r.ensure_workspace()
    return tmp_path


class TestExpertAI:
    def test_returns_decision_on_valid_response(self, tmp_workspace, monkeypatch):
        import adelie.kb.retriever as r
        monkeypatch.setattr(r, "WORKSPACE_PATH", tmp_workspace)
        monkeypatch.setattr(r, "INDEX_FILE", tmp_workspace / "index.json")

        with patch("adelie.agents.expert_ai.generate") as mock_generate:
            mock_generate.return_value = json.dumps(MOCK_DECISION)
            import adelie.agents.expert_ai as e
            decision = e.run(
                system_state={"situation": "normal", "loop_iteration": 1},
                loop_iteration=1,
            )

        assert decision["action"] == "CONTINUE"
        assert decision["next_situation"] == "normal"

    def test_returns_fallback_on_invalid_json(self, tmp_workspace, monkeypatch):
        import adelie.kb.retriever as r
        monkeypatch.setattr(r, "WORKSPACE_PATH", tmp_workspace)
        monkeypatch.setattr(r, "INDEX_FILE", tmp_workspace / "index.json")

        with patch("adelie.agents.expert_ai.generate") as mock_generate:
            mock_generate.return_value = "INVALID JSON"
            import adelie.agents.expert_ai as e
            decision = e.run(
                system_state={"situation": "normal"},
                loop_iteration=1,
            )

        assert decision["action"] == "CONTINUE"
        assert decision["next_situation"] == "normal"

    def test_situational_kb_loaded_for_error(self, tmp_workspace, monkeypatch):
        """Verify that error situation loads errors/ KB files."""
        import adelie.kb.retriever as r
        monkeypatch.setattr(r, "WORKSPACE_PATH", tmp_workspace)
        monkeypatch.setattr(r, "INDEX_FILE", tmp_workspace / "index.json")

        # Write a KB error file
        (tmp_workspace / "errors" / "known_error.md").write_text("# Known Error\nfix: restart", encoding="utf-8")
        r.update_index("errors/known_error.md", ["error"], "A known error")

        captured_prompts: list[str] = []

        def mock_gen(system_prompt, user_prompt, temperature=0.3):
            captured_prompts.append(user_prompt)
            return json.dumps(MOCK_DECISION)

        with patch("adelie.agents.expert_ai.generate", side_effect=mock_gen):
            import adelie.agents.expert_ai as e
            e.run(
                system_state={"situation": "error"},
                loop_iteration=1,
            )

        # Verify the prompt included the error KB content
        assert len(captured_prompts) == 1
        assert "known_error.md" in captured_prompts[0] or "Known Error" in captured_prompts[0] or "restart" in captured_prompts[0]
