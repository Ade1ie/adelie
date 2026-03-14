"""tests/test_spec_chunker.py — Unit tests for the Spec Chunker module."""
from __future__ import annotations

import pytest

from adelie.spec_chunker import (
    Chunk,
    CHUNK_THRESHOLD,
    chunk_markdown,
    needs_chunking,
)


class TestNeedsChunking:
    def test_short_text_no_chunking(self):
        assert needs_chunking("Hello world") is False

    def test_long_text_needs_chunking(self):
        text = "x" * (CHUNK_THRESHOLD + 1)
        assert needs_chunking(text) is True

    def test_threshold_boundary(self):
        text = "x" * CHUNK_THRESHOLD
        assert needs_chunking(text) is False
        text = "x" * (CHUNK_THRESHOLD + 1)
        assert needs_chunking(text) is True


class TestChunkMarkdown:
    def test_short_text_single_chunk(self):
        text = "# Hello\n\nThis is short."
        chunks = chunk_markdown(text)
        assert len(chunks) == 1
        assert chunks[0].heading == "Full Document"
        assert "Hello" in chunks[0].content

    def test_empty_text_no_chunks(self):
        assert chunk_markdown("") == []
        assert chunk_markdown("   ") == []

    def test_splits_by_h2_headings(self):
        sections = []
        for i in range(5):
            sections.append(f"## Section {i}\n\n{'Content ' * 400}")
        text = "\n\n".join(sections)

        chunks = chunk_markdown(text)
        assert len(chunks) >= 5
        headings = [c.heading for c in chunks]
        assert "Section 0" in headings
        assert "Section 4" in headings

    def test_preserves_introduction(self):
        text = "# Title\n\nIntro paragraph with enough text.\n\n" + "x " * 2000
        text += "\n\n## Section A\n\n" + "Content A " * 2000
        text += "\n\n## Section B\n\n" + "Content B " * 2000

        chunks = chunk_markdown(text)
        headings = [c.heading for c in chunks]
        assert "Introduction" in headings or any("Title" in h for h in headings)

    def test_large_section_sub_splits(self):
        # Create a section with sub-headings that exceeds max chunk size
        text = "## Big Section\n\n"
        for i in range(10):
            text += f"### Sub {i}\n\n{'Detail ' * 300}\n\n"

        # Make it exceed threshold
        text = "# Title\n\n" + text + "\n\n## Another\n\n" + "x " * 2000
        chunks = chunk_markdown(text)

        # Should have more chunks than just 2 sections
        assert len(chunks) > 2

    def test_paragraph_splitting_when_no_subheadings(self):
        # A single section with no sub-headings but very long
        text = "## Long Section\n\n"
        for i in range(50):
            text += f"Paragraph {i}. " + "Word " * 100 + "\n\n"
        # Pad to exceed threshold
        text = "# Doc\n\npreamble\n\n" + text

        chunks = chunk_markdown(text)
        # Should be split into multiple chunks
        assert len(chunks) > 1

    def test_chunk_metadata(self):
        text = "## Section A\n\n" + "Content " * 500
        text += "\n\n## Section B\n\n" + "Content " * 500
        text = "# Doc\n\n" + text + "\n\n" + "x " * 2000

        chunks = chunk_markdown(text, source_name="test_doc")
        for chunk in chunks:
            assert chunk.index >= 0
            assert chunk.char_count > 0
            assert chunk.heading
            assert chunk.content

    def test_chunk_indices_sequential(self):
        sections = []
        for i in range(6):
            sections.append(f"## Part {i}\n\n{'Data ' * 400}")
        text = "\n\n".join(sections)

        chunks = chunk_markdown(text)
        indices = [c.index for c in chunks]
        assert indices == list(range(len(chunks)))

    def test_summary_line(self):
        chunk = Chunk(index=0, heading="Auth Spec", content="test", parent_headings=["API"])
        assert "chunk 0" in chunk.summary_line
        assert "Auth Spec" in chunk.summary_line
        assert "API" in chunk.summary_line


