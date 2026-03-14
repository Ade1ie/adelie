"""
adelie/browser_search.py

Browser-based web search using Playwright.
Searches Google via a headless Chromium browser, visits top result pages,
extracts their content, and uses LLM to synthesize a final answer.

This module is used as a fallback when the Gemini Search Grounding API
is unavailable (e.g. 429 RESOURCE_EXHAUSTED).
"""

from __future__ import annotations

import re
import time
from typing import Optional
from urllib.parse import quote_plus

from rich.console import Console

console = Console()

# ── Content extraction selectors ─────────────────────────────────────────────
# Priority order for main content areas
_CONTENT_SELECTORS = [
    "article",
    "main",
    "[role='main']",
    ".post-content",
    ".article-content",
    ".entry-content",
    ".post-body",
    ".markdown-body",       # GitHub
    "#answer",              # Stack Overflow
    ".answer",              # Stack Overflow
    ".s-prose",             # Stack Overflow new
    "#content",
    ".content",
    "#readme",              # GitHub README
]

# Elements to remove before extracting text
_REMOVE_SELECTORS = [
    "nav", "header", "footer",
    ".sidebar", "#sidebar", "aside",
    ".nav", ".menu", ".breadcrumb",
    ".advertisement", ".ad", ".ads",
    ".cookie-banner", ".popup",
    "script", "style", "noscript",
    ".comments", "#comments",
    ".social-share", ".share-buttons",
    ".related-posts", ".recommended",
]

MAX_PAGE_TEXT_LENGTH = 3000   # Max chars per page
MAX_TOTAL_CONTENT = 10000    # Max chars across all pages for LLM
SEARCH_TIMEOUT_MS = 15000    # 15s per page load
NAVIGATION_TIMEOUT_MS = 20000


