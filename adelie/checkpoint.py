"""
adelie/checkpoint.py

Checkpoint system for safe rollback of file modifications.

Before promoting staged files to the project, a checkpoint is created
that captures the current state of affected files. This allows instant
rollback via the CLI's /restore command.

Inspired by gemini-cli's checkpointing system (shadow Git snapshots +
conversation/tool state).
"""

from __future__ import annotations

import json
import shutil
import time
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from rich.console import Console

from adelie.config import ADELIE_ROOT, PROJECT_ROOT

console = Console()

# ── Constants ────────────────────────────────────────────────────────────────

CHECKPOINTS_DIR = ADELIE_ROOT / "checkpoints"
MAX_CHECKPOINTS = 20  # Auto-prune oldest beyond this


@dataclass
class Checkpoint:
    """A saved snapshot of project state."""
    checkpoint_id: str
    created_at: str
    cycle: int
    phase: str
    files: list[dict]          # [{filepath, existed, size}]
    description: str = ""
    _base_dir: Path = field(default_factory=lambda: CHECKPOINTS_DIR, repr=False)

    @property
    def path(self) -> Path:
        return self._base_dir / self.checkpoint_id

    @property
    def meta_path(self) -> Path:
        return self.path / "meta.json"

    @property
    def files_dir(self) -> Path:
        return self.path / "files"


