"""
adelie/kb/retriever.py

Knowledge Base retriever module.
Expert AI uses this to situationally select and read only relevant KB files
instead of loading the entire workspace into its context window.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from adelie.config import KB_CATEGORIES, SITUATION_CATEGORY_MAP, WORKSPACE_PATH


# ── Index path ───────────────────────────────────────────────────────────────
INDEX_FILE = WORKSPACE_PATH / "index.json"


# ── Setup ────────────────────────────────────────────────────────────────────

def ensure_workspace() -> None:
    """Create workspace directory and all KB category folders if missing."""
    WORKSPACE_PATH.mkdir(parents=True, exist_ok=True)
    for cat in KB_CATEGORIES:
        (WORKSPACE_PATH / cat).mkdir(exist_ok=True)
    if not INDEX_FILE.exists():
        INDEX_FILE.write_text(json.dumps({}, indent=2), encoding="utf-8")


# ── Index management ─────────────────────────────────────────────────────────

def get_index() -> dict:
    """Return the full KB index as a dictionary."""
    ensure_workspace()
    try:
        return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def update_index(relative_path: str, tags: list[str], summary: str) -> None:
    """
    Upsert a KB file entry in index.json.
    Also updates the embedding for semantic search.

    Args:
        relative_path: Path relative to WORKSPACE_PATH (e.g. 'skills/how_to_retry.md')
        tags:          List of keyword tags for retrieval
        summary:       One-line description of the file content
    """
    index = get_index()
    index[relative_path] = {
        "tags": tags,
        "summary": summary,
        "updated": datetime.now().isoformat(timespec="seconds"),
    }
    INDEX_FILE.write_text(json.dumps(index, indent=2), encoding="utf-8")

    # Update embedding (async-safe, fails silently)
    try:
        from adelie.kb.embedding_store import update_embedding
        file_path = WORKSPACE_PATH / relative_path
        if file_path.exists():
            content = file_path.read_text(encoding="utf-8")
            update_embedding(relative_path, content, summary)
    except Exception:
        pass  # Embedding is optional — tag search still works


# ── Category listing ─────────────────────────────────────────────────────────

def list_categories() -> dict[str, int]:
    """Return a dict of {category_name: file_count} for all KB categories."""
    ensure_workspace()
    return {
        cat: len(list((WORKSPACE_PATH / cat).glob("*")))
        for cat in KB_CATEGORIES
    }


# ── Situational query ─────────────────────────────────────────────────────────

def query(situation: str, extra_tags: Optional[list[str]] = None) -> list[Path]:
    """
    Return a list of KB file Paths most relevant to the current situation.

    Args:
        situation:  One of the keys in SITUATION_CATEGORY_MAP
                    ('error', 'new_logic', 'export', 'maintenance', 'normal')
        extra_tags: Additional tags to filter by (optional)

    Returns:
        Ordered list of Path objects — most specific categories first.
    """
    categories = SITUATION_CATEGORY_MAP.get(situation, SITUATION_CATEGORY_MAP["normal"])
    index = get_index()
    selected: list[Path] = []

    # First pass: files in the relevant categories
    for cat in categories:
        cat_dir = WORKSPACE_PATH / cat
        for file_path in sorted(cat_dir.glob("*.md")):
            rel = file_path.relative_to(WORKSPACE_PATH).as_posix()
            entry = index.get(rel, {})
            file_tags = entry.get("tags", [])
            # If extra_tags provided, only include files that match at least one
            if extra_tags:
                if any(t in file_tags for t in extra_tags):
                    selected.append(file_path)
            else:
                selected.append(file_path)

    # Deduplicate while preserving order
    seen: set[Path] = set()
    deduped: list[Path] = []
    for p in selected:
        if p not in seen:
            seen.add(p)
            deduped.append(p)

    return deduped


# ── File reader ───────────────────────────────────────────────────────────────

def read_files(paths: list[Path]) -> str:
    """
    Load and concatenate KB file contents for prompt injection.

    Returns a formatted string suitable for inclusion in an AI prompt.
    """
    if not paths:
        return "(no relevant knowledge base files found for this situation)"

    blocks: list[str] = []
    for p in paths:
        if p.exists():
            relative = p.relative_to(WORKSPACE_PATH).as_posix()
            content = p.read_text(encoding="utf-8").strip()
            blocks.append(f"### [{relative}]\n{content}")

    return "\n\n---\n\n".join(blocks)


def get_index_summary() -> str:
    """Return a compact text summary of the KB index for prompt injection."""
    index = get_index()
    if not index:
        return "(Knowledge Base is empty)"
    lines = ["Current Knowledge Base index:"]
    for path, meta in index.items():
        tags = ", ".join(meta.get("tags", []))
        summary = meta.get("summary", "")
        lines.append(f"  • {path} [{tags}]: {summary}")
    return "\n".join(lines)


# ── Semantic query (hybrid: tag + embedding) ───────────────────────────────

def semantic_query(
    situation: str,
    query_text: str = "",
    extra_tags: Optional[list[str]] = None,
    max_results: int = 8,
) -> list[Path]:
    """
    Hybrid search: combines tag-based category matching with
    semantic embedding search for more accurate retrieval.

    Args:
        situation:   Current system situation (for tag-based search)
        query_text:  Natural language query for semantic matching
        extra_tags:  Additional tag filters
        max_results: Maximum number of files to return

    Returns:
        Ordered list of Path objects — best matches first.
    """
    # 1. Tag-based results (always available)
    tag_results = query(situation, extra_tags)

    # 2. Semantic results (if embeddings available)
    semantic_results: list[Path] = []
    if query_text:
        try:
            from adelie.kb.embedding_store import semantic_search
            search_query = f"situation: {situation}. {query_text}"
            matches = semantic_search(search_query, top_k=max_results)
            for rel_path, score in matches:
                full_path = WORKSPACE_PATH / rel_path
                if full_path.exists():
                    semantic_results.append(full_path)
        except Exception:
            pass  # Fall back to tag-only search

    # 3. Merge: semantic results first (higher signal), then tag results
    merged: list[Path] = []
    seen: set[Path] = set()

    for p in semantic_results:
        if p not in seen:
            seen.add(p)
            merged.append(p)

    for p in tag_results:
        if p not in seen:
            seen.add(p)
            merged.append(p)

    return merged[:max_results]


# ── Spec Chunk Query ──────────────────────────────────────────────────────────


def query_spec_chunks(
    query_text: str = "",
    spec_name: str = "",
    max_tokens: int = 4000,
    max_results: int = 10,
) -> list[Path]:
    """
    Retrieve the most relevant spec chunks for a given query,
    respecting a token budget.

    Uses semantic search (embedding similarity) when available,
    falls back to tag-based matching. Assembles the top chunks
    that fit within the token budget.

    Args:
        query_text:  Natural language query for semantic matching.
        spec_name:   Filter chunks by parent spec name (optional).
        max_tokens:  Maximum total tokens for returned chunks.
        max_results: Maximum number of chunks to return.

    Returns:
        Ordered list of chunk file Paths — most relevant first.
    """
    from adelie.context_compactor import estimate_tokens

    index = get_index()

    # Collect all spec chunk paths
    chunk_paths: list[Path] = []
    for rel_path, meta in index.items():
        tags = meta.get("tags", [])
        if "spec_chunk" not in tags:
            continue
        # Filter by spec name if provided
        if spec_name and spec_name not in tags and f"spec_{spec_name}" not in tags:
            continue
        full_path = WORKSPACE_PATH / rel_path
        if full_path.exists():
            chunk_paths.append(full_path)

    if not chunk_paths:
        # Fall back to non-chunked specs
        for rel_path, meta in index.items():
            tags = meta.get("tags", [])
            if "spec" in tags and "spec_chunk" not in tags:
                if spec_name and spec_name not in tags:
                    continue
                full_path = WORKSPACE_PATH / rel_path
                if full_path.exists():
                    chunk_paths.append(full_path)

    if not chunk_paths:
        return []

    # Try semantic ranking if query provided
    ranked_paths: list[Path] = []
    if query_text:
        try:
            from adelie.kb.embedding_store import semantic_search
            matches = semantic_search(query_text, top_k=max_results * 2)
            for rel_path, score in matches:
                full_path = WORKSPACE_PATH / rel_path
                if full_path in chunk_paths:
                    ranked_paths.append(full_path)
        except Exception:
            pass

    # Add remaining chunks not found by semantic search (in original order)
    seen = set(ranked_paths)
    for p in chunk_paths:
        if p not in seen:
            ranked_paths.append(p)

    # Assemble chunks within token budget
    selected: list[Path] = []
    total_tokens = 0

    for path in ranked_paths:
        if len(selected) >= max_results:
            break
        try:
            content = path.read_text(encoding="utf-8")
            tokens = estimate_tokens(content)
            if total_tokens + tokens <= max_tokens:
                selected.append(path)
                total_tokens += tokens
            elif not selected:
                # Always include at least one chunk even if over budget
                selected.append(path)
                break
        except Exception:
            continue

    return selected
