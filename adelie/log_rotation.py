"""
adelie/log_rotation.py

Manages log file rotation across all agents.
Keeps only the most recent N log files per agent directory,
cleaning up old files to prevent disk bloat.
"""

from __future__ import annotations

from pathlib import Path

from rich.console import Console

from adelie.config import ADELIE_ROOT

console = Console()

# Max log files to keep per directory
MAX_LOGS_PER_DIR = 10

# Agent log directories (relative to .adelie/)
LOG_DIRS = [
    "runner",
    "reviews",
    "tests/results",
    "monitor",
    "monitor/alerts",
    "analysis",
]


def rotate_logs(max_per_dir: int = MAX_LOGS_PER_DIR) -> int:
    """
    Clean up old log files across all agent directories.
    Keeps the most recent `max_per_dir` files in each directory.

    Returns:
        Total number of files removed.
    """
    total_removed = 0

    for rel_dir in LOG_DIRS:
        log_dir = ADELIE_ROOT / rel_dir
        if not log_dir.exists():
            continue

        # Get all .md and .json log files, sorted by modification time (newest first)
        log_files = sorted(
            [f for f in log_dir.glob("*") if f.is_file() and f.suffix in (".md", ".json")],
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )

        # Keep only the newest max_per_dir files
        to_remove = log_files[max_per_dir:]
        for f in to_remove:
            try:
                f.unlink()
                total_removed += 1
            except OSError:
                pass

    if total_removed > 0:
        console.print(f"[dim]🗑️  Log rotation: removed {total_removed} old log file(s)[/dim]")

    return total_removed
