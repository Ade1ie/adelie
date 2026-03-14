"""tests/test_feedback_queue.py — Tests for the user feedback queue."""
from __future__ import annotations

import json

import pytest


@pytest.fixture
def tmp_feedback(tmp_path, monkeypatch):
    """Set up a temporary feedback directory."""
    import adelie.feedback_queue as fq
    fb_dir = tmp_path / ".adelie" / "feedback"
    fb_dir.mkdir(parents=True)
    monkeypatch.setattr(fq, "FEEDBACK_DIR", fb_dir)
    return fb_dir


class TestFeedbackQueue:
    def test_submit_creates_file(self, tmp_feedback):
        from adelie.feedback_queue import submit_feedback
        result = submit_feedback("Fix the API", priority="high", source="cli")
        assert "id" in result
        files = list(tmp_feedback.glob("*.json"))
        assert len(files) == 1
        data = json.loads(files[0].read_text(encoding="utf-8"))
        assert data["message"] == "Fix the API"
        assert data["priority"] == "high"
        assert data["processed"] is False

    def test_read_pending_returns_unprocessed(self, tmp_feedback):
        from adelie.feedback_queue import submit_feedback, read_pending
        submit_feedback("First", priority="normal")
        submit_feedback("Second", priority="critical")
        pending = read_pending()
        assert len(pending) == 2
        # Critical should come first (priority sorted)
        assert pending[0]["priority"] == "critical"
        assert pending[1]["priority"] == "normal"

    def test_mark_processed(self, tmp_feedback):
        from adelie.feedback_queue import submit_feedback, read_pending, mark_processed
        result = submit_feedback("Test feedback")
        fb_id = result["id"]
        assert len(read_pending()) == 1
        assert mark_processed(fb_id) is True
        assert len(read_pending()) == 0

    def test_clear_processed(self, tmp_feedback):
        from adelie.feedback_queue import submit_feedback, mark_processed, clear_processed
        r1 = submit_feedback("A")
        r2 = submit_feedback("B")
        mark_processed(r1["id"])
        removed = clear_processed()
        assert removed == 1
        files = list(tmp_feedback.glob("*.json"))
        assert len(files) == 1  # Only B remains

    def test_format_for_prompt(self, tmp_feedback):
        from adelie.feedback_queue import submit_feedback, read_pending, format_for_prompt
        submit_feedback("Build the API first", priority="high")
        pending = read_pending()
        prompt = format_for_prompt(pending)
        assert "User Feedback" in prompt
        assert "Build the API first" in prompt
        assert "PRIORITY" in prompt

    def test_empty_pending_returns_empty_list(self, tmp_feedback):
        from adelie.feedback_queue import read_pending
        assert read_pending() == []

    def test_format_empty_returns_empty_string(self, tmp_feedback):
        from adelie.feedback_queue import format_for_prompt
        assert format_for_prompt([]) == ""
