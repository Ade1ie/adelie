"""
adelie/kb/embedding_store.py

Lightweight embedding-based semantic search for the Knowledge Base.
Uses Gemini's text-embedding API to create vector representations of KB files,
enabling meaning-based retrieval instead of just tag matching.

Storage: simple JSON file alongside index.json (KB is small, ~48 files max).
Fallback: if embedding fails, returns empty results and tag-based search is used.
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Optional

from rich.console import Console

from adelie.config import GEMINI_API_KEY, WORKSPACE_PATH

console = Console()

# ── Paths ────────────────────────────────────────────────────────────────────

EMBEDDINGS_FILE = WORKSPACE_PATH / "embeddings.json"

# ── Config ───────────────────────────────────────────────────────────────────

EMBEDDING_MODEL = "gemini-embedding-001"  # Replacement for deprecated text-embedding-004
EMBEDDING_DIMENSION = 3072  # gemini-embedding-001 output dimension
MAX_RESULTS = 8  # Max files to return from semantic search
SIMILARITY_THRESHOLD = 0.3  # Minimum cosine similarity to include
_STORE_MODEL_KEY = "__model__"  # Track which model generated stored embeddings


# ── Embedding Client (lazy) ─────────────────────────────────────────────────

_embed_client = None


def _get_embed_client():
    """Lazy-init the Gemini client for embeddings."""
    global _embed_client
    if _embed_client is None:
        if not GEMINI_API_KEY:
            return None
        from google import genai
        _embed_client = genai.Client(api_key=GEMINI_API_KEY)
    return _embed_client


# ── Vector Operations ────────────────────────────────────────────────────────


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ── Embedding Store ──────────────────────────────────────────────────────────


def _load_store() -> dict:
    """Load embedding store from disk. Auto-clears if model changed."""
    if EMBEDDINGS_FILE.exists():
        try:
            store = json.loads(EMBEDDINGS_FILE.read_text(encoding="utf-8"))
            # Invalidate embeddings from a different model (dimension mismatch)
            if store.get(_STORE_MODEL_KEY) != EMBEDDING_MODEL:
                console.print(
                    f"[yellow]🔄 Embedding model changed → clearing stale embeddings[/yellow]"
                )
                return {_STORE_MODEL_KEY: EMBEDDING_MODEL}
            return store
        except (json.JSONDecodeError, OSError):
            return {_STORE_MODEL_KEY: EMBEDDING_MODEL}
    return {_STORE_MODEL_KEY: EMBEDDING_MODEL}


def _save_store(store: dict) -> None:
    """Persist embedding store to disk."""
    store[_STORE_MODEL_KEY] = EMBEDDING_MODEL
    EMBEDDINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    EMBEDDINGS_FILE.write_text(
        json.dumps(store, ensure_ascii=False),
        encoding="utf-8",
    )


def _compute_embedding(text: str) -> Optional[list[float]]:
    """
    Compute embedding vector for a text string using Gemini API.
    Returns None on failure.
    """
    client = _get_embed_client()
    if client is None:
        return None

    try:
        # Truncate very long texts — chunked specs should already be sized,
        # but limit non-chunked content to a reasonable embedding window.
        MAX_EMBED_CHARS = 10000
        if len(text) > MAX_EMBED_CHARS:
            text = text[:MAX_EMBED_CHARS]

        result = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=text,
        )

        # The API returns an EmbedContentResponse with embeddings
        if result and result.embeddings:
            return list(result.embeddings[0].values)
        return None

    except Exception as e:
        console.print(f"[dim]⚠️  Embedding error: {e}[/dim]")
        return None


# ── Public API ───────────────────────────────────────────────────────────────


def update_embedding(relative_path: str, content: str, summary: str = "") -> bool:
    """
    Create or update the embedding for a KB file.
    Uses summary + content for a richer embedding.

    Args:
        relative_path: Path relative to WORKSPACE_PATH (e.g. 'skills/api_design.md')
        content:       Full file content
        summary:       One-line summary (from index)

    Returns:
        True if embedding was created/updated, False on failure.
    """
    # Build embedding text: summary provides a concise signal, content adds detail
    embed_text = f"{summary}\n\n{content}" if summary else content

    vector = _compute_embedding(embed_text)
    if vector is None:
        return False

    store = _load_store()
    store[relative_path] = {
        "vector": vector,
        "timestamp": time.time(),
    }
    _save_store(store)
    return True


def remove_embedding(relative_path: str) -> None:
    """Remove embedding for a deleted KB file."""
    store = _load_store()
    if relative_path in store:
        del store[relative_path]
        _save_store(store)


def semantic_search(
    query_text: str,
    top_k: int = MAX_RESULTS,
    threshold: float = SIMILARITY_THRESHOLD,
) -> list[tuple[str, float]]:
    """
    Search KB files by semantic similarity to a query.

    Args:
        query_text: Natural language query (e.g. situation description)
        top_k:      Maximum number of results
        threshold:  Minimum cosine similarity (0.0–1.0)

    Returns:
        List of (relative_path, similarity_score) tuples, sorted by score descending.
    """
    query_vector = _compute_embedding(query_text)
    if query_vector is None:
        return []

    store = _load_store()
    if not store:
        return []

    scores: list[tuple[str, float]] = []
    for path, entry in store.items():
        if path == _STORE_MODEL_KEY:
            continue
        vector = entry.get("vector", []) if isinstance(entry, dict) else []
        if not vector:
            continue
        sim = cosine_similarity(query_vector, vector)
        if sim >= threshold:
            scores.append((path, sim))

    # Sort by similarity descending
    scores.sort(key=lambda x: x[1], reverse=True)
    return scores[:top_k]


def rebuild_all_embeddings() -> dict:
    """
    Rebuild embeddings for all existing KB files.
    Useful after first setup or when embedding model changes.

    Returns:
        Dict with counts: {"updated": N, "failed": M, "total": T}
    """
    from adelie.kb.retriever import get_index

    index = get_index()
    updated = 0
    failed = 0

    for rel_path, meta in index.items():
        full_path = WORKSPACE_PATH / rel_path
        if not full_path.exists():
            continue

        content = full_path.read_text(encoding="utf-8")
        summary = meta.get("summary", "")

        if update_embedding(rel_path, content, summary):
            updated += 1
            console.print(f"[dim]  🔗 Embedded: {rel_path}[/dim]")
        else:
            failed += 1

    return {"updated": updated, "failed": failed, "total": len(index)}


def get_store_stats() -> dict:
    """Return embedding store statistics."""
    store = _load_store()
    file_keys = [k for k in store if k != _STORE_MODEL_KEY]
    return {
        "total_embeddings": len(file_keys),
        "files": file_keys,
    }
