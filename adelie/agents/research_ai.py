"""
adelie/agents/research_ai.py

Research AI agent — performs web research and stores findings in the KB.

Uses Gemini's Google Search grounding to search the web for information
requested by Expert AI. Results are stored as KB documents for future
reference by all other agents.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from rich.console import Console

from adelie.config import WORKSPACE_PATH, KB_CATEGORIES
from adelie.kb import retriever
from adelie.llm_client import generate
from adelie.web_search import search as web_search

console = Console()

RESEARCH_LOG_ROOT = WORKSPACE_PATH.parent / "research"

MAX_ANSWER_LENGTH = 3000  # Truncate long answers for KB docs


def run(
    queries: list[dict],
    max_queries: int = 5,
) -> list[dict]:
    """
    Run Research AI for a list of research queries.

    Args:
        queries: List of research query dicts from Expert AI.
                 Each: {"topic": str, "context": str, "category": str}
        max_queries: Maximum number of queries to execute (cost limit).

    Returns:
        List of result dicts:
        [{"topic": str, "kb_path": str, "summary": str, "sources": [...]}]
    """
    retriever.ensure_workspace()

    if not queries:
        return []

    # Limit queries
    queries = queries[:max_queries]

    console.print(
        f"[bold blue]🔍 Research AI[/bold blue] — "
        f"{len(queries)} quer{'y' if len(queries) == 1 else 'ies'} to research"
    )

    results = []

    for i, q in enumerate(queries):
        topic = q.get("topic", "").strip()
        context = q.get("context", "")
        category = q.get("category", "dependencies").strip().rstrip("/")

        if not topic:
            continue

        # Validate category
        if category not in KB_CATEGORIES:
            category = "dependencies"  # Default

        console.print(
            f"[blue]  🔎 [{i + 1}/{len(queries)}][/blue] {topic[:60]}…"
        )

        # Perform web search
        search_result = web_search(query=topic, context=context)

        answer = search_result.get("answer", "")
        sources = search_result.get("sources", [])
        search_queries = search_result.get("search_queries", [])
        grounded = search_result.get("grounded", False)

        if not answer:
            console.print(f"[dim]    ⏭  No results for: {topic[:40]}[/dim]")
            continue

        # Build KB document
        filename = _topic_to_filename(topic)
        doc_content = _build_kb_document(
            topic=topic,
            context=context,
            answer=answer,
            sources=sources,
            search_queries=search_queries,
            grounded=grounded,
        )

        # Write to KB
        kb_path = f"{category}/{filename}"
        out_path = WORKSPACE_PATH / category / filename
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(doc_content, encoding="utf-8")

        # Update KB index
        tags = ["research", "web_sourced"] if grounded else ["research", "llm_knowledge"]
        summary = f"Research: {topic[:80]}"
        retriever.update_index(kb_path, tags=tags, summary=summary)

        console.print(
            f"[green]    ✓ Saved[/green] {kb_path} "
            f"({len(sources)} source{'s' if len(sources) != 1 else ''})"
        )

        results.append({
            "topic": topic,
            "kb_path": kb_path,
            "summary": summary,
            "sources": sources,
            "grounded": grounded,
        })

    # Save research log
    _save_research_log(results)

    console.print(
        f"[bold blue]🔍 Research AI[/bold blue] — "
        f"{len(results)} result(s) saved to KB"
    )

    return results


def _topic_to_filename(topic: str) -> str:
    """Convert a research topic to a safe KB filename."""
    import re
    # Take first 40 chars, lowercase, replace non-alnum with underscores
    name = topic[:40].lower().strip()
    name = re.sub(r"[^a-z0-9가-힣]+", "_", name)
    name = name.strip("_")
    if not name:
        name = "research"
    return f"research_{name}.md"


def _build_kb_document(
    topic: str,
    context: str,
    answer: str,
    sources: list[dict],
    search_queries: list[str],
    grounded: bool,
) -> str:
    """Build a structured KB document from research results."""
    ts = datetime.now().isoformat(timespec="seconds")

    # Truncate answer if too long
    if len(answer) > MAX_ANSWER_LENGTH:
        answer = answer[:MAX_ANSWER_LENGTH] + "\n\n... (truncated)"

    doc = f"""<!-- tags: research, {'web_sourced' if grounded else 'llm_knowledge'} -->
<!-- summary: Research: {topic[:80]} -->
<!-- updated: {ts} -->
<!-- grounded: {grounded} -->

# 🔍 {topic}

**Researched**: {ts}
**Grounded**: {"Yes (Google Search)" if grounded else "No (LLM knowledge only)"}
{f"**Context**: {context}" if context else ""}

## Findings

{answer}
"""

    if sources:
        doc += "\n## Sources\n\n"
        for j, src in enumerate(sources, 1):
            title = src.get("title", "Unknown")
            url = src.get("url", "")
            doc += f"{j}. [{title}]({url})\n"

    if search_queries:
        doc += f"\n## Search Queries\n\n"
        for sq in search_queries:
            doc += f"- `{sq}`\n"

    return doc


def _save_research_log(results: list[dict]) -> None:
    """Save a summary log of research performed this cycle."""
    if not results:
        return

    RESEARCH_LOG_ROOT.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = RESEARCH_LOG_ROOT / f"log_{ts}.json"

    log_data = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "total_queries": len(results),
        "grounded_count": sum(1 for r in results if r.get("grounded")),
        "results": [
            {
                "topic": r["topic"],
                "kb_path": r["kb_path"],
                "sources_count": len(r.get("sources", [])),
                "grounded": r.get("grounded", False),
            }
            for r in results
        ],
    }

    log_path.write_text(json.dumps(log_data, indent=2, ensure_ascii=False), encoding="utf-8")

    # Keep only last 20 logs
    logs = sorted(RESEARCH_LOG_ROOT.glob("log_*.json"))
    if len(logs) > 20:
        for old in logs[:-20]:
            old.unlink()
