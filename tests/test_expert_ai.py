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

    def test_prompt_includes_coder_registry(self, tmp_workspace, monkeypatch):
        """Expert AI 프롬프트에 기존 코더 목록이 포함되는지 검증."""
        import adelie.kb.retriever as r
        monkeypatch.setattr(r, "WORKSPACE_PATH", tmp_workspace)
        monkeypatch.setattr(r, "INDEX_FILE", tmp_workspace / "index.json")

        # registry.json 생성
        coder_dir = tmp_workspace.parent / "coder"
        coder_dir.mkdir(parents=True, exist_ok=True)
        (coder_dir / "registry.json").write_text(json.dumps({
            "coders": [{"layer": 0, "name": "test_coder", "last_task": "Build X"}]
        }))

        captured = []

        def mock_gen(system_prompt, user_prompt, temperature=0.3):
            captured.append(user_prompt)
            return json.dumps(MOCK_DECISION)

        with patch("adelie.agents.expert_ai.generate", side_effect=mock_gen):
            import adelie.agents.expert_ai as e
            e.run(system_state={"situation": "normal"}, loop_iteration=1)

        assert "Existing Coders" in captured[0]
        assert "test_coder" in captured[0]

    def test_prompt_includes_build_errors(self, tmp_workspace, monkeypatch):
        """빌드 에러가 프롬프트에 포함되는지 검증."""
        import adelie.kb.retriever as r
        monkeypatch.setattr(r, "WORKSPACE_PATH", tmp_workspace)
        monkeypatch.setattr(r, "INDEX_FILE", tmp_workspace / "index.json")

        runner_dir = tmp_workspace.parent / "runner"
        runner_dir.mkdir(parents=True, exist_ok=True)
        (runner_dir / "build_log_20260314_175813.md").write_text(
            "# Runner Log\n## ❌ [BUILD] npm run build\n- Failed"
        )

        captured = []

        def mock_gen(system_prompt, user_prompt, temperature=0.3):
            captured.append(user_prompt)
            return json.dumps(MOCK_DECISION)

        with patch("adelie.agents.expert_ai.generate", side_effect=mock_gen):
            import adelie.agents.expert_ai as e
            e.run(system_state={"situation": "normal"}, loop_iteration=1)

        assert "Build" in captured[0] or "Failed" in captured[0]
