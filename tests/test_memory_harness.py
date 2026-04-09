"""
tests/test_memory_harness.py

Tests for the Memory Harness — selective forgetting system.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest


# ── Phase Group Tests ────────────────────────────────────────────────────────


class TestPhaseGroups:
    def test_exact_phase(self):
        from adelie.memory_harness import _get_phase_group
        groups = _get_phase_group("initial")
        assert "initial" in groups

    def test_mid_group(self):
        from adelie.memory_harness import _get_phase_group
        groups = _get_phase_group("mid_1")
        assert "mid_1" in groups
        assert "mid" in groups  # mid_1 belongs to "mid" group

    def test_mid_2_group(self):
        from adelie.memory_harness import _get_phase_group
        groups = _get_phase_group("mid_2")
        assert "mid_2" in groups
        assert "mid" in groups

    def test_unknown_phase(self):
        from adelie.memory_harness import _get_phase_group
        groups = _get_phase_group("custom_phase")
        assert "custom_phase" in groups  # Always includes itself
        assert len(groups) == 1


# ── Phase Scope Filter Tests ────────────────────────────────────────────────


class TestPhaseScopeFilter:
    def _setup_workspace(self, tmp_path):
        """Create a workspace with index and KB files."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "skills").mkdir()
        (workspace / "logic").mkdir()

        # Create KB files
        (workspace / "skills" / "roadmap.md").write_text("# Roadmap\nProject plan", encoding="utf-8")
        (workspace / "skills" / "auth.md").write_text("# Auth\nAuth guide", encoding="utf-8")
        (workspace / "logic" / "deploy.md").write_text("# Deploy\nDeploy guide", encoding="utf-8")
        (workspace / "logic" / "general.md").write_text("# General\nGeneral notes", encoding="utf-8")

        # Create index with phase_scope
        index = {
            "skills/roadmap.md": {
                "tags": ["roadmap"],
                "summary": "Project roadmap",
                "phase_scope": ["initial"],
                "updated": "2026-01-01T00:00:00",
            },
            "skills/auth.md": {
                "tags": ["auth"],
                "summary": "Auth guide",
                "phase_scope": ["mid", "late"],
                "updated": "2026-01-01T00:00:00",
            },
            "logic/deploy.md": {
                "tags": ["deploy"],
                "summary": "Deploy guide",
                "phase_scope": ["late", "evolve"],
                "updated": "2026-01-01T00:00:00",
            },
            "logic/general.md": {
                "tags": ["general"],
                "summary": "General notes",
                # No phase_scope — global visibility
                "updated": "2026-01-01T00:00:00",
            },
        }
        (workspace / "index.json").write_text(
            json.dumps(index, indent=2), encoding="utf-8"
        )
        return workspace

    def test_filter_initial_phase(self, tmp_path):
        from adelie.memory_harness import MemoryHarness
        workspace = self._setup_workspace(tmp_path)
        harness = MemoryHarness(workspace_path=workspace)

        paths = [
            workspace / "skills" / "roadmap.md",
            workspace / "skills" / "auth.md",
            workspace / "logic" / "deploy.md",
            workspace / "logic" / "general.md",
        ]

        filtered = harness.filter_by_phase(paths, "initial")
        names = [p.name for p in filtered]

        assert "roadmap.md" in names   # scoped to initial ✓
        assert "general.md" in names   # no scope = global ✓
        assert "auth.md" not in names  # scoped to mid/late ✗
        assert "deploy.md" not in names  # scoped to late/evolve ✗

    def test_filter_mid_1_phase(self, tmp_path):
        from adelie.memory_harness import MemoryHarness
        workspace = self._setup_workspace(tmp_path)
        harness = MemoryHarness(workspace_path=workspace)

        paths = [
            workspace / "skills" / "roadmap.md",
            workspace / "skills" / "auth.md",
            workspace / "logic" / "general.md",
        ]

        filtered = harness.filter_by_phase(paths, "mid_1")
        names = [p.name for p in filtered]

        assert "roadmap.md" not in names  # scoped to initial only ✗
        assert "auth.md" in names         # scoped to mid → mid_1 matches ✓
        assert "general.md" in names      # global ✓

    def test_no_phase_returns_all(self, tmp_path):
        from adelie.memory_harness import MemoryHarness
        workspace = self._setup_workspace(tmp_path)
        harness = MemoryHarness(workspace_path=workspace)

        paths = [
            workspace / "skills" / "roadmap.md",
            workspace / "skills" / "auth.md",
        ]

        # No phase = return all
        filtered = harness.filter_by_phase(paths, "")
        assert len(filtered) == 2

    def test_empty_paths(self, tmp_path):
        from adelie.memory_harness import MemoryHarness
        workspace = self._setup_workspace(tmp_path)
        harness = MemoryHarness(workspace_path=workspace)
        assert harness.filter_by_phase([], "initial") == []


