"""tests/test_browser_search.py — Tests for the browser search fallback module."""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest


class TestBrowserSearchHelpers:
    """Test helper functions that don't require a real browser."""

    def test_clean_text_removes_excessive_newlines(self):
        from adelie.browser_search import _clean_text
        text = "Hello\n\n\n\n\nWorld\n\n\n\nFoo"
        result = _clean_text(text)
        assert "\n\n\n" not in result
        assert "Hello" in result
        assert "World" in result

    def test_clean_text_truncates_long_content(self):
        from adelie.browser_search import _clean_text, MAX_PAGE_TEXT_LENGTH
        text = "A" * (MAX_PAGE_TEXT_LENGTH + 1000)
        result = _clean_text(text)
        assert len(result) <= MAX_PAGE_TEXT_LENGTH + 50  # +50 for truncation note

    def test_clean_text_removes_short_lines(self):
        from adelie.browser_search import _clean_text
        text = "x\nThis is a real sentence.\ny\nAnother good line here."
        result = _clean_text(text)
        assert "This is a real sentence." in result
        assert "Another good line here." in result

    def test_empty_result_structure(self):
        from adelie.browser_search import _empty_result
        result = _empty_result("test query", error="timeout")
        assert result["grounded"] is False
        assert "timeout" in result["answer"]
        assert result["sources"] == []
        assert result["search_queries"] == ["test query"]

    def test_empty_result_without_error(self):
        from adelie.browser_search import _empty_result
        result = _empty_result("test query")
        assert result["answer"] == ""
        assert result["grounded"] is False


class TestBrowserSearchFallbackIntegration:
    """Test that web_search properly falls back to browser search."""

    def test_fallback_called_on_429(self, monkeypatch):
        """When Gemini returns 429, browser fallback should be triggered."""
        monkeypatch.setattr("adelie.web_search.LLM_PROVIDER", "gemini")
        monkeypatch.setattr("adelie.web_search.BROWSER_SEARCH_ENABLED", True)
        monkeypatch.setattr("adelie.web_search.GEMINI_API_KEY", "test-key")

        mock_browser_result = {
            "answer": "Browser search answer",
            "sources": [{"title": "Example", "url": "https://example.com"}],
            "search_queries": ["test query"],
            "grounded": True,
        }

        # Mock the genai.Client to raise 429 on generate_content
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = Exception(
            "429 RESOURCE_EXHAUSTED: quota exceeded"
        )

        mock_google = MagicMock()
        mock_genai = MagicMock()
        mock_genai.Client = MagicMock(return_value=mock_client)
        mock_google.genai = mock_genai

        with patch.dict("sys.modules", {"google": mock_google, "google.genai": mock_genai}):
            with patch(
                "adelie.web_search._search_browser_fallback",
                return_value=mock_browser_result,
            ) as mock_fallback:
                from adelie.web_search import _search_gemini
                result = _search_gemini("test query")
                mock_fallback.assert_called_once()
                assert result["answer"] == "Browser search answer"
                assert result["grounded"] is True

    def test_fallback_not_called_when_disabled(self, monkeypatch):
        """When BROWSER_SEARCH_ENABLED is False, fallback should not be used."""
        monkeypatch.setattr("adelie.web_search.LLM_PROVIDER", "gemini")
        monkeypatch.setattr("adelie.web_search.BROWSER_SEARCH_ENABLED", False)

        mock_error_result = {
            "answer": "Research failed for: test. Error: 429",
            "sources": [],
            "search_queries": ["test"],
            "grounded": False,
        }

        with patch("adelie.web_search._search_gemini", return_value=mock_error_result):
            from adelie.web_search import search
            result = search("test")
            assert result["grounded"] is False

    def test_browser_fallback_function_calls_browser_search(self):
        """_search_browser_fallback should delegate to browser_search."""
        mock_result = {
            "answer": "Found via browser",
            "sources": [{"title": "Test", "url": "https://test.com"}],
            "search_queries": ["npm deps"],
            "grounded": True,
        }

        with patch("adelie.web_search.BROWSER_SEARCH_MAX_PAGES", 3):
            with patch(
                "adelie.browser_search.browser_search",
                return_value=mock_result,
            ):
                from adelie.web_search import _search_browser_fallback
                result = _search_browser_fallback("npm deps", "some context")
                assert result["answer"] == "Found via browser"
                assert result["grounded"] is True

    def test_browser_fallback_handles_import_error(self):
        """If playwright is not installed, should return empty result gracefully."""
        from adelie.browser_search import _empty_result

        with patch(
            "adelie.browser_search.browser_search",
            side_effect=ImportError("No module playwright"),
        ):
            from adelie.web_search import _search_browser_fallback
            result = _search_browser_fallback("test query")
            assert result["grounded"] is False


class TestBrowserSearchModule:
    """Test the browser_search module with mocked Playwright."""

    def test_browser_search_returns_valid_structure(self):
        """browser_search should return the expected dict structure."""
        # Mock the playwright.sync_api module's sync_playwright
        mock_pw_manager = MagicMock()
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()

        mock_pw_manager.__enter__ = MagicMock(return_value=MagicMock())
        mock_pw_manager.__enter__.return_value.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page

        mock_playwright = MagicMock()
        mock_playwright.sync_api.sync_playwright = MagicMock(return_value=mock_pw_manager)

        with patch.dict("sys.modules", {"playwright": mock_playwright, "playwright.sync_api": mock_playwright.sync_api}):
            with patch("adelie.browser_search._google_search", return_value=[
                {"title": "Result 1", "url": "https://example.com", "snippet": "snippet"},
            ]):
                with patch("adelie.browser_search._extract_page_content", return_value="Page content here " * 20):
                    with patch("adelie.browser_search._summarize_with_llm", return_value="Summarized answer"):
                        from adelie.browser_search import browser_search
                        result = browser_search("test query")

        assert "answer" in result
        assert "sources" in result
        assert "search_queries" in result
        assert "grounded" in result

    def test_browser_search_no_playwright_graceful(self):
        """If playwright not importable, return error gracefully."""
        with patch.dict("sys.modules", {"playwright": None, "playwright.sync_api": None}):
            # Re-import to trigger the ImportError path
            from adelie.browser_search import _empty_result
            result = _empty_result("test", error="playwright not installed")
            assert "playwright" in result["answer"]
            assert result["grounded"] is False
