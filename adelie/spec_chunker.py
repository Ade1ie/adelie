"""
adelie/spec_chunker.py — Smart Markdown Chunking Engine

Splits large Markdown documents into semantically meaningful chunks
based on heading structure, with configurable size limits.
Each chunk is suitable for individual embedding and retrieval.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# ── Configuration ────────────────────────────────────────────────────────────

# Max characters per chunk (roughly ~1500 tokens at 4 chars/token)
DEFAULT_MAX_CHUNK_CHARS = 6000

# Threshold: files smaller than this are not chunked
CHUNK_THRESHOLD = 8000

# Minimum chunk size (avoid tiny fragments)
MIN_CHUNK_CHARS = 200


# ── Data Structures ──────────────────────────────────────────────────────────


@dataclass
class Chunk:
    """A semantically meaningful piece of a larger document."""

    index: int
    heading: str          # The section heading (or "Introduction" for preamble)
    content: str          # Full text of this chunk (including heading)
    char_count: int = 0
    parent_headings: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.char_count:
            self.char_count = len(self.content)

    @property
    def summary_line(self) -> str:
        """One-line description for index metadata."""
        prefix = " > ".join(self.parent_headings) if self.parent_headings else ""
        heading = self.heading
        if prefix:
            heading = f"{prefix} > {heading}"
        return f"[chunk {self.index}] {heading} ({self.char_count} chars)"


# ── Chunking Logic ───────────────────────────────────────────────────────────


def chunk_markdown(
    text: str,
    max_chunk_chars: int = DEFAULT_MAX_CHUNK_CHARS,
    source_name: str = "",
) -> list[Chunk]:
    """
    Split Markdown text into semantically meaningful chunks.

    Strategy:
    1. Split by ## headings (level 2) to preserve section boundaries.
    2. If a section exceeds max_chunk_chars, sub-split by ### headings (level 3).
    3. If still too large, split by paragraph boundaries (double newline).
    4. Each chunk includes context: parent heading chain for relevance.

    Args:
        text:            Full Markdown content.
        max_chunk_chars: Maximum characters per chunk.
        source_name:     Name of the source file (for metadata).

    Returns:
        List of Chunk objects, each sized ≤ max_chunk_chars.
    """
    if not text or not text.strip():
        return []

    # If text is small enough, return as single chunk
    if len(text) <= CHUNK_THRESHOLD:
        return [Chunk(
            index=0,
            heading=source_name or "Full Document",
            content=text,
        )]

    # Step 1: Split by level-2 headings (##)
    sections = _split_by_heading(text, level=2)

    chunks: list[Chunk] = []
    chunk_index = 0

    for section_heading, section_content in sections:
        full_section = section_content

        if len(full_section) <= max_chunk_chars:
            # Section fits in one chunk
            chunks.append(Chunk(
                index=chunk_index,
                heading=section_heading,
                content=full_section,
            ))
            chunk_index += 1
        else:
            # Section too large — sub-split by level-3 headings
            sub_sections = _split_by_heading(full_section, level=3)

            if len(sub_sections) > 1:
                # Multiple sub-sections found
                for sub_heading, sub_content in sub_sections:
                    if len(sub_content) <= max_chunk_chars:
                        chunks.append(Chunk(
                            index=chunk_index,
                            heading=sub_heading,
                            content=sub_content,
                            parent_headings=[section_heading] if section_heading != sub_heading else [],
                        ))
                        chunk_index += 1
                    else:
                        # Still too large — split by paragraphs
                        para_chunks = _split_by_paragraphs(
                            sub_content, max_chunk_chars, sub_heading
                        )
                        for pc_heading, pc_content in para_chunks:
                            chunks.append(Chunk(
                                index=chunk_index,
                                heading=pc_heading,
                                content=pc_content,
                                parent_headings=[section_heading],
                            ))
                            chunk_index += 1
            else:
                # No sub-headings — split by paragraphs directly
                para_chunks = _split_by_paragraphs(
                    full_section, max_chunk_chars, section_heading
                )
                for pc_heading, pc_content in para_chunks:
                    chunks.append(Chunk(
                        index=chunk_index,
                        heading=pc_heading,
                        content=pc_content,
                    ))
                    chunk_index += 1

    # Filter out empty/tiny chunks
    chunks = [c for c in chunks if c.char_count >= MIN_CHUNK_CHARS]

    # Re-index after filtering
    for i, chunk in enumerate(chunks):
        chunk.index = i

    return chunks


def needs_chunking(text: str) -> bool:
    """Check if text is large enough to require chunking."""
    return len(text) > CHUNK_THRESHOLD


# ── Internal Helpers ─────────────────────────────────────────────────────────


def _split_by_heading(text: str, level: int = 2) -> list[tuple[str, str]]:
    """
    Split Markdown text by headings of the specified level.

    Returns:
        List of (heading_text, section_content) tuples.
        The first section may have heading "Introduction" if there's
        content before the first heading.
    """
    # Pattern: match lines starting with N '#' chars followed by space
    pattern = rf"^({'#' * level})\s+(.+)$"
    sections: list[tuple[str, str]] = []
    current_heading = "Introduction"
    current_lines: list[str] = []

    for line in text.split("\n"):
        match = re.match(pattern, line)
        if match:
            # Save previous section
            if current_lines:
                content = "\n".join(current_lines).strip()
                if content:
                    sections.append((current_heading, content))
            current_heading = match.group(2).strip()
            current_lines = [line]  # Include the heading line itself
        else:
            current_lines.append(line)

    # Don't forget the last section
    if current_lines:
        content = "\n".join(current_lines).strip()
        if content:
            sections.append((current_heading, content))

    return sections


def _split_by_paragraphs(
    text: str,
    max_chars: int,
    base_heading: str,
) -> list[tuple[str, str]]:
    """
    Split text by paragraph boundaries (double newlines) to fit within max_chars.

    Returns:
        List of (heading, content) tuples. Headings are numbered like
        "Section Name (Part 1)", "Section Name (Part 2)", etc.
    """
    paragraphs = re.split(r"\n\n+", text)
    parts: list[tuple[str, str]] = []
    current_part: list[str] = []
    current_size = 0
    part_num = 1

    for para in paragraphs:
        para_size = len(para)

        if current_size + para_size > max_chars and current_part:
            # Flush current part
            heading = f"{base_heading} (Part {part_num})" if part_num > 1 or para_size > 0 else base_heading
            parts.append((heading, "\n\n".join(current_part)))
            current_part = []
            current_size = 0
            part_num += 1

        current_part.append(para)
        current_size += para_size + 2  # +2 for the \n\n separator

    # Flush remaining
    if current_part:
        heading = f"{base_heading} (Part {part_num})" if part_num > 1 else base_heading
        parts.append((heading, "\n\n".join(current_part)))

    return parts