# ── Phase Scope Tagging ──────────────────────────────────────────────────────


class TestPhaseScoping:
    def test_set_phase_scope(self, tmp_path):
        from adelie.memory_harness import MemoryHarness
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "index.json").write_text("{}", encoding="utf-8")

        harness = MemoryHarness(workspace_path=workspace)
        harness.set_phase_scope("skills/new.md", ["initial", "mid"])

        index = json.loads((workspace / "index.json").read_text(encoding="utf-8"))
        assert index["skills/new.md"]["phase_scope"] == ["initial", "mid"]

    def test_auto_tag_phase(self, tmp_path):
        from adelie.memory_harness import MemoryHarness
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        index = {"skills/doc.md": {"tags": ["test"], "summary": "A doc"}}
        (workspace / "index.json").write_text(json.dumps(index), encoding="utf-8")

        harness = MemoryHarness(workspace_path=workspace)
        harness.auto_tag_phase("skills/doc.md", "mid_1")

        updated = json.loads((workspace / "index.json").read_text(encoding="utf-8"))
        assert "mid_1" in updated["skills/doc.md"]["phase_scope"]

    def test_auto_tag_no_duplicate(self, tmp_path):
        from adelie.memory_harness import MemoryHarness
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        index = {"skills/doc.md": {"tags": [], "summary": "", "phase_scope": ["mid_1"]}}
        (workspace / "index.json").write_text(json.dumps(index), encoding="utf-8")

        harness = MemoryHarness(workspace_path=workspace)
        harness.auto_tag_phase("skills/doc.md", "mid_1")

        updated = json.loads((workspace / "index.json").read_text(encoding="utf-8"))
        assert updated["skills/doc.md"]["phase_scope"].count("mid_1") == 1


# ── Staleness Detection ──────────────────────────────────────────────────────


class TestStaleness:
    def test_fresh_reference(self, tmp_path):
        from adelie.memory_harness import MemoryHarness
        harness = MemoryHarness(workspace_path=tmp_path)
        harness.update_cycle(5)
        harness.record_reference("errors/e1.md", 5)
        assert not harness._is_stale("errors/e1.md")

    def test_stale_reference(self, tmp_path):
        from adelie.memory_harness import MemoryHarness
        harness = MemoryHarness(workspace_path=tmp_path)
        harness.record_reference("errors/e1.md", 1)
        harness.update_cycle(5)  # 4 cycles later
        assert harness._is_stale("errors/e1.md")  # default threshold = 3

    def test_never_referenced(self, tmp_path):
        from adelie.memory_harness import MemoryHarness
        harness = MemoryHarness(workspace_path=tmp_path)
        harness.update_cycle(5)
        assert harness._is_stale("errors/unknown.md")

    def test_custom_threshold(self, tmp_path):
        from adelie.memory_harness import MemoryHarness
        harness = MemoryHarness(workspace_path=tmp_path)
        harness.record_reference("errors/e1.md", 3)
        harness.update_cycle(5)
        assert not harness._is_stale("errors/e1.md", stale_cycles=3)  # 2 < 3
        assert harness._is_stale("errors/e1.md", stale_cycles=2)     # 2 >= 2


# ── Archive Manager ──────────────────────────────────────────────────────────


