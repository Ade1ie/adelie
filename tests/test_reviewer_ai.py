"""tests/test_reviewer_ai.py — Tests for Reviewer AI (mocks LLM)."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest


MOCK_REVIEW_PASS = {
    "overall_score": 9,
    "issues": [
        {"severity": "INFO", "file": "src/auth.py", "line": 5, "title": "Consider type hints", "description": "Add type annotations", "suggestion": "Use type hints"}
    ],
    "summary": "Code looks good overall.",
    "approved": True,
}

MOCK_REVIEW_FAIL = {
    "overall_score": 3,
    "issues": [
        {"severity": "CRITICAL", "file": "src/auth.py", "line": 10, "title": "SQL Injection", "description": "Raw SQL", "suggestion": "Use parameterized queries"}
    ],
    "summary": "Critical security issues.",
    "approved": False,
}


@pytest.fixture
def tmp_workspace(tmp_path, monkeypatch):
    import adelie.config as cfg
    ws = tmp_path / ".adelie" / "kb"
    ws.mkdir(parents=True)
    monkeypatch.setattr(cfg, "WORKSPACE_PATH", ws)
    return tmp_path


class TestReviewerAI:
    def test_approved_review(self, tmp_workspace, monkeypatch):
        import adelie.agents.reviewer_ai as rv
        monkeypatch.setattr(rv, "WORKSPACE_PATH", tmp_workspace / ".adelie" / "kb")
        monkeypatch.setattr(rv, "REVIEW_ROOT", tmp_workspace / ".adelie" / "reviews")

        # Create source file
        (tmp_workspace / "src").mkdir()
        (tmp_workspace / "src" / "auth.py").write_text("def login(): pass", encoding="utf-8")

        with patch("adelie.agents.reviewer_ai.generate") as mock_gen:
            mock_gen.return_value = json.dumps(MOCK_REVIEW_PASS)
            result = rv.run_review(
                coder_name="test_coder",
                written_files=[{"filepath": "src/auth.py", "language": "python", "description": "Auth"}],
                workspace_root=tmp_workspace,
            )

        assert result["approved"] is True
        assert result["overall_score"] == 9

    def test_rejected_review(self, tmp_workspace, monkeypatch):
        import adelie.agents.reviewer_ai as rv
        monkeypatch.setattr(rv, "WORKSPACE_PATH", tmp_workspace / ".adelie" / "kb")
        monkeypatch.setattr(rv, "REVIEW_ROOT", tmp_workspace / ".adelie" / "reviews")

        (tmp_workspace / "src").mkdir(exist_ok=True)
        (tmp_workspace / "src" / "auth.py").write_text("query = f'SELECT * FROM users WHERE id={id}'", encoding="utf-8")

        with patch("adelie.agents.reviewer_ai.generate") as mock_gen:
            mock_gen.return_value = json.dumps(MOCK_REVIEW_FAIL)
            result = rv.run_review(
                coder_name="bad_coder",
                written_files=[{"filepath": "src/auth.py", "language": "python", "description": "Auth"}],
                workspace_root=tmp_workspace,
            )

        assert result["approved"] is False
        assert len(result["issues"]) == 1
        assert result["issues"][0]["severity"] == "CRITICAL"

    def test_saves_review_report(self, tmp_workspace, monkeypatch):
        import adelie.agents.reviewer_ai as rv
        review_dir = tmp_workspace / ".adelie" / "reviews"
        monkeypatch.setattr(rv, "WORKSPACE_PATH", tmp_workspace / ".adelie" / "kb")
        monkeypatch.setattr(rv, "REVIEW_ROOT", review_dir)

        (tmp_workspace / "src").mkdir(exist_ok=True)
        (tmp_workspace / "src" / "app.py").write_text("print('hi')", encoding="utf-8")

        with patch("adelie.agents.reviewer_ai.generate") as mock_gen:
            mock_gen.return_value = json.dumps(MOCK_REVIEW_PASS)
            rv.run_review(
                coder_name="my_coder",
                written_files=[{"filepath": "src/app.py", "language": "python", "description": "App"}],
                workspace_root=tmp_workspace,
            )

        assert review_dir.exists()
        reports = list(review_dir.glob("my_coder_*.md"))
        assert len(reports) == 1

    def test_empty_files_returns_perfect_score(self, tmp_workspace, monkeypatch):
        import adelie.agents.reviewer_ai as rv
        monkeypatch.setattr(rv, "WORKSPACE_PATH", tmp_workspace / ".adelie" / "kb")
        result = rv.run_review(coder_name="empty", written_files=[], workspace_root=tmp_workspace)
        assert result["approved"] is True
        assert result["overall_score"] == 10
