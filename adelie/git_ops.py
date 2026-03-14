"""
adelie/git_ops.py

Git integration utilities for the Adelie orchestrator.
Provides auto-commit/push functionality after code is promoted.
"""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from rich.console import Console

from adelie.config import PROJECT_ROOT

console = Console()

GIT_TIMEOUT = 30  # seconds


def is_git_repo(root: Path | None = None) -> bool:
    """Check if the project root is a Git repository."""
    root = root or PROJECT_ROOT
    return (root / ".git").is_dir()


def get_status(root: Path | None = None) -> dict:
    """Get git status summary."""
    root = root or PROJECT_ROOT
    result = _run_git(["git", "status", "--porcelain"], cwd=root)
    if result["returncode"] != 0:
        return {"ok": False, "error": result["stderr"]}

    lines = result["stdout"].strip().splitlines() if result["stdout"].strip() else []
    return {
        "ok": True,
        "changed_files": len(lines),
        "files": [line.strip() for line in lines[:20]],  # Cap display
    }


def auto_commit(
    message: str,
    files: list[str] | None = None,
    root: Path | None = None,
) -> dict:
    """
    Auto-commit changed files.

    Args:
        message: Commit message
        files: Specific files to stage (None = stage all changes)
        root: Project root

    Returns:
        Result dict with success status.
    """
    root = root or PROJECT_ROOT

    if not is_git_repo(root):
        return {"ok": False, "error": "Not a git repository"}

    # Stage files
    if files:
        for f in files:
            result = _run_git(["git", "add", f], cwd=root)
            if result["returncode"] != 0:
                console.print(f"[dim]⚠️ git add failed for {f}: {result['stderr'][:100]}[/dim]")
    else:
        result = _run_git(["git", "add", "-A"], cwd=root)
        if result["returncode"] != 0:
            return {"ok": False, "error": result["stderr"]}

    # Check if there's anything to commit
    status = _run_git(["git", "diff", "--cached", "--name-only"], cwd=root)
    staged = status["stdout"].strip()
    if not staged:
        console.print("[dim]📎 git: nothing to commit[/dim]")
        return {"ok": True, "committed": False, "message": "Nothing to commit"}

    staged_count = len(staged.splitlines())

    # Commit
    result = _run_git(["git", "commit", "-m", message], cwd=root)
    if result["returncode"] != 0:
        return {"ok": False, "error": result["stderr"]}

    console.print(
        f"[green]📦 git commit[/green] — {staged_count} file(s): {message[:60]}"
    )
    return {"ok": True, "committed": True, "files_count": staged_count, "message": message}


def auto_push(remote: str = "origin", branch: str | None = None, root: Path | None = None) -> dict:
    """
    Push to remote. Only called in late/evolve phases.

    Args:
        remote: Remote name (default: origin)
        branch: Branch to push (None = current branch)
        root: Project root

    Returns:
        Result dict.
    """
    root = root or PROJECT_ROOT

    if not is_git_repo(root):
        return {"ok": False, "error": "Not a git repository"}

    # Get current branch if not specified
    if not branch:
        result = _run_git(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=root)
        if result["returncode"] != 0:
            return {"ok": False, "error": "Could not determine current branch"}
        branch = result["stdout"].strip()

    # Check if remote exists
    result = _run_git(["git", "remote"], cwd=root)
    if remote not in result["stdout"].split():
        return {"ok": False, "error": f"Remote '{remote}' not found"}

    result = _run_git(["git", "push", remote, branch], cwd=root, timeout=60)
    if result["returncode"] != 0:
        console.print(f"[yellow]⚠️ git push failed: {result['stderr'][:100]}[/yellow]")
        return {"ok": False, "error": result["stderr"]}

    console.print(f"[green]🚀 git push[/green] → {remote}/{branch}")
    return {"ok": True, "remote": remote, "branch": branch}


def get_log(n: int = 5, root: Path | None = None) -> list[dict]:
    """Get recent git log entries."""
    root = root or PROJECT_ROOT
    result = _run_git(
        ["git", "log", f"-{n}", "--pretty=format:%H|%s|%ai"],
        cwd=root,
    )
    if result["returncode"] != 0:
        return []

    entries = []
    for line in result["stdout"].strip().splitlines():
        parts = line.split("|", 2)
        if len(parts) == 3:
            entries.append({"hash": parts[0][:8], "message": parts[1], "date": parts[2]})
    return entries


def _run_git(cmd: list[str], cwd: Path, timeout: int = GIT_TIMEOUT) -> dict:
    """Execute a git command safely."""
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
    except subprocess.TimeoutExpired:
        return {"returncode": -1, "stdout": "", "stderr": f"Timed out after {timeout}s"}
    except Exception as e:
        return {"returncode": -1, "stdout": "", "stderr": str(e)}
