"""
adelie/web_search.py

Web search via Gemini's Grounding with Google Search.
Provides a unified search() function that:
  - Gemini: uses google_search grounding tool for real-time web results
  - Ollama: falls back to LLM internal knowledge (no web search)
"""

from __future__ import annotations

import json
import re
from typing import Optional

from rich.console import Console

from adelie.config import (
    BROWSER_SEARCH_ENABLED,
    BROWSER_SEARCH_MAX_PAGES,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    LLM_PROVIDER,
    OLLAMA_API_KEY,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
)

console = Console()


def search(
    query: str,
    context: str = "",
    model: str | None = None,
) -> dict:
    """
    Perform a grounded web search using Gemini's Google Search tool.

    Args:
        query: The search query / research question.
        context: Additional context for why this search is needed.
        model: Override model (default: use configured model).

    Returns:
        {
            "answer": str,           # Synthesized answer from search results
            "sources": [             # List of web sources used
                {"title": str, "url": str}
            ],
            "search_queries": [str], # Actual queries sent to Google
            "grounded": bool,        # True if real web search was used
        }
    """
    if LLM_PROVIDER == "gemini":
        return _search_gemini(query, context, model)
    else:
        return _search_ollama_fallback(query, context, model)


def _search_gemini(
    query: str,
    context: str = "",
    model: str | None = None,
) -> dict:
    """Search via Gemini with Google Search grounding."""
    try:
        from google import genai
        from google.genai import types as genai_types
    except ImportError:
        console.print("[red]❌ google-genai not installed[/red]")
        return _empty_result(query, error="google-genai not installed")

    client = genai.Client(api_key=GEMINI_API_KEY)
    use_model = model or GEMINI_MODEL

    # Build the grounding tool
    grounding_tool = genai_types.Tool(
        google_search=genai_types.GoogleSearch()
    )

    prompt = f"""Research the following topic and provide a comprehensive, factual answer.

Topic: {query}
{"Context: " + context if context else ""}

Provide:
1. A detailed, factual answer based on search results
2. Key findings and insights
3. Any relevant code examples, API references, or best practices

Be thorough and cite specific facts from your sources."""

    try:
        response = client.models.generate_content(
            model=use_model,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                tools=[grounding_tool],
                temperature=0.2,
            ),
        )

        # Extract answer text
        answer = response.text.strip() if response.text else ""

        sources = []
        search_queries = []

        # Parse grounding metadata
        if response.candidates:
            candidate = response.candidates[0]
            metadata = getattr(candidate, "grounding_metadata", None)

            if metadata:
                # Extract search queries
                if hasattr(metadata, "web_search_queries") and metadata.web_search_queries:
                    search_queries = list(metadata.web_search_queries)

                # Extract source URLs
                if hasattr(metadata, "grounding_chunks") and metadata.grounding_chunks:
                    for chunk in metadata.grounding_chunks:
                        if hasattr(chunk, "web") and chunk.web:
                            sources.append({
                                "title": getattr(chunk.web, "title", ""),
                                "url": getattr(chunk.web, "uri", ""),
                            })

        # Track token usage
        try:
            from adelie.llm_client import _record_usage
            meta = response.usage_metadata
            _record_usage(
                prompt=getattr(meta, "prompt_token_count", 0) or 0,
                completion=getattr(meta, "candidates_token_count", 0) or 0,
            )
        except Exception:
            pass

        console.print(
            f"[bold blue]🔍 Research[/bold blue] — "
            f"{len(sources)} source(s), "
            f"{len(search_queries)} search quer{'y' if len(search_queries) == 1 else 'ies'}"
        )

        return {
            "answer": answer,
            "sources": sources,
            "search_queries": search_queries,
            "grounded": bool(sources),
        }

    except Exception as e:
        err_str = str(e)
        # If rate-limited and browser search is enabled, fall back
        if ("429" in err_str or "RESOURCE_EXHAUSTED" in err_str) and BROWSER_SEARCH_ENABLED:
            console.print(
                "[yellow]⚡ Gemini Search quota exceeded — "
                "falling back to browser search…[/yellow]"
            )
            return _search_browser_fallback(query, context)
        console.print(f"[red]❌ Gemini Search error: {e}[/red]")
        return _empty_result(query, error=str(e))


def _search_browser_fallback(
    query: str,
    context: str = "",
) -> dict:
    """Fallback: use Playwright headless browser to search Google directly."""
    try:
        from adelie.browser_search import browser_search
        return browser_search(
            query=query,
            context=context,
            max_pages=BROWSER_SEARCH_MAX_PAGES,
        )
    except Exception as e:
        console.print(f"[red]❌ Browser search fallback also failed: {e}[/red]")
        return _empty_result(query, error=f"Browser fallback failed: {e}")


def _search_ollama_fallback(
    query: str,
    context: str = "",
    model: str | None = None,
) -> dict:
    """Fallback for Ollama — no web search, LLM knowledge only."""
    import requests

    console.print("[dim]⚠️  Ollama: no web search — using LLM knowledge only[/dim]")

    use_model = model or OLLAMA_MODEL
    url = f"{OLLAMA_BASE_URL}/v1/chat/completions"

    prompt = f"""Research the following topic based on your training knowledge.

Topic: {query}
{"Context: " + context if context else ""}

Provide a detailed, factual answer. Note that you don't have access to
real-time information, so state clearly when information might be outdated."""

    try:
        headers = {"Content-Type": "application/json"}
        if OLLAMA_API_KEY:
            headers["Authorization"] = f"Bearer {OLLAMA_API_KEY}"

        resp = requests.post(
            url,
            headers=headers,
            json={
                "model": use_model,
                "messages": [
                    {"role": "system", "content": "You are a research assistant. Provide thorough, factual answers."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
                "stream": False,
            },
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        answer = data["choices"][0]["message"]["content"].strip()

        return {
            "answer": answer,
            "sources": [],
            "search_queries": [query],
            "grounded": False,
        }
    except Exception as e:
        console.print(f"[red]❌ Ollama Search error: {e}[/red]")
        return _empty_result(query, error=str(e))


def _empty_result(query: str, error: str = "") -> dict:
    """Return an empty result on failure."""
    return {
        "answer": f"Research failed for: {query}. Error: {error}" if error else "",
        "sources": [],
        "search_queries": [query],
        "grounded": False,
    }
