"""tests/test_research_ai.py — Tests for the Research AI agent."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest


@pytest.fixture
def tmp_workspace(tmp_path, monkeypatch):
    import adelie.config as cfg
    ws = tmp_path / ".adelie" / "kb"
    ws.mkdir(parents=True)
    for cat in ["skills", "dependencies", "errors", "logic", "exports", "maintenance"]:
        (ws / cat).mkdir()
    monkeypatch.setattr(cfg, "WORKSPACE_PATH", ws)
    monkeypatch.setattr(cfg, "ADELIE_ROOT", ws.parent)
    monkeypatch.setattr(cfg, "PROJECT_ROOT", tmp_path)

    # Mock retriever
    monkeypatch.setattr("adelie.kb.retriever.ensure_workspace", lambda: None)
    monkeypatch.setattr("adelie.kb.retriever.update_index", lambda *a, **kw: None)

    return ws


class TestResearchAI:
    def test_run_with_queries(self, tmp_workspace):
        """Research AI should process queries and write KB docs."""
        mock_search = {
            "answer": "Next.js 15 has server actions built-in.",
            "sources": [{"title": "nextjs.org", "url": "https://nextjs.org/docs"}],
            "search_queries": ["Next.js 15 server actions"],
            "grounded": True,
        }

        with patch("adelie.agents.research_ai.web_search", return_value=mock_search):
            from adelie.agents.research_ai import run
            results = run(
                queries=[{
                    "topic": "Next.js 15 server actions",
                    "context": "Building API layer",
                    "category": "dependencies",
                }],
                max_queries=5,
            )

        assert len(results) == 1
        assert results[0]["topic"] == "Next.js 15 server actions"
        assert results[0]["grounded"] is True
        assert "dependencies/" in results[0]["kb_path"]

        # Check file was written
        kb_files = list((tmp_workspace / "dependencies").glob("research_*.md"))
        assert len(kb_files) == 1
        content = kb_files[0].read_text(encoding="utf-8")
        assert "Next.js 15" in content
        assert "nextjs.org" in content

    def test_empty_queries_returns_empty(self, tmp_workspace):
        """Empty query list should return empty results."""
        from adelie.agents.research_ai import run
        results = run(queries=[], max_queries=5)
        assert results == []

    def test_max_queries_limit(self, tmp_workspace):
        """Should respect max_queries limit."""
        queries = [
            {"topic": f"Topic {i}", "context": "", "category": "dependencies"}
            for i in range(10)
        ]

        mock_search = {
            "answer": "Answer",
            "sources": [],
            "search_queries": ["query"],
            "grounded": False,
        }

        with patch("adelie.agents.research_ai.web_search", return_value=mock_search):
            from adelie.agents.research_ai import run
            results = run(queries=queries, max_queries=3)

        assert len(results) == 3

    def test_invalid_category_defaults(self, tmp_workspace):
        """Invalid category should default to dependencies."""
        mock_search = {
            "answer": "Some answer",
            "sources": [],
            "search_queries": [],
            "grounded": False,
        }

        with patch("adelie.agents.research_ai.web_search", return_value=mock_search):
            from adelie.agents.research_ai import run
            results = run(
                queries=[{"topic": "Test", "context": "", "category": "invalid_cat"}],
            )

        assert len(results) == 1
        assert results[0]["kb_path"].startswith("dependencies/")

    def test_topic_to_filename(self):
        """Filename generation should be safe and descriptive."""
        from adelie.agents.research_ai import _topic_to_filename
        assert _topic_to_filename("Next.js 15 server actions").endswith(".md")
        assert _topic_to_filename("Next.js 15 server actions").startswith("research_")
        assert "/" not in _topic_to_filename("path/with/slashes")

    def test_build_kb_document_content(self):
        """KB document should contain topic, answer, and sources."""
        from adelie.agents.research_ai import _build_kb_document
        doc = _build_kb_document(
            topic="Test Topic",
            context="Test context",
            answer="The answer is 42.",
            sources=[{"title": "wiki", "url": "https://wiki.org"}],
            search_queries=["test query"],
            grounded=True,
        )
        assert "Test Topic" in doc
        assert "The answer is 42." in doc
        assert "wiki" in doc
        assert "web_sourced" in doc

    def test_research_log_saved(self, tmp_workspace):
        """Research log should be saved after execution."""
        mock_search = {
            "answer": "Result",
            "sources": [],
            "search_queries": [],
            "grounded": False,
        }

        with patch("adelie.agents.research_ai.web_search", return_value=mock_search):
            from adelie.agents.research_ai import run, RESEARCH_LOG_ROOT
            # Patch RESEARCH_LOG_ROOT to tmp
            import adelie.agents.research_ai as rai
            original = rai.RESEARCH_LOG_ROOT
            rai.RESEARCH_LOG_ROOT = tmp_workspace.parent / "research"
            try:
                results = run(queries=[{"topic": "Test", "context": "", "category": "dependencies"}])
            finally:
                rai.RESEARCH_LOG_ROOT = original

        log_dir = tmp_workspace.parent / "research"
        if log_dir.exists():
            logs = list(log_dir.glob("log_*.json"))
            assert len(logs) == 1
            data = json.loads(logs[0].read_text(encoding="utf-8"))
            assert data["total_queries"] == 1
