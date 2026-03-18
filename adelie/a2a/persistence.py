"""
adelie/a2a/persistence.py

Task persistence — stores A2A tasks to disk for durability.
Inspired by Gemini CLI's a2a-server persistence module.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

from adelie.a2a.types import A2ATask, TaskState, A2AEvent, EventType


class TaskStore:
    """
    Persists A2A tasks to JSON files.

    Storage: {store_dir}/{task_id}.json
    """

    def __init__(self, store_dir: Optional[Path] = None):
        if store_dir is None:
            from adelie.config import ADELIE_ROOT
            store_dir = ADELIE_ROOT / "a2a_tasks"
        self._dir = store_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, A2ATask] = {}

    def save(self, task: A2ATask) -> None:
        """Save a task to disk and cache."""
        self._cache[task.task_id] = task
        path = self._dir / f"{task.task_id}.json"
        path.write_text(
            json.dumps(task.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def load(self, task_id: str) -> Optional[A2ATask]:
        """Load a task from cache or disk."""
        if task_id in self._cache:
            return self._cache[task_id]

        path = self._dir / f"{task_id}.json"
        if not path.exists():
            return None

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            task = A2ATask(
                task_id=data["task_id"],
                prompt=data.get("prompt", ""),
                state=TaskState(data.get("state", "submitted")),
                created_at=data.get("created_at", ""),
                updated_at=data.get("updated_at", ""),
                result=data.get("result", ""),
                error=data.get("error", ""),
                metadata=data.get("metadata", {}),
            )
            self._cache[task_id] = task
            return task
        except Exception:
            return None

    def delete(self, task_id: str) -> bool:
        """Delete a task."""
        self._cache.pop(task_id, None)
        path = self._dir / f"{task_id}.json"
        if path.exists():
            path.unlink()
            return True
        return False

    def list_tasks(self) -> list[A2ATask]:
        """List all persisted tasks."""
        tasks = []
        for f in sorted(self._dir.glob("*.json")):
            task = self.load(f.stem)
            if task:
                tasks.append(task)
        return tasks
