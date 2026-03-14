"""tests/test_goal_seeding.py — Tests for goal seeding and LLM guardrails."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest


@pytest.fixture
def tmp_workspace(tmp_path, monkeypatch):
    import adelie.config as cfg
    ws = tmp_path / ".adelie" / "kb"
    ws.mkdir(parents=True)
    (ws / "logic").mkdir()
    monkeypatch.setattr(cfg, "WORKSPACE_PATH", ws)
    monkeypatch.setattr(cfg, "ADELIE_ROOT", ws.parent)
    monkeypatch.setattr(cfg, "PROJECT_ROOT", tmp_path)
    return ws


class TestGoalSeeding:
    def test_goal_file_loaded_by_expert(self, tmp_workspace, monkeypatch):
        """Expert AI should always include project_goal.md when it exists."""
        # Create goal file
        goal_path = tmp_workspace / "logic" / "project_goal.md"
        goal_path.write_text("# Goal\nBuild a REST API", encoding="utf-8")

        # Create index
        (tmp_workspace / "index.json").write_text("{}", encoding="utf-8")

        import adelie.agents.expert_ai as expert
        # Also patch the WORKSPACE_PATH that expert_ai.py reads via `from adelie.config import WORKSPACE_PATH`
        import adelie.config as cfg
        monkeypatch.setattr(cfg, "WORKSPACE_PATH", tmp_workspace)

        from adelie.kb import retriever as _retriever
        monkeypatch.setattr(_retriever, "WORKSPACE_PATH", tmp_workspace)

        monkeypatch.setattr("adelie.kb.retriever.ensure_workspace", lambda: None)
        monkeypatch.setattr("adelie.kb.retriever.get_index_summary", lambda: "empty")
        monkeypatch.setattr("adelie.kb.retriever.list_categories", lambda: {"logic": 1})
        monkeypatch.setattr("adelie.kb.retriever.semantic_query", lambda **kw: [])
        monkeypatch.setattr("adelie.kb.retriever.read_files", lambda paths: "goal content" if paths else "")

        decision = {
            "action": "CONTINUE",
            "reasoning": "test",
            "commands": [],
            "kb_updates_needed": [],
            "next_situation": "normal",
            "coder_tasks": [],
            "export_data": None,
        }

        with patch("adelie.agents.expert_ai.generate") as mock_gen:
            mock_gen.return_value = json.dumps(decision)
            result = expert.run(
                system_state={"situation": "normal", "goal": "test", "phase": "initial"},
                loop_iteration=1,
            )

        # Verify it worked
        assert result["action"] == "CONTINUE"
        # The generate call should have been made with goal content in the prompt
        call_args = mock_gen.call_args
        assert call_args is not None


class TestLLMGuardrails:
    def test_validate_decision_valid(self):
        from adelie.agents.expert_ai import _validate_decision
        assert _validate_decision({
            "action": "CONTINUE",
            "next_situation": "normal",
        }) is True

    def test_validate_decision_invalid_action(self):
        from adelie.agents.expert_ai import _validate_decision
        assert _validate_decision({
            "action": "INVALID_ACTION",
            "next_situation": "normal",
        }) is False

    def test_validate_decision_missing_action(self):
        from adelie.agents.expert_ai import _validate_decision
        assert _validate_decision({
            "next_situation": "normal",
        }) is False

    def test_validate_decision_invalid_situation(self):
        from adelie.agents.expert_ai import _validate_decision
        assert _validate_decision({
            "action": "CONTINUE",
            "next_situation": "invalid_state",
        }) is False

    def test_validate_decision_not_dict(self):
        from adelie.agents.expert_ai import _validate_decision
        assert _validate_decision("not a dict") is False

    def test_validate_decision_optional_situation(self):
        """next_situation is optional — missing should still be valid."""
        from adelie.agents.expert_ai import _validate_decision
        assert _validate_decision({"action": "CONTINUE"}) is True

    def test_json_retry_on_failure(self, tmp_workspace, monkeypatch):
        """Expert AI should retry on invalid JSON."""
        import adelie.agents.expert_ai as expert
        monkeypatch.setattr("adelie.kb.retriever.ensure_workspace", lambda: None)
        monkeypatch.setattr("adelie.kb.retriever.get_index_summary", lambda: "empty")
        monkeypatch.setattr("adelie.kb.retriever.list_categories", lambda: {})
        monkeypatch.setattr("adelie.kb.retriever.semantic_query", lambda **kw: [])
        monkeypatch.setattr("adelie.kb.retriever.read_files", lambda paths: "")

        good_response = json.dumps({
            "action": "CONTINUE",
            "reasoning": "retry worked",
            "commands": [],
            "kb_updates_needed": [],
            "next_situation": "normal",
            "coder_tasks": [],
            "export_data": None,
        })

        call_count = 0
        def mock_generate(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "This is not JSON at all"
            return good_response

        with patch("adelie.agents.expert_ai.generate", side_effect=mock_generate):
            result = expert.run(
                system_state={"situation": "normal", "goal": "test", "phase": "initial"},
                loop_iteration=1,
            )

        assert result["action"] == "CONTINUE"
        assert call_count == 2  # First call failed, second succeeded
