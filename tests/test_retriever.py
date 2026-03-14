"""tests/test_retriever.py — Unit tests for the KB Retriever module."""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import pytest

# Patch WORKSPACE_PATH to a temp dir before importing retriever
import adelie.config as cfg


@pytest.fixture
def tmp_workspace(tmp_path, monkeypatch):
    """Provide a temporary workspace for each test."""
    monkeypatch.setattr(cfg, "WORKSPACE_PATH", tmp_path)
    # Also patch the retriever's own reference
    import adelie.kb.retriever as r
    monkeypatch.setattr(r, "WORKSPACE_PATH", tmp_path)
    monkeypatch.setattr(r, "INDEX_FILE", tmp_path / "index.json")
    r.ensure_workspace()
    return tmp_path


def _write_kb_file(workspace: Path, category: str, filename: str, content: str, tags: list[str], summary: str):
    import adelie.kb.retriever as r
    p = workspace / category / filename
    p.write_text(content, encoding="utf-8")
    r.update_index(f"{category}/{filename}", tags, summary)
    return p


class TestEnsureWorkspace:
    def test_creates_all_category_folders(self, tmp_workspace):
        from adelie.config import KB_CATEGORIES
        for cat in KB_CATEGORIES:
            assert (tmp_workspace / cat).is_dir()

    def test_creates_empty_index(self, tmp_workspace):
        index_file = tmp_workspace / "index.json"
        assert index_file.exists()
        assert json.loads(index_file.read_text()) == {}


class TestIndexManagement:
    def test_update_and_get_index(self, tmp_workspace):
        import adelie.kb.retriever as r
        r.update_index("skills/test.md", ["tag1", "tag2"], "A test skill")
        index = r.get_index()
        assert "skills/test.md" in index
        assert index["skills/test.md"]["tags"] == ["tag1", "tag2"]
        assert index["skills/test.md"]["summary"] == "A test skill"

    def test_update_index_upserts(self, tmp_workspace):
        import adelie.kb.retriever as r
        r.update_index("skills/test.md", ["old"], "old summary")
        r.update_index("skills/test.md", ["new"], "new summary")
        index = r.get_index()
        assert index["skills/test.md"]["tags"] == ["new"]


class TestQuery:
    def test_query_returns_files_for_situation(self, tmp_workspace):
        import adelie.kb.retriever as r
        _write_kb_file(tmp_workspace, "skills", "how_to_retry.md", "retry steps", ["retry"], "Retry guide")
        _write_kb_file(tmp_workspace, "errors", "known_error.md", "error info", ["error"], "Known error")

        # 'error' situation should pull from errors/ and skills/
        paths = r.query("error")
        names = [p.name for p in paths]
        assert "known_error.md" in names
        assert "how_to_retry.md" in names

    def test_query_with_extra_tags_filters(self, tmp_workspace):
        import adelie.kb.retriever as r
        _write_kb_file(tmp_workspace, "skills", "skill_a.md", "a", ["deploy"], "Deploy")
        _write_kb_file(tmp_workspace, "skills", "skill_b.md", "b", ["testing"], "Test")

        paths = r.query("normal", extra_tags=["deploy"])
        names = [p.name for p in paths]
        assert "skill_a.md" in names
        assert "skill_b.md" not in names

    def test_query_empty_workspace_returns_empty(self, tmp_workspace):
        import adelie.kb.retriever as r
        assert r.query("normal") == []


class TestReadFiles:
    def test_read_files_formats_content(self, tmp_workspace):
        import adelie.kb.retriever as r
        p = _write_kb_file(tmp_workspace, "skills", "guide.md", "# Guide\nDo this.", ["x"], "x")
        result = r.read_files([p])
        assert "skills/guide.md" in result
        assert "Do this." in result

    def test_read_files_empty_list(self, tmp_workspace):
        import adelie.kb.retriever as r
        result = r.read_files([])
        assert "no relevant" in result.lower()