class CheckpointManager:
    """
    Manages project state checkpoints for safe rollback.

    Usage:
        mgr = CheckpointManager()
        cp = mgr.create(files=[{"filepath": "src/app.py"}], cycle=5, phase="mid")
        mgr.list_checkpoints()
        mgr.restore(checkpoint_id)
    """

    def __init__(self, checkpoints_dir: Optional[Path] = None):
        self._dir = checkpoints_dir or CHECKPOINTS_DIR
        self._dir.mkdir(parents=True, exist_ok=True)

    # ── Create ───────────────────────────────────────────────────────────

    def create(
        self,
        files: list[dict],
        cycle: int = 0,
        phase: str = "",
        description: str = "",
    ) -> Optional[Checkpoint]:
        """
        Create a checkpoint by snapshotting the current state of target files.

        Args:
            files: List of dicts with 'filepath' keys (relative to PROJECT_ROOT).
            cycle: Current orchestrator loop iteration.
            phase: Current project phase.
            description: Human-readable description.

        Returns:
            Checkpoint object, or None if no files to checkpoint.
        """
        if not files:
            return None

        ts = datetime.now()
        checkpoint_id = ts.strftime("%Y%m%d_%H%M%S") + f"_cycle{cycle}"

        cp = Checkpoint(
            checkpoint_id=checkpoint_id,
            created_at=ts.isoformat(timespec="seconds"),
            cycle=cycle,
            phase=phase,
            files=[],
            description=description or f"Auto-checkpoint before cycle #{cycle} promote",
            _base_dir=self._dir,
        )

        # Create checkpoint directory
        cp.files_dir.mkdir(parents=True, exist_ok=True)

        # Snapshot each file
        for finfo in files:
            filepath = finfo.get("filepath", "")
            if not filepath:
                continue

            source = PROJECT_ROOT / filepath
            file_record = {
                "filepath": filepath,
                "existed": source.exists(),
                "size": source.stat().st_size if source.exists() else 0,
            }

            if source.exists():
                # Copy the current version to checkpoint
                dest = cp.files_dir / filepath
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, dest)

            cp.files.append(file_record)

        # Save metadata
        meta = {
            "checkpoint_id": cp.checkpoint_id,
            "created_at": cp.created_at,
            "cycle": cp.cycle,
            "phase": cp.phase,
            "description": cp.description,
            "files": cp.files,
        }
        cp.meta_path.write_text(
            json.dumps(meta, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        console.print(
            f"[dim]💾 Checkpoint created: {checkpoint_id} "
            f"({len(cp.files)} file(s))[/dim]"
        )

        # Auto-prune old checkpoints
        self._prune()

        return cp

    # ── Restore ──────────────────────────────────────────────────────────

    def restore(self, checkpoint_id: str) -> bool:
        """
        Restore project files to a checkpoint state.

        Files that existed at checkpoint time are restored.
        Files that did NOT exist at checkpoint time are deleted (new files removed).

        Args:
            checkpoint_id: ID of the checkpoint to restore.

        Returns:
            True if restore succeeded.
        """
        cp = self._load_checkpoint(checkpoint_id)
        if not cp:
            console.print(f"[red]❌ Checkpoint not found: {checkpoint_id}[/red]")
            return False

        restored = 0
        removed = 0

        for file_record in cp.files:
            filepath = file_record["filepath"]
            target = PROJECT_ROOT / filepath

            if file_record["existed"]:
                # Restore from checkpoint
                source = cp.files_dir / filepath
                if source.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
                    restored += 1
            else:
                # File was new — remove it
                if target.exists():
                    target.unlink()
                    removed += 1

        console.print(
            f"[bold green]✅ Restored checkpoint {checkpoint_id}: "
            f"{restored} restored, {removed} removed[/bold green]"
        )
        return True

    # ── List ─────────────────────────────────────────────────────────────

    def list_checkpoints(self) -> list[Checkpoint]:
        """List all available checkpoints, newest first."""
        checkpoints = []
        if not self._dir.exists():
            return checkpoints

        for cp_dir in sorted(self._dir.iterdir(), reverse=True):
            if not cp_dir.is_dir():
                continue
            meta_file = cp_dir / "meta.json"
            if not meta_file.exists():
                continue
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                checkpoints.append(Checkpoint(
                    checkpoint_id=meta["checkpoint_id"],
                    created_at=meta["created_at"],
                    cycle=meta.get("cycle", 0),
                    phase=meta.get("phase", ""),
                    files=meta.get("files", []),
                    description=meta.get("description", ""),
                    _base_dir=self._dir,
                ))
            except Exception:
                continue

        return checkpoints

    def get_checkpoint(self, checkpoint_id: str) -> Optional[Checkpoint]:
        """Get a specific checkpoint by ID."""
        return self._load_checkpoint(checkpoint_id)

    # ── Delete ───────────────────────────────────────────────────────────

    def delete(self, checkpoint_id: str) -> bool:
        """Delete a specific checkpoint."""
        cp_path = self._dir / checkpoint_id
        if cp_path.exists() and cp_path.is_dir():
            shutil.rmtree(cp_path)
            return True
        return False

    def clear_all(self) -> int:
        """Delete all checkpoints. Returns count deleted."""
        checkpoints = self.list_checkpoints()
        for cp in checkpoints:
            self.delete(cp.checkpoint_id)
        return len(checkpoints)

    # ── Helpers ──────────────────────────────────────────────────────────

    def _load_checkpoint(self, checkpoint_id: str) -> Optional[Checkpoint]:
        """Load checkpoint metadata from disk."""
        meta_file = self._dir / checkpoint_id / "meta.json"
        if not meta_file.exists():
            return None
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            return Checkpoint(
                checkpoint_id=meta["checkpoint_id"],
                created_at=meta["created_at"],
                cycle=meta.get("cycle", 0),
                phase=meta.get("phase", ""),
                files=meta.get("files", []),
                description=meta.get("description", ""),
                _base_dir=self._dir,
            )
        except Exception:
            return None

    def _prune(self) -> int:
        """Remove oldest checkpoints if beyond MAX_CHECKPOINTS."""
        checkpoints = self.list_checkpoints()
        if len(checkpoints) <= MAX_CHECKPOINTS:
            return 0

        pruned = 0
        for cp in checkpoints[MAX_CHECKPOINTS:]:
            self.delete(cp.checkpoint_id)
            pruned += 1

        if pruned:
            console.print(f"[dim]🗑️  Pruned {pruned} old checkpoint(s)[/dim]")
        return pruned