class TestChunkIntegrationWithSpecLoader:
    """Integration tests between chunker and spec_loader."""

    def test_large_md_gets_chunked(self, tmp_path, monkeypatch):
        import adelie.config as cfg
        import adelie.kb.retriever as r

        workspace = tmp_path / "workspace"
        monkeypatch.setattr(cfg, "WORKSPACE_PATH", workspace)
        monkeypatch.setattr(r, "WORKSPACE_PATH", workspace)
        monkeypatch.setattr(r, "INDEX_FILE", workspace / "index.json")
        r.ensure_workspace()

        from adelie.spec_loader import load_spec

        # Create a large MD spec
        md_file = tmp_path / "big_spec.md"
        content = "# Big Specification\n\n"
        for i in range(20):
            content += f"## Section {i}: Feature Details\n\n"
            content += f"This section describes feature {i} in detail. " * 50
            content += "\n\n"
        md_file.write_text(content, encoding="utf-8")

        result = load_spec(md_file, workspace)
        assert result.exists()

        # Check that chunk files were created
        logic_dir = workspace / "logic"
        chunk_files = list(logic_dir.glob("spec_big_spec_chunk_*.md"))
        assert len(chunk_files) > 0

        # Check index has chunk entries
        index = r.get_index()
        chunk_entries = [k for k in index if "chunk" in k]
        assert len(chunk_entries) > 0

        # Each chunk entry should have spec_chunk tag
        for entry_key in chunk_entries:
            assert "spec_chunk" in index[entry_key]["tags"]

    def test_small_md_not_chunked(self, tmp_path, monkeypatch):
        import adelie.config as cfg
        import adelie.kb.retriever as r

        workspace = tmp_path / "workspace"
        monkeypatch.setattr(cfg, "WORKSPACE_PATH", workspace)
        monkeypatch.setattr(r, "WORKSPACE_PATH", workspace)
        monkeypatch.setattr(r, "INDEX_FILE", workspace / "index.json")
        r.ensure_workspace()

        from adelie.spec_loader import load_spec

        md_file = tmp_path / "small_spec.md"
        md_file.write_text("# Small Spec\n\nJust a short spec.", encoding="utf-8")

        result = load_spec(md_file, workspace)
        assert result.exists()

        # No chunk files should exist
        logic_dir = workspace / "logic"
        chunk_files = list(logic_dir.glob("spec_small_spec_chunk_*.md"))
        assert len(chunk_files) == 0

    def test_remove_spec_cleans_chunks(self, tmp_path, monkeypatch):
        import adelie.config as cfg
        import adelie.kb.retriever as r

        workspace = tmp_path / "workspace"
        monkeypatch.setattr(cfg, "WORKSPACE_PATH", workspace)
        monkeypatch.setattr(r, "WORKSPACE_PATH", workspace)
        monkeypatch.setattr(r, "INDEX_FILE", workspace / "index.json")
        r.ensure_workspace()

        from adelie.spec_loader import load_spec, remove_spec, list_specs

        # Create and load a large spec
        md_file = tmp_path / "chunked.md"
        content = "# Chunked Spec\n\n"
        for i in range(15):
            content += f"## Part {i}\n\n" + "Details " * 300 + "\n\n"
        md_file.write_text(content, encoding="utf-8")

        load_spec(md_file, workspace)

        # Verify chunks exist
        logic_dir = workspace / "logic"
        chunk_files = list(logic_dir.glob("spec_chunked_chunk_*.md"))
        assert len(chunk_files) > 0

        # Remove spec
        result = remove_spec(workspace, "spec_chunked")
        assert result is True

        # All files should be gone
        assert not (logic_dir / "spec_chunked.md").exists()
        remaining_chunks = list(logic_dir.glob("spec_chunked_chunk_*.md"))
        assert len(remaining_chunks) == 0

        # Index should be clean
        assert len(list_specs(workspace)) == 0
