"""tests/test_embedding_store.py — Tests for KB embedding store and semantic search."""
from __future__ import annotations

from unittest.mock import patch, MagicMock
import math

import pytest

from adelie.kb.embedding_store import cosine_similarity


# ── Vector Operations ────────────────────────────────────────────────────────


class TestCosineSimilarity:
    def test_identical_vectors(self):
        v = [1.0, 2.0, 3.0]
        assert abs(cosine_similarity(v, v) - 1.0) < 0.001

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert abs(cosine_similarity(a, b)) < 0.001

    def test_opposite_vectors(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert abs(cosine_similarity(a, b) - (-1.0)) < 0.001

    def test_empty_vectors(self):
        assert cosine_similarity([], []) == 0.0

    def test_mismatched_lengths(self):
        assert cosine_similarity([1.0], [1.0, 2.0]) == 0.0

    def test_zero_vector(self):
        assert cosine_similarity([0.0, 0.0], [1.0, 2.0]) == 0.0


# ── Embedding Store ──────────────────────────────────────────────────────────


class TestEmbeddingStore:
    def test_load_save_roundtrip(self, tmp_path, monkeypatch):
        import adelie.kb.embedding_store as es
        monkeypatch.setattr(es, "EMBEDDINGS_FILE", tmp_path / "embeddings.json")

        store = {"skills/a.md": {"vector": [1.0, 2.0], "timestamp": 123}}
        es._save_store(store)
        loaded = es._load_store()
        assert loaded["skills/a.md"]["vector"] == [1.0, 2.0]

    def test_load_empty(self, tmp_path, monkeypatch):
        import adelie.kb.embedding_store as es
        monkeypatch.setattr(es, "EMBEDDINGS_FILE", tmp_path / "nonexistent.json")
        store = es._load_store()
        # Empty store still contains the model marker
        assert store.get(es._STORE_MODEL_KEY) == es.EMBEDDING_MODEL
        assert len([k for k in store if k != es._STORE_MODEL_KEY]) == 0


# ── Semantic Search (mocked embeddings) ──────────────────────────────────────


class TestSemanticSearch:
    def test_search_with_mocked_embeddings(self, tmp_path, monkeypatch):
        import adelie.kb.embedding_store as es
        monkeypatch.setattr(es, "EMBEDDINGS_FILE", tmp_path / "embeddings.json")

        # Pre-populate store with known vectors
        store = {
            "skills/api.md": {"vector": [1.0, 0.0, 0.0], "timestamp": 1},
            "errors/bug.md": {"vector": [0.0, 1.0, 0.0], "timestamp": 1},
            "logic/plan.md": {"vector": [0.7, 0.7, 0.0], "timestamp": 1},
        }
        es._save_store(store)

        # Mock _compute_embedding to return a vector similar to api.md
        with patch.object(es, "_compute_embedding", return_value=[0.9, 0.1, 0.0]):
            results = es.semantic_search("how to use the API", top_k=3, threshold=0.1)

        # api.md should be most similar, then plan.md (mixed), then bug.md (orthogonal)
        assert len(results) >= 2
        paths = [r[0] for r in results]
        assert paths[0] == "skills/api.md"

    def test_search_empty_store(self, tmp_path, monkeypatch):
        import adelie.kb.embedding_store as es
        monkeypatch.setattr(es, "EMBEDDINGS_FILE", tmp_path / "embeddings.json")

        with patch.object(es, "_compute_embedding", return_value=[1.0, 0.0]):
            results = es.semantic_search("anything")
        assert results == []

    def test_search_returns_empty_on_embedding_failure(self, tmp_path, monkeypatch):
        import adelie.kb.embedding_store as es
        monkeypatch.setattr(es, "EMBEDDINGS_FILE", tmp_path / "embeddings.json")

        with patch.object(es, "_compute_embedding", return_value=None):
            results = es.semantic_search("anything")
        assert results == []


# ── Update / Remove Embedding ────────────────────────────────────────────────


class TestUpdateRemoveEmbedding:
    def test_update_and_remove(self, tmp_path, monkeypatch):
        import adelie.kb.embedding_store as es
        monkeypatch.setattr(es, "EMBEDDINGS_FILE", tmp_path / "embeddings.json")

        with patch.object(es, "_compute_embedding", return_value=[1.0, 2.0, 3.0]):
            assert es.update_embedding("skills/a.md", "content", "summary") is True

        store = es._load_store()
        assert "skills/a.md" in store

        es.remove_embedding("skills/a.md")
        store = es._load_store()
        assert "skills/a.md" not in store

    def test_update_fails_gracefully(self, tmp_path, monkeypatch):
        import adelie.kb.embedding_store as es
        monkeypatch.setattr(es, "EMBEDDINGS_FILE", tmp_path / "embeddings.json")

        with patch.object(es, "_compute_embedding", return_value=None):
            assert es.update_embedding("skills/a.md", "content") is False


# ── Retriever Semantic Query ─────────────────────────────────────────────────


class TestRetrieverSemanticQuery:
    def test_falls_back_to_tag_search(self, tmp_path, monkeypatch):
        """When semantic search returns nothing, tag-based results still work."""
        import adelie.kb.retriever as r
        import adelie.config as cfg

        monkeypatch.setattr(cfg, "WORKSPACE_PATH", tmp_path)
        monkeypatch.setattr(r, "WORKSPACE_PATH", tmp_path)
        monkeypatch.setattr(r, "INDEX_FILE", tmp_path / "index.json")
        r.ensure_workspace()

        # Create a KB file
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir(exist_ok=True)
        test_file = skills_dir / "test.md"
        test_file.write_text("# Test\nSome skill")

        # Manually update index (without embedding to avoid API call)
        index = r.get_index()
        index["skills/test.md"] = {"tags": ["test"], "summary": "A test skill", "updated": "2024-01-01"}
        r.INDEX_FILE.write_text(__import__("json").dumps(index, indent=2))

        # semantic_query should fall back to tag search
        with patch("adelie.kb.embedding_store.semantic_search", return_value=[]):
            results = r.semantic_query("normal", query_text="test query")

        assert len(results) >= 1
        assert any("test.md" in str(p) for p in results)


# ── Store Stats ──────────────────────────────────────────────────────────────


class TestStoreStats:
    def test_empty_stats(self, tmp_path, monkeypatch):
        import adelie.kb.embedding_store as es
        monkeypatch.setattr(es, "EMBEDDINGS_FILE", tmp_path / "embeddings.json")
        stats = es.get_store_stats()
        assert stats["total_embeddings"] == 0
