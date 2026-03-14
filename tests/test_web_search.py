"""tests/test_web_search.py — Tests for the web search module."""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest


class TestWebSearch:
    def test_search_gemini_returns_result(self, monkeypatch):
        """Test Gemini search via dispatch."""
        monkeypatch.setattr("adelie.web_search.LLM_PROVIDER", "gemini")

        mock_result = {
            "answer": "This is the grounded answer.",
            "sources": [{"title": "example.com", "url": "https://example.com"}],
            "search_queries": ["test query"],
            "grounded": True,
        }

        with patch("adelie.web_search._search_gemini", return_value=mock_result):
            from adelie.web_search import search
            result = search("test query")

        assert result["grounded"] is True
        assert len(result["sources"]) == 1
        assert result["answer"] == "This is the grounded answer."

    def test_ollama_fallback_flags_not_grounded(self, monkeypatch):
        """Ollama fallback should return grounded=False."""
        monkeypatch.setattr("adelie.web_search.LLM_PROVIDER", "ollama")
        monkeypatch.setattr("adelie.web_search.OLLAMA_MODEL", "llama3")
        monkeypatch.setattr("adelie.web_search.OLLAMA_BASE_URL", "http://localhost:11434")

        import requests

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "LLM knowledge answer"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20},
        }
        mock_resp.raise_for_status = MagicMock()

        with patch.object(requests, "post", return_value=mock_resp):
            from adelie.web_search import _search_ollama_fallback
            result = _search_ollama_fallback("test query")

        assert result["grounded"] is False
        assert result["answer"] == "LLM knowledge answer"
        assert result["sources"] == []

    def test_empty_result_on_error(self):
        """_empty_result should return a valid but empty structure."""
        from adelie.web_search import _empty_result
        result = _empty_result("test", error="API timeout")
        assert result["grounded"] is False
        assert "API timeout" in result["answer"]
        assert result["sources"] == []

    def test_search_dispatches_by_provider(self, monkeypatch):
        """search() should call Gemini for gemini provider."""
        monkeypatch.setattr("adelie.web_search.LLM_PROVIDER", "gemini")
        from adelie.web_search import search

        with patch("adelie.web_search._search_gemini") as mock_gemini:
            mock_gemini.return_value = {"answer": "ok", "sources": [], "search_queries": [], "grounded": False}
            result = search("test")
            mock_gemini.assert_called_once()

    def test_search_dispatches_ollama(self, monkeypatch):
        """search() should call Ollama fallback for ollama provider."""
        monkeypatch.setattr("adelie.web_search.LLM_PROVIDER", "ollama")
        from adelie.web_search import search

        with patch("adelie.web_search._search_ollama_fallback") as mock_ollama:
            mock_ollama.return_value = {"answer": "ok", "sources": [], "search_queries": [], "grounded": False}
            result = search("test")
            mock_ollama.assert_called_once()
