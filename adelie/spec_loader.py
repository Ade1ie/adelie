"""
adelie/spec_loader.py — Multi-format Spec Loader

Converts specification files (MD, PDF, DOCX) to Markdown
and loads them into the Adelie Knowledge Base.
Large files are automatically chunked and individually embedded.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Optional

from adelie.kb import retriever


# ── Supported extensions ─────────────────────────────────────────────────────

SUPPORTED_EXTENSIONS = {".md", ".pdf", ".docx", ".doc"}


# ── Converters ───────────────────────────────────────────────────────────────


def _convert_pdf(file_path: Path) -> str:
    """Extract text from a PDF file and format as Markdown."""
    try:
        from PyPDF2 import PdfReader
    except ImportError:
        raise ImportError(
            "PyPDF2 is required for PDF support. Install with: pip install PyPDF2>=3.0.0"
        )

    reader = PdfReader(str(file_path))
    sections: list[str] = []
    sections.append(f"# {file_path.stem}\n")
    sections.append(f"> 📄 Converted from `{file_path.name}` ({len(reader.pages)} pages)\n")

    for i, page in enumerate(reader.pages, 1):
        text = page.extract_text()
        if text and text.strip():
            sections.append(f"## Page {i}\n")
            # Clean up common PDF artifacts
            cleaned = text.strip()
            # Normalize excessive whitespace but preserve paragraph breaks
            lines = cleaned.split("\n")
            cleaned_lines: list[str] = []
            for line in lines:
                stripped = line.strip()
                if stripped:
                    cleaned_lines.append(stripped)
                elif cleaned_lines and cleaned_lines[-1] != "":
                    cleaned_lines.append("")
            sections.append("\n".join(cleaned_lines))

    return "\n\n".join(sections)


def _convert_docx(file_path: Path) -> str:
    """Convert a DOCX file to Markdown, preserving headings, paragraphs, and tables."""
    try:
        from docx import Document
    except ImportError:
        raise ImportError(
            "python-docx is required for DOCX support. Install with: pip install python-docx>=0.8.11"
        )

    doc = Document(str(file_path))
    sections: list[str] = []
    sections.append(f"# {file_path.stem}\n")
    sections.append(f"> 📄 Converted from `{file_path.name}`\n")

    # Heading style → MD level mapping
    HEADING_MAP = {
        "Heading 1": "## ",
        "Heading 2": "### ",
        "Heading 3": "#### ",
        "Heading 4": "##### ",
        "Heading 5": "###### ",
    }

    for element in doc.element.body:
        tag = element.tag.split("}")[-1]  # Strip namespace

        if tag == "p":
            # It's a paragraph
            from docx.text.paragraph import Paragraph
            para = Paragraph(element, doc)
            text = para.text.strip()
            if not text:
                continue

            style_name = para.style.name if para.style else ""
            prefix = HEADING_MAP.get(style_name, "")

            if prefix:
                sections.append(f"{prefix}{text}")
            elif style_name and "List" in style_name:
                sections.append(f"- {text}")
            else:
                sections.append(text)

        elif tag == "tbl":
            # It's a table
            from docx.table import Table
            table = Table(element, doc)
            if not table.rows:
                continue

            # Build MD table
            md_rows: list[str] = []
            for row_idx, row in enumerate(table.rows):
                cells = [cell.text.strip().replace("|", "\\|") for cell in row.cells]
                md_rows.append("| " + " | ".join(cells) + " |")
                if row_idx == 0:
                    md_rows.append("| " + " | ".join(["---"] * len(cells)) + " |")

            sections.append("\n".join(md_rows))

    return "\n\n".join(sections)


def _read_markdown(file_path: Path) -> str:
    """Read a Markdown file as-is."""
    return file_path.read_text(encoding="utf-8")


# ── Public API ───────────────────────────────────────────────────────────────


def convert_to_markdown(file_path: Path) -> str:
    """
    Auto-detect file format and convert to Markdown.

    Args:
        file_path: Path to the source spec file.

    Returns:
        Markdown string content.

    Raises:
        ValueError: If the file extension is not supported.
        FileNotFoundError: If the file doesn't exist.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    ext = file_path.suffix.lower()

    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file format: '{ext}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    if ext == ".md":
        return _read_markdown(file_path)
    elif ext == ".pdf":
        return _convert_pdf(file_path)
    elif ext in (".docx", ".doc"):
        return _convert_docx(file_path)

    # Should not reach here
    raise ValueError(f"Unhandled extension: {ext}")


