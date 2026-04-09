"""
adelie/memory_harness.py

Selective Forgetting — Memory Harness for context focus management.

Prevents context derailment in long sessions by enforcing "blindfolds"
on AI agents, limiting their view to only current-phase-relevant knowledge.

Three mechanisms:
  1. Phase Scope Filter — KB files tagged with phase_scope are only visible
     in their designated phases.
  2. Archive Manager — Resolved errors and completed-phase docs are moved
     to archive/, removing them from active queries.
  3. Summary Tree — Archived docs get a 1-2 line summary preserved in
     archive/summaries.md for minimal historical context.

Integration points:
  - retriever.query() / semantic_query() — phase-aware filtering
  - orchestrator.py — phase transition hook triggers archiving
  - context_engine.py — archive summary injected as a small context section
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console

console = Console()


# ── Module-level singleton ───────────────────────────────────────────────────

_harness_instance: Optional["MemoryHarness"] = None


def get_memory_harness() -> MemoryHarness:
    """Get or create the module-level MemoryHarness singleton."""
    global _harness_instance
    if _harness_instance is None:
        _harness_instance = MemoryHarness()
    return _harness_instance


def reset_memory_harness() -> None:
    """Reset the singleton (for tests)."""
    global _harness_instance
    _harness_instance = None


# ── Phase Group Mapping ──────────────────────────────────────────────────────

# Maps individual phase names to broader groups for scope matching.
# e.g., "mid_1" and "mid_2" both belong to the "mid" group.
_PHASE_GROUPS: dict[str, list[str]] = {
    "initial": ["initial"],
    "mid":     ["mid", "mid_1", "mid_2"],
    "mid_1":   ["mid", "mid_1"],
    "mid_2":   ["mid", "mid_2"],
    "late":    ["late"],
    "evolve":  ["evolve"],
}


def _get_phase_group(phase: str) -> set[str]:
    """
    Get all phase identifiers that the given phase belongs to.
    Used for scope matching: if a file is scoped to "mid", it matches mid_1 and mid_2.
    """
    groups = {phase}  # Always includes itself
    for group_name, members in _PHASE_GROUPS.items():
        if phase in members:
            groups.add(group_name)
            groups.update(members)
    return groups


# ── MemoryHarness ────────────────────────────────────────────────────────────


class MemoryHarness:
    """
    Controls what knowledge is visible to AI agents based on the current phase.

    Acts as a "blindfold" — agents only see KB files relevant to their
    current work phase, reducing hallucination from stale context.
    """

    def __init__(self, workspace_path: Path | None = None):
        if workspace_path is None:
            try:
                from adelie.config import WORKSPACE_PATH
                workspace_path = WORKSPACE_PATH
            except Exception:
                workspace_path = Path.cwd() / ".adelie" / "workspace"

        self._workspace = workspace_path
        self._archive_dir = workspace_path / "archive"
        self._summaries_path = self._archive_dir / "summaries.md"

        # Track when each KB file was last referenced (for staleness detection)
        self._reference_tracker: dict[str, int] = {}  # rel_path → last_cycle
        self._current_cycle: int = 0

        # Default staleness threshold (cycles without reference before archiving)
        self.error_stale_cycles: int = 3

    # ── Phase Scope Filter ───────────────────────────────────────────────

    def filter_by_phase(
        self,
        paths: list[Path],
        current_phase: str,
    ) -> list[Path]:
        """
        Filter KB file paths to only those visible in the current phase.

        Rules:
          - Files with no phase_scope → always visible (backward compatible)
          - Files with phase_scope → visible only if current_phase matches

        Args:
            paths: List of KB file paths to filter
            current_phase: Current project phase (e.g., "mid_1")

        Returns:
            Filtered list of paths visible in this phase.
        """
        if not current_phase or not paths:
            return paths

        try:
            index = self._get_index()
        except Exception:
            return paths  # Can't load index — don't filter

        phase_groups = _get_phase_group(current_phase)
        filtered: list[Path] = []

        for p in paths:
            try:
                rel = p.relative_to(self._workspace).as_posix()
            except ValueError:
                filtered.append(p)  # Not in workspace — don't filter
                continue

            entry = index.get(rel, {})
            scope = entry.get("phase_scope", [])

            # No scope = always visible
            if not scope:
                filtered.append(p)
                continue

            # Check if any scope entry matches current phase groups
            if any(s in phase_groups for s in scope):
                filtered.append(p)

        return filtered

    def set_phase_scope(
        self,
        relative_path: str,
        phases: list[str],
    ) -> None:
        """
        Set the phase_scope for a KB file in the index.

        Args:
            relative_path: Path relative to workspace (e.g., "skills/roadmap.md")
            phases: List of phases this file should be visible in
        """
        index = self._get_index()
        if relative_path in index:
            index[relative_path]["phase_scope"] = phases
        else:
            index[relative_path] = {
                "tags": [],
                "summary": "",
                "phase_scope": phases,
                "updated": datetime.now().isoformat(timespec="seconds"),
            }
        self._save_index(index)

    def auto_tag_phase(
        self,
        relative_path: str,
        current_phase: str,
    ) -> None:
        """
        Automatically add current_phase to a file's phase_scope.
        Called when Writer AI creates a new KB file.

        If the file has no phase_scope yet, creates one with the current phase.
        If it already has one, appends the current phase.
        """
        index = self._get_index()
        entry = index.get(relative_path, {})
        scope = entry.get("phase_scope", [])

        if current_phase not in scope:
            scope.append(current_phase)

        if relative_path in index:
            index[relative_path]["phase_scope"] = scope
        else:
            index[relative_path] = {
                "tags": [],
                "summary": "",
                "phase_scope": scope,
                "updated": datetime.now().isoformat(timespec="seconds"),
            }
        self._save_index(index)

    # ── Reference Tracking (for staleness) ───────────────────────────────

    def record_reference(self, relative_path: str, cycle: int) -> None:
        """Record that a KB file was referenced in a given cycle."""
        self._reference_tracker[relative_path] = cycle
        self._current_cycle = max(self._current_cycle, cycle)

    def update_cycle(self, cycle: int) -> None:
        """Update the current cycle counter."""
        self._current_cycle = cycle

    def _is_stale(self, relative_path: str, stale_cycles: int | None = None) -> bool:
        """
        Check if a KB file is stale (not referenced for N cycles).

        Args:
            relative_path: File path relative to workspace
            stale_cycles: Override threshold (default: self.error_stale_cycles)

        Returns:
            True if the file hasn't been referenced for stale_cycles cycles.
        """
        threshold = stale_cycles if stale_cycles is not None else self.error_stale_cycles
        last_ref = self._reference_tracker.get(relative_path, 0)
        return (self._current_cycle - last_ref) >= threshold

    # ── Archive Manager ──────────────────────────────────────────────────

    def archive_resolved_errors(self) -> int:
        """
        Archive error files that haven't been referenced for N cycles.
        Moves them to archive/errors/ and adds summaries.

        Returns:
            Number of files archived.
        """
        errors_dir = self._workspace / "errors"
        if not errors_dir.exists():
            return 0

        archive_errors = self._archive_dir / "errors"
        archived = 0

        for error_file in list(errors_dir.glob("*.md")):
            rel = f"errors/{error_file.name}"
            if self._is_stale(rel):
                summary = self._extract_summary(error_file)
                self._archive_file(error_file, archive_errors)
                self._add_summary(rel, summary, "resolved error")
                self._remove_from_index(rel)
                archived += 1

        if archived:
            console.print(
                f"[dim]🧹 Memory Harness: archived {archived} resolved error(s)[/dim]"
            )

        return archived

    def on_phase_transition(self, old_phase: str, new_phase: str) -> int:
        """
        Archive KB files that are scoped to the old phase but NOT the new phase.
        Called by the orchestrator when a phase transition occurs.

        Args:
            old_phase: Phase we're leaving
            new_phase: Phase we're entering

        Returns:
            Number of files archived.
        """
        index = self._get_index()
        new_groups = _get_phase_group(new_phase)
        archived = 0

        for rel_path, entry in list(index.items()):
            scope = entry.get("phase_scope", [])
            if not scope:
                continue  # No scope → global — don't archive

            # File is scoped to old phase, but NOT to new phase
            old_match = any(s in _get_phase_group(old_phase) for s in scope)
            new_match = any(s in new_groups for s in scope)

            if old_match and not new_match:
                file_path = self._workspace / rel_path
                if file_path.exists():
                    category = rel_path.split("/")[0] if "/" in rel_path else "general"
                    archive_dest = self._archive_dir / category
                    summary = self._extract_summary(file_path)
                    self._archive_file(file_path, archive_dest)
                    self._add_summary(
                        rel_path, summary,
                        f"phase transition: {old_phase} → {new_phase}",
                    )
                    self._remove_from_index(rel_path)
                    archived += 1

        if archived:
            console.print(
                f"[dim]🧹 Memory Harness: archived {archived} file(s) on "
                f"{old_phase} → {new_phase}[/dim]"
            )

        return archived

    def _archive_file(self, source: Path, archive_dir: Path) -> None:
        """Move a file from active KB to archive directory."""
        archive_dir.mkdir(parents=True, exist_ok=True)
        dest = archive_dir / source.name

        # Avoid overwriting — add timestamp suffix if conflict
        if dest.exists():
            ts = datetime.now().strftime("%H%M%S")
            stem = source.stem
            dest = archive_dir / f"{stem}_{ts}{source.suffix}"

        shutil.move(str(source), str(dest))

    def _remove_from_index(self, relative_path: str) -> None:
        """Remove a file entry from the KB index."""
        index = self._get_index()
        if relative_path in index:
            del index[relative_path]
            self._save_index(index)

    # ── Summary Tree ─────────────────────────────────────────────────────

    def _extract_summary(self, file_path: Path) -> str:
        """Extract a 1-2 line summary from a KB file."""
        try:
            content = file_path.read_text(encoding="utf-8").strip()
        except Exception:
            return f"(could not read {file_path.name})"

        lines = content.splitlines()

        # Try to find a summary line
        for line in lines[:10]:
            stripped = line.strip()
            # Skip headers, empty lines, and metadata
            if stripped.startswith("#") and len(stripped) > 2:
                return stripped.lstrip("#").strip()[:120]

        # Fallback: first non-empty, non-header line
        for line in lines[:10]:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and not stripped.startswith("---"):
                return stripped[:120]

        return f"(content from {file_path.name})"

    def _add_summary(
        self,
        relative_path: str,
        summary: str,
        reason: str,
    ) -> None:
        """Append a summary entry to the archive summaries file."""
        self._archive_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = f"- **{relative_path}** [{reason}]: {summary}\n"

        # Append to summaries.md
        if self._summaries_path.exists():
            existing = self._summaries_path.read_text(encoding="utf-8")
        else:
            existing = "# Archived Knowledge Summaries\n\n"
            existing += "This file contains summaries of archived KB files.\n"
            existing += "Full contents are preserved in archive/ subdirectories.\n\n"

        # Add under current timestamp section
        section_header = f"## Archived at {ts}\n"
        if section_header not in existing:
            existing += f"\n{section_header}"

        existing += entry
        self._summaries_path.write_text(existing, encoding="utf-8")

    def get_archive_summary(self) -> str:
        """
        Get the archive summaries text for injection into agent context.
        Returns empty string if no summaries exist.
        """
        if not self._summaries_path.exists():
            return ""

        try:
            content = self._summaries_path.read_text(encoding="utf-8").strip()
            if not content or content == "# Archived Knowledge Summaries":
                return ""
            return content
        except Exception:
            return ""

    # ── Index Helpers ────────────────────────────────────────────────────

    def _get_index(self) -> dict:
        """Load the KB index."""
        index_path = self._workspace / "index.json"
        if not index_path.exists():
            return {}
        try:
            return json.loads(index_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, Exception):
            return {}

    def _save_index(self, index: dict) -> None:
        """Save the KB index."""
        index_path = self._workspace / "index.json"
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(
            json.dumps(index, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # ── Stats ────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Get memory harness statistics for monitoring."""
        archive_count = 0
        if self._archive_dir.exists():
            for f in self._archive_dir.rglob("*"):
                if f.is_file() and f.name != "summaries.md":
                    archive_count += 1

        index = self._get_index()
        scoped_count = sum(
            1 for entry in index.values()
            if entry.get("phase_scope")
        )

        return {
            "active_kb_files": len(index),
            "phase_scoped_files": scoped_count,
            "archived_files": archive_count,
            "tracked_references": len(self._reference_tracker),
            "current_cycle": self._current_cycle,
            "has_summaries": self._summaries_path.exists(),
        }
