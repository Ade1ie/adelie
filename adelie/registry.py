"""
adelie/registry.py

Global workspace registry — stored in ~/.adelie/registry.json.
Tracks all initialized workspaces across the system.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

REGISTRY_DIR = Path.home() / ".adelie"
REGISTRY_FILE = REGISTRY_DIR / "registry.json"


def _ensure_registry() -> None:
    REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    if not REGISTRY_FILE.exists():
        REGISTRY_FILE.write_text("[]", encoding="utf-8")


def get_all() -> list[dict]:
    """Return all registered workspaces."""
    _ensure_registry()
    try:
        data = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def register(directory: str, goal: str = "") -> None:
    """Register or update a workspace in the global registry."""
    _ensure_registry()
    workspaces = get_all()
    abs_path = str(Path(directory).resolve())
    now = datetime.now().isoformat(timespec="seconds")

    # Check if already registered
    for ws in workspaces:
        if ws.get("path") == abs_path:
            ws["last_used"] = now
            if goal:
                ws["last_goal"] = goal
            _save(workspaces)
            return

    # New entry
    workspaces.append({
        "path": abs_path,
        "created": now,
        "last_used": now,
        "last_goal": goal,
    })
    _save(workspaces)


def get_by_index(index: int) -> dict | None:
    """Get a workspace by its 1-based index."""
    workspaces = get_all()
    if 1 <= index <= len(workspaces):
        return workspaces[index - 1]
    return None


def update_last_used(directory: str, goal: str = "") -> None:
    """Update the last_used timestamp for a workspace."""
    register(directory, goal)


def remove(index: int) -> bool:
    """Remove a workspace from the registry by 1-based index."""
    workspaces = get_all()
    if 1 <= index <= len(workspaces):
        workspaces.pop(index - 1)
        _save(workspaces)
        return True
    return False


def _save(workspaces: list[dict]) -> None:
    _ensure_registry()
    REGISTRY_FILE.write_text(
        json.dumps(workspaces, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