class TestArchiveManager:
    def test_archive_resolved_errors(self, tmp_path):
        from adelie.memory_harness import MemoryHarness
        workspace = tmp_path / "workspace"
        errors_dir = workspace / "errors"
        errors_dir.mkdir(parents=True)

        # Create error files
        (errors_dir / "error_1.md").write_text("# Error 1\nSome error", encoding="utf-8")
        (errors_dir / "error_2.md").write_text("# Error 2\nAnother error", encoding="utf-8")

        # Create index
        index = {
            "errors/error_1.md": {"tags": ["error"], "summary": "Error 1"},
            "errors/error_2.md": {"tags": ["error"], "summary": "Error 2"},
        }
        (workspace / "index.json").write_text(json.dumps(index), encoding="utf-8")

        harness = MemoryHarness(workspace_path=workspace)
        harness.update_cycle(5)
        # Don't record any references — both errors are stale

        archived = harness.archive_resolved_errors()

        assert archived == 2
        assert not (errors_dir / "error_1.md").exists()  # Moved
        assert not (errors_dir / "error_2.md").exists()  # Moved
        assert (workspace / "archive" / "errors" / "error_1.md").exists()
        assert (workspace / "archive" / "errors" / "error_2.md").exists()

    def test_no_archive_fresh_errors(self, tmp_path):
        from adelie.memory_harness import MemoryHarness
        workspace = tmp_path / "workspace"
        errors_dir = workspace / "errors"
        errors_dir.mkdir(parents=True)

        (errors_dir / "recent.md").write_text("# Recent Error", encoding="utf-8")
        (workspace / "index.json").write_text("{}", encoding="utf-8")

        harness = MemoryHarness(workspace_path=workspace)
        harness.update_cycle(3)
        harness.record_reference("errors/recent.md", 2)  # Referenced 1 cycle ago

        archived = harness.archive_resolved_errors()
        assert archived == 0
        assert (errors_dir / "recent.md").exists()  # Still active

    def test_on_phase_transition(self, tmp_path):
        from adelie.memory_harness import MemoryHarness
        workspace = tmp_path / "workspace"
        skills_dir = workspace / "skills"
        skills_dir.mkdir(parents=True)

        (skills_dir / "roadmap.md").write_text("# Roadmap\nPhase 1 plan", encoding="utf-8")
        (skills_dir / "global.md").write_text("# Global\nAlways needed", encoding="utf-8")

        index = {
            "skills/roadmap.md": {
                "tags": ["roadmap"],
                "summary": "Roadmap",
                "phase_scope": ["initial"],
            },
            "skills/global.md": {
                "tags": ["general"],
                "summary": "Global notes",
                # No phase_scope — should NOT be archived
            },
        }
        (workspace / "index.json").write_text(json.dumps(index), encoding="utf-8")

        harness = MemoryHarness(workspace_path=workspace)
        archived = harness.on_phase_transition("initial", "mid_1")

        assert archived == 1
        assert not (skills_dir / "roadmap.md").exists()  # Archived
        assert (skills_dir / "global.md").exists()        # Untouched
        assert (workspace / "archive" / "skills" / "roadmap.md").exists()


# ── Summary Tree ─────────────────────────────────────────────────────────────


class TestSummaryTree:
    def test_extract_summary_from_header(self, tmp_path):
        from adelie.memory_harness import MemoryHarness
        harness = MemoryHarness(workspace_path=tmp_path)

        file = tmp_path / "test.md"
        file.write_text("# API Timeout Fix\n\nDetailed content...", encoding="utf-8")
        summary = harness._extract_summary(file)
        assert "API Timeout Fix" in summary

    def test_extract_summary_fallback(self, tmp_path):
        from adelie.memory_harness import MemoryHarness
        harness = MemoryHarness(workspace_path=tmp_path)

        file = tmp_path / "test.md"
        file.write_text("No headers here, just plain text.", encoding="utf-8")
        summary = harness._extract_summary(file)
        assert "No headers here" in summary

    def test_add_and_get_summary(self, tmp_path):
        from adelie.memory_harness import MemoryHarness
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "index.json").write_text("{}", encoding="utf-8")

        harness = MemoryHarness(workspace_path=workspace)
        harness._add_summary("errors/old.md", "API timeout resolved", "resolved error")
        harness._add_summary("skills/roadmap.md", "Project plan Phase 1", "phase transition")

        summary = harness.get_archive_summary()
        assert "old.md" in summary
        assert "API timeout resolved" in summary
        assert "roadmap.md" in summary
        assert "Project plan Phase 1" in summary

    def test_empty_archive_summary(self, tmp_path):
        from adelie.memory_harness import MemoryHarness
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        harness = MemoryHarness(workspace_path=workspace)
        assert harness.get_archive_summary() == ""


