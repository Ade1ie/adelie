"""tests/test_checkpoint.py — Tests for the checkpoint system."""
from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def checkpoint_env(tmp_path):
    """Create an isolated checkpoint environment."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    adelie_root = tmp_path / ".adelie"
    adelie_root.mkdir()
    checkpoints_dir = adelie_root / "checkpoints"
    checkpoints_dir.mkdir()

    # Create some project files
    (project_root / "src").mkdir()
    (project_root / "src" / "app.py").write_text("print('hello')", encoding="utf-8")
    (project_root / "src" / "utils.py").write_text("def add(a, b): return a + b", encoding="utf-8")
    (project_root / "README.md").write_text("# My Project", encoding="utf-8")

    return {
        "project_root": project_root,
        "adelie_root": adelie_root,
        "checkpoints_dir": checkpoints_dir,
    }


@pytest.fixture
def mgr(checkpoint_env):
    """Create a CheckpointManager with patched PROJECT_ROOT (stays active)."""
    from adelie.checkpoint import CheckpointManager
    with patch("adelie.checkpoint.PROJECT_ROOT", checkpoint_env["project_root"]):
        yield CheckpointManager(checkpoints_dir=checkpoint_env["checkpoints_dir"])


class TestCheckpointCreate:
    def test_create_checkpoint(self, checkpoint_env, mgr):
        cp = mgr.create(
            files=[
                {"filepath": "src/app.py"},
                {"filepath": "src/utils.py"},
            ],
            cycle=5,
            phase="mid",
        )

        assert cp is not None
        assert cp.cycle == 5
        assert cp.phase == "mid"
        assert len(cp.files) == 2
        assert cp.meta_path.exists()
        assert (cp.files_dir / "src" / "app.py").exists()

    def test_create_checkpoint_empty_files(self, mgr):
        cp = mgr.create(files=[], cycle=1)
        assert cp is None

    def test_create_checkpoint_nonexistent_file(self, mgr):
        """Files that don't exist yet should be recorded as existed=False."""
        cp = mgr.create(
            files=[{"filepath": "new_file.py"}],
            cycle=1,
        )

        assert cp is not None
        assert len(cp.files) == 1
        assert cp.files[0]["existed"] is False
        assert cp.files[0]["size"] == 0

    def test_create_checkpoint_metadata(self, mgr):
        cp = mgr.create(
            files=[{"filepath": "README.md"}],
            cycle=10,
            phase="late",
            description="Test checkpoint",
        )

        meta = json.loads(cp.meta_path.read_text(encoding="utf-8"))
        assert meta["cycle"] == 10
        assert meta["phase"] == "late"
        assert meta["description"] == "Test checkpoint"
        assert len(meta["files"]) == 1


class TestCheckpointRestore:
    def test_restore_modified_file(self, checkpoint_env, mgr):
        project_root = checkpoint_env["project_root"]

        # Create checkpoint with current state
        cp = mgr.create(
            files=[{"filepath": "src/app.py"}],
            cycle=1,
        )

        # Modify the file
        (project_root / "src" / "app.py").write_text("print('modified')", encoding="utf-8")
        assert (project_root / "src" / "app.py").read_text() == "print('modified')"

        # Restore
        result = mgr.restore(cp.checkpoint_id)

        assert result is True
        assert (project_root / "src" / "app.py").read_text() == "print('hello')"

    def test_restore_removes_new_files(self, checkpoint_env, mgr):
        project_root = checkpoint_env["project_root"]

        # Create checkpoint (new_file.py doesn't exist yet)
        cp = mgr.create(
            files=[{"filepath": "new_file.py"}],
            cycle=1,
        )

        # Create the new file (simulating promote)
        (project_root / "new_file.py").write_text("new content")

        # Restore should remove it
        result = mgr.restore(cp.checkpoint_id)

        assert result is True
        assert not (project_root / "new_file.py").exists()

    def test_restore_nonexistent_checkpoint(self, mgr):
        result = mgr.restore("does_not_exist")
        assert result is False


class TestCheckpointList:
    def test_list_empty(self, mgr):
        assert mgr.list_checkpoints() == []

    def test_list_multiple(self, mgr):
        mgr.create(files=[{"filepath": "README.md"}], cycle=1)
        time.sleep(0.05)
        mgr.create(files=[{"filepath": "README.md"}], cycle=2)

        cps = mgr.list_checkpoints()
        assert len(cps) == 2

    def test_get_checkpoint(self, mgr):
        cp = mgr.create(files=[{"filepath": "README.md"}], cycle=3)

        loaded = mgr.get_checkpoint(cp.checkpoint_id)
        assert loaded is not None
        assert loaded.cycle == 3

    def test_get_nonexistent(self, mgr):
        assert mgr.get_checkpoint("nope") is None


class TestCheckpointDelete:
    def test_delete_checkpoint(self, mgr):
        cp = mgr.create(files=[{"filepath": "README.md"}], cycle=1)

        assert mgr.delete(cp.checkpoint_id) is True
        assert mgr.get_checkpoint(cp.checkpoint_id) is None

    def test_delete_nonexistent(self, mgr):
        assert mgr.delete("nope") is False

    def test_clear_all(self, mgr):
        mgr.create(files=[{"filepath": "README.md"}], cycle=1)
        time.sleep(0.05)
        mgr.create(files=[{"filepath": "README.md"}], cycle=2)

        count = mgr.clear_all()
        assert count == 2
        assert mgr.list_checkpoints() == []


class TestCheckpointPrune:
    def test_auto_prune(self, checkpoint_env):
        """Verify auto-prune keeps only MAX_CHECKPOINTS newest."""
        from adelie.checkpoint import CheckpointManager

        with patch("adelie.checkpoint.PROJECT_ROOT", checkpoint_env["project_root"]):
            with patch("adelie.checkpoint.MAX_CHECKPOINTS", 3):
                mgr = CheckpointManager(checkpoints_dir=checkpoint_env["checkpoints_dir"])
                ids = []
                for i in range(5):
                    cp = mgr.create(files=[{"filepath": "README.md"}], cycle=i)
                    ids.append(cp.checkpoint_id)
                    time.sleep(0.05)  # Ensure unique timestamps for sort

                cps = mgr.list_checkpoints()
                assert len(cps) == 3
                # Newest should survive
                assert cps[0].cycle == 4


class TestCheckpointDataclass:
    def test_checkpoint_properties(self):
        from adelie.checkpoint import Checkpoint, CHECKPOINTS_DIR
        cp = Checkpoint(
            checkpoint_id="test_001",
            created_at="2024-01-01T00:00:00",
            cycle=1,
            phase="initial",
            files=[],
        )
        assert cp.path == CHECKPOINTS_DIR / "test_001"
        assert cp.meta_path == CHECKPOINTS_DIR / "test_001" / "meta.json"
        assert cp.files_dir == CHECKPOINTS_DIR / "test_001" / "files"