def browser_search(
    query: str,
    context: str = "",
    max_results: int = 5,
    max_pages: int = 3,
) -> dict:
    """
    Perform a web search using a headless browser.

    1. Open Google, search for the query
    2. Parse result links (up to max_results)
    3. Visit top pages (up to max_pages) and extract content
    4. Send collected content to LLM for synthesis

    Args:
        query: The search query.
        context: Additional context for the search.
        max_results: Max number of search result links to collect.
        max_pages: Max number of pages to actually visit and read.

    Returns:
        Same structure as web_search.search():
        {
            "answer": str,
            "sources": [{"title": str, "url": str}],
            "search_queries": [str],
            "grounded": bool,
        }
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        console.print(
            "[red]❌ playwright not installed. "
            "Run: pip install playwright && playwright install chromium[/red]"
        )
        return _empty_result(query, error="playwright not installed")

    console.print(
        f"[bold cyan]🌐 Browser Search[/bold cyan] — "
        f"Searching Google for: {query[:60]}…"
    )

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser_context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 800},
                locale="en-US",
            )
            browser_context.set_default_timeout(NAVIGATION_TIMEOUT_MS)

            page = browser_context.new_page()

            # Step 1: Google search
            search_results = _google_search(page, query, max_results)

            if not search_results:
                browser.close()
                console.print("[yellow]  ⚠️  No search results found[/yellow]")
                return _empty_result(query, error="No search results found")

            console.print(
                f"[cyan]  📋 Found {len(search_results)} results, "
                f"visiting top {min(max_pages, len(search_results))} pages…[/cyan]"
            )

            # Step 2: Visit pages and extract content
            pages_content = []
            sources = []

            for i, result in enumerate(search_results[:max_pages]):
                url = result["url"]
                title = result["title"]

                console.print(f"[dim]    → [{i+1}] {title[:50]}…[/dim]")

                content = _extract_page_content(page, url)
                if content and len(content.strip()) > 100:
                    pages_content.append({
                        "title": title,
                        "url": url,
                        "content": content[:MAX_PAGE_TEXT_LENGTH],
                    })
                    sources.append({"title": title, "url": url})
                else:
                    # Still record as source even if content extraction failed
                    snippet = result.get("snippet", "")
                    if snippet:
                        pages_content.append({
                            "title": title,
                            "url": url,
                            "content": snippet,
                        })
                        sources.append({"title": title, "url": url})

            browser.close()

            if not pages_content:
                return _empty_result(query, error="Could not extract content from any page")

            # Step 3: Synthesize with LLM
            console.print(
                f"[cyan]  🤖 Synthesizing {len(pages_content)} page(s) with LLM…[/cyan]"
            )
            answer = _summarize_with_llm(query, context, pages_content)

            console.print(
                f"[bold cyan]🌐 Browser Search[/bold cyan] — "
                f"Done ({len(sources)} sources)"
            )

            return {
                "answer": answer,
                "sources": sources,
                "search_queries": [query],
                "grounded": True,
            }

    except Exception as e:
        console.print(f"[red]❌ Browser search error: {e}[/red]")
        return _empty_result(query, error=str(e))


def _google_search(page, query: str, max_results: int = 5) -> list[dict]:
    """
    Perform a Google search and parse the result links.

    Returns:
        List of {"title": str, "url": str, "snippet": str}
    """
    search_url = f"https://www.google.com/search?q={quote_plus(query)}&hl=en"

    try:
        page.goto(search_url, wait_until="domcontentloaded", timeout=SEARCH_TIMEOUT_MS)
        # Wait for results to load
        page.wait_for_selector("div#search", timeout=5000)
    except Exception as e:
        console.print(f"[yellow]  ⚠️  Google search page load failed: {e}[/yellow]")
        return []

    # Small delay to let results render
    time.sleep(1)

    results = []

    try:
        # Parse search result entries
        # Google's result structure: div.g contains each result
        result_elements = page.query_selector_all("div.g")

        for elem in result_elements[:max_results * 2]:  # Check more elements than needed
            try:
                # Find the link
                link_el = elem.query_selector("a[href]")
                if not link_el:
                    continue

                href = link_el.get_attribute("href") or ""

                # Skip non-http links, Google internal links
                if not href.startswith("http"):
                    continue
                if "google.com" in href and "/search" in href:
                    continue
                if "accounts.google" in href:
                    continue

                # Get title
                title_el = elem.query_selector("h3")
                title = title_el.inner_text().strip() if title_el else ""
                if not title:
                    continue

                # Get snippet
                snippet = ""
                snippet_el = elem.query_selector(
                    "div[data-sncf], div.VwiC3b, span.aCOpRe, div.IsZvec"
                )
                if snippet_el:
                    snippet = snippet_el.inner_text().strip()

                results.append({
                    "title": title,
                    "url": href,
                    "snippet": snippet,
                })

                if len(results) >= max_results:
                    break

            except Exception:
                continue

    except Exception as e:
        console.print(f"[yellow]  ⚠️  Failed to parse search results: {e}[/yellow]")

    return results


def _extract_page_content(page, url: str) -> str:
    """
    Visit a URL and extract the main text content.

    Uses a priority-based selector strategy to find the main content area,
    removes noise elements, and returns clean text.
    """
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=SEARCH_TIMEOUT_MS)
        # Brief wait for dynamic content
        time.sleep(1)
    except Exception as e:
        console.print(f"[dim]      ⚠️  Page load failed: {str(e)[:50]}[/dim]")
        return ""

    try:
        # Remove noise elements first
        for selector in _REMOVE_SELECTORS:
            try:
                page.evaluate(
                    f"""() => {{
                        document.querySelectorAll('{selector}').forEach(el => el.remove());
                    }}"""
                )
            except Exception:
                pass

        # Try priority content selectors
        for selector in _CONTENT_SELECTORS:
            try:
                element = page.query_selector(selector)
                if element:
                    text = element.inner_text()
                    if text and len(text.strip()) > 100:
                        return _clean_text(text)
            except Exception:
                continue

        # Fallback: use body
        try:
            body = page.query_selector("body")
            if body:
                text = body.inner_text()
                return _clean_text(text)
        except Exception:
            pass

    except Exception as e:
        console.print(f"[dim]      ⚠️  Content extraction failed: {str(e)[:50]}[/dim]")

    return ""


def _clean_text(text: str) -> str:
    """Clean extracted text by removing excessive whitespace and noise."""
    # Remove excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Remove lines that are just whitespace
    lines = [line.strip() for line in text.split("\n")]
    lines = [line for line in lines if line]
    # Remove very short lines that are likely UI elements
    lines = [line for line in lines if len(line) > 2 or line in ("", "-", "•")]
    text = "\n".join(lines)
    # Truncate
    if len(text) > MAX_PAGE_TEXT_LENGTH:
        text = text[:MAX_PAGE_TEXT_LENGTH] + "\n\n... (truncated)"
    return text.strip()


def _summarize_with_llm(
    query: str,
    context: str,
    pages_content: list[dict],
) -> str:
    """
    Use the configured LLM to synthesize search results into a coherent answer.
    """
    from adelie.llm_client import generate

    # Build the content section
    content_parts = []
    total_len = 0
    for i, pc in enumerate(pages_content, 1):
        part = f"### Source {i}: {pc['title']}\nURL: {pc['url']}\n\n{pc['content']}"
        if total_len + len(part) > MAX_TOTAL_CONTENT:
            # Truncate this part to fit
            remaining = MAX_TOTAL_CONTENT - total_len
            if remaining > 200:
                part = part[:remaining] + "\n\n... (truncated)"
            else:
                break
        content_parts.append(part)
        total_len += len(part)

    all_content = "\n\n---\n\n".join(content_parts)

    system_prompt = (
        "You are a research assistant. Synthesize the web search results below "
        "into a comprehensive, factual answer. Include specific details, code "
        "examples, and best practices where relevant. Cite which source the "
        "information came from. Respond in the same language as the query."
    )

    user_prompt = f"""Research query: {query}
{"Context: " + context if context else ""}

## Web Search Results

{all_content}

## Instructions

Based on the search results above:
1. Provide a detailed, factual answer to the research query
2. Include key findings, code examples, and best practices
3. Note which sources support each finding
4. If the results are insufficient, state what additional research might be needed"""

    try:
        answer = generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.2,
        )
        # Strip any JSON formatting since generate() might return JSON
        # We want plain text here
        answer = answer.strip()
        if answer.startswith("{") or answer.startswith('"'):
            try:
                import json
                parsed = json.loads(answer)
                if isinstance(parsed, dict):
                    answer = parsed.get("answer", parsed.get("response", str(parsed)))
                elif isinstance(parsed, str):
                    answer = parsed
            except (json.JSONDecodeError, ValueError):
                pass
        return answer
    except Exception as e:
        console.print(f"[red]  ❌ LLM summarization failed: {e}[/red]")
        # Return raw content as fallback
        return f"(LLM summarization failed. Raw content below)\n\n{all_content[:2000]}"


def _empty_result(query: str, error: str = "") -> dict:
    """Return an empty result on failure."""
    return {
        "answer": f"Browser search failed for: {query}. Error: {error}" if error else "",
        "sources": [],
        "search_queries": [query],
        "grounded": False,
    }