# ── Singleton Tests ──────────────────────────────────────────────────────────


class TestSingleton:
    def test_reset(self):
        from adelie.memory_harness import get_memory_harness, reset_memory_harness

        h1 = get_memory_harness()
        reset_memory_harness()
        h2 = get_memory_harness()
        assert h1 is not h2


# ── Stats Tests ──────────────────────────────────────────────────────────────


class TestStats:
    def test_get_stats(self, tmp_path):
        from adelie.memory_harness import MemoryHarness
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        index = {
            "skills/a.md": {"tags": [], "summary": "", "phase_scope": ["initial"]},
            "logic/b.md": {"tags": [], "summary": ""},
        }
        (workspace / "index.json").write_text(json.dumps(index), encoding="utf-8")

        harness = MemoryHarness(workspace_path=workspace)
        harness.update_cycle(3)
        stats = harness.get_stats()

        assert stats["active_kb_files"] == 2
        assert stats["phase_scoped_files"] == 1
        assert stats["current_cycle"] == 3


# ── Integration: Retriever Phase Filter ──────────────────────────────────────


class TestRetrieverIntegration:
    def test_query_with_no_phase_backward_compat(self, tmp_path, monkeypatch):
        """query() without current_phase returns all files (backward compatible)."""
        from adelie.kb import retriever

        workspace = tmp_path / "workspace"
        skills_dir = workspace / "skills"
        skills_dir.mkdir(parents=True)
        (skills_dir / "a.md").write_text("A", encoding="utf-8")

        index = {"skills/a.md": {"tags": ["test"], "summary": "A", "phase_scope": ["initial"]}}
        (workspace / "index.json").write_text(json.dumps(index), encoding="utf-8")

        monkeypatch.setattr(retriever, "WORKSPACE_PATH", workspace)
        monkeypatch.setattr(retriever, "INDEX_FILE", workspace / "index.json")
        monkeypatch.setattr(retriever, "SITUATION_CATEGORY_MAP", {"normal": ["skills"]})

        # No current_phase → should return all
        results = retriever.query("normal")
        assert len(results) == 1

    def test_query_with_phase_filters(self, tmp_path, monkeypatch):
        """query() with current_phase filters by phase scope."""
        from adelie.kb import retriever
        from adelie.memory_harness import reset_memory_harness

        reset_memory_harness()

        workspace = tmp_path / "workspace"
        skills_dir = workspace / "skills"
        skills_dir.mkdir(parents=True)
        (skills_dir / "early.md").write_text("Early doc", encoding="utf-8")
        (skills_dir / "late_only.md").write_text("Late doc", encoding="utf-8")

        index = {
            "skills/early.md": {"tags": ["test"], "summary": "E", "phase_scope": ["initial"]},
            "skills/late_only.md": {"tags": ["test"], "summary": "L", "phase_scope": ["late"]},
        }
        (workspace / "index.json").write_text(json.dumps(index), encoding="utf-8")

        monkeypatch.setattr(retriever, "WORKSPACE_PATH", workspace)
        monkeypatch.setattr(retriever, "INDEX_FILE", workspace / "index.json")
        monkeypatch.setattr(retriever, "SITUATION_CATEGORY_MAP", {"normal": ["skills"]})

        # Patch MemoryHarness to use this workspace
        from adelie import memory_harness
        original_init = memory_harness.MemoryHarness.__init__

        def patched_init(self, workspace_path=None):
            original_init(self, workspace_path=workspace)

        monkeypatch.setattr(memory_harness.MemoryHarness, "__init__", patched_init)

        results = retriever.query("normal", current_phase="initial")
        names = [p.name for p in results]
        assert "early.md" in names
        assert "late_only.md" not in names