def load_spec(
    file_path: Path,
    workspace_path: Path,
    category: str = "logic",
    custom_name: Optional[str] = None,
) -> Path:
    """
    Convert a spec file to Markdown and save it to the KB.
    Large files are automatically chunked for better embedding coverage.

    Args:
        file_path:      Path to the source spec file.
        workspace_path: Path to the .adelie/workspace directory.
        category:       KB category to store in (default: 'logic').
        custom_name:    Optional custom base name for the KB file.

    Returns:
        Path to the saved master KB file.
    """
    from adelie.spec_chunker import chunk_markdown, needs_chunking

    markdown_content = convert_to_markdown(file_path)

    # Determine output filename
    base_name = custom_name or file_path.stem
    # Sanitize: replace spaces/special chars with underscores
    safe_name = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in base_name)
    output_name = f"spec_{safe_name}.md"

    # Save master file to KB
    target_dir = workspace_path / category
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / output_name
    target_path.write_text(markdown_content, encoding="utf-8")

    # Register master file in KB index
    relative_path = f"{category}/{output_name}"
    chunk_count = 0

    if needs_chunking(markdown_content):
        # Large file → chunk and embed individually
        chunks = chunk_markdown(markdown_content, source_name=base_name)
        chunk_count = len(chunks)

        # Register master with chunk metadata
        retriever.update_index(
            relative_path,
            tags=["spec", "specification", "spec_master", category, base_name],
            summary=f"Specification: {file_path.name} ({chunk_count} chunks, {len(markdown_content)} chars)",
        )

        # Save and register each chunk
        for chunk in chunks:
            chunk_filename = f"spec_{safe_name}_chunk_{chunk.index:03d}.md"
            chunk_path = target_dir / chunk_filename
            chunk_rel = f"{category}/{chunk_filename}"

            # Prepend context header to chunk content
            header = (
                f"> 📎 Chunk {chunk.index} of `{file_path.name}` — "
                f"Section: {chunk.heading}\n\n"
            )
            chunk_path.write_text(header + chunk.content, encoding="utf-8")

            # Register chunk in KB index
            retriever.update_index(
                chunk_rel,
                tags=["spec", "spec_chunk", category, base_name, f"spec_{safe_name}"],
                summary=f"Spec chunk [{chunk.index}]: {chunk.heading} ({chunk.char_count} chars)",
            )
    else:
        # Small file → single registration (no chunking needed)
        retriever.update_index(
            relative_path,
            tags=["spec", "specification", category, base_name],
            summary=f"Specification: {file_path.name} (loaded as {output_name})",
        )

    return target_path


def get_spec_info(workspace_path: Path, spec_name: str) -> Optional[dict]:
    """
    Get detailed info about a loaded spec including chunk count.

    Returns:
        Dict with 'name', 'category', 'chunks', 'total_chars', or None.
    """
    index = retriever.get_index()
    master_info = None
    chunk_count = 0

    for rel_path, meta in index.items():
        tags = meta.get("tags", [])
        full_path = workspace_path / rel_path
        if not full_path.exists():
            continue

        if "spec_master" in tags and spec_name in tags:
            parts = rel_path.split("/", 1)
            master_info = {
                "name": full_path.stem,
                "category": parts[0] if len(parts) > 1 else "unknown",
                "path": rel_path,
                "size": full_path.stat().st_size,
                "summary": meta.get("summary", ""),
            }
        elif "spec_chunk" in tags and spec_name in tags:
            chunk_count += 1

    if master_info:
        master_info["chunks"] = chunk_count
        return master_info

    return None


def list_specs(workspace_path: Path) -> list[dict]:
    """
    List all loaded specification files from the KB.

    Returns:
        List of dicts with 'name', 'category', 'path', 'size', 'chunks' keys.
    """
    index = retriever.get_index()
    specs: list[dict] = []
    # Track chunk counts per spec parent
    chunk_counts: dict[str, int] = {}

    # First pass: count chunks
    for rel_path, meta in index.items():
        tags = meta.get("tags", [])
        if "spec_chunk" in tags:
            # Find parent spec name from tags
            for tag in tags:
                if tag.startswith("spec_") and tag != "spec_chunk":
                    chunk_counts[tag] = chunk_counts.get(tag, 0) + 1

    # Second pass: list master specs (or non-chunked specs)
    for rel_path, meta in index.items():
        tags = meta.get("tags", [])
        # Include spec_master files and simple specs (no chunks)
        if "spec" in tags and "spec_chunk" not in tags:
            full_path = workspace_path / rel_path
            if full_path.exists():
                parts = rel_path.split("/", 1)
                spec_key = full_path.stem  # e.g. "spec_my_spec"
                specs.append({
                    "name": full_path.stem,
                    "category": parts[0] if len(parts) > 1 else "unknown",
                    "path": rel_path,
                    "size": full_path.stat().st_size,
                    "chunks": chunk_counts.get(spec_key, 0),
                    "summary": meta.get("summary", ""),
                    "updated": meta.get("updated", ""),
                })

    return specs


def remove_spec(workspace_path: Path, spec_name: str) -> bool:
    """
    Remove a loaded specification from the KB, including all chunks.

    Args:
        workspace_path: Path to the .adelie/workspace directory.
        spec_name:      Name (stem) of the spec file to remove.

    Returns:
        True if removed, False if not found.
    """
    index = retriever.get_index()
    to_remove: list[str] = []

    for rel_path, meta in index.items():
        tags = meta.get("tags", [])
        if "spec" not in tags:
            continue

        full_path = workspace_path / rel_path

        # Match master file
        is_master = (
            full_path.stem == spec_name
            or full_path.stem == f"spec_{spec_name}"
        )

        # Match chunk files (tagged with parent spec name)
        is_chunk = (
            "spec_chunk" in tags
            and (spec_name in tags or f"spec_{spec_name}" in tags)
        )

        if is_master or is_chunk:
            to_remove.append(rel_path)
            if full_path.exists():
                full_path.unlink()

            # Also remove embedding if exists
            try:
                from adelie.kb.embedding_store import remove_embedding
                remove_embedding(rel_path)
            except Exception:
                pass

    if not to_remove:
        return False

    # Update index
    for key in to_remove:
        index.pop(key, None)
    retriever.INDEX_FILE.write_text(
        json.dumps(index, indent=2), encoding="utf-8"
    )

    return True
