"""
adelie/project_context.py

Collects real project file tree and source code metadata
to inject as context into all AI agents.

Provides:
  - File tree snapshot (with size, last modified)
  - Source code statistics
  - Key config file detection
"""

from __future__ import annotations

import os
import platform
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

from adelie.config import PROJECT_ROOT, ADELIE_ROOT

# Extensions grouped by role
CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs",
    ".svelte", ".vue", ".html", ".css", ".scss",
    ".sql", ".sh", ".bash",
}

CONFIG_EXTENSIONS = {
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".env",
}

DOC_EXTENSIONS = {
    ".md", ".txt", ".rst",
}

SKIP_DIRS = {
    ".adelie", ".git", "node_modules", "__pycache__", ".venv",
    "venv", ".next", "dist", "build", ".cache", ".pytest_cache",
    "coverage", ".nyc_output", "target", ".tox",
}

MAX_TREE_FILES = 200  # Cap to avoid overloading context


class FileInfo(NamedTuple):
    path: str          # relative to project root
    size: int          # bytes
    modified: str      # ISO timestamp
    extension: str     # e.g. ".py"


def _should_skip(path: Path) -> bool:
    """Check if path should be excluded."""
    parts = path.relative_to(PROJECT_ROOT).parts
    return any(p in SKIP_DIRS or p.startswith(".") for p in parts)


def collect_file_tree() -> list[FileInfo]:
    """
    Collect all relevant files in the project.
    Returns list of FileInfo sorted by path.
    """
    files: list[FileInfo] = []

    if not PROJECT_ROOT.exists():
        return files

    all_exts = CODE_EXTENSIONS | CONFIG_EXTENSIONS | DOC_EXTENSIONS

    for f in PROJECT_ROOT.rglob("*"):
        if not f.is_file():
            continue
        if _should_skip(f):
            continue
        if f.suffix not in all_exts:
            continue

        try:
            stat = f.stat()
            rel = f.relative_to(PROJECT_ROOT).as_posix()
            files.append(FileInfo(
                path=rel,
                size=stat.st_size,
                modified=datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                extension=f.suffix,
            ))
        except (OSError, ValueError):
            continue

    # Sort by path, cap at limit
    files.sort(key=lambda f: f.path)
    return files[:MAX_TREE_FILES]


def get_tree_summary() -> str:
    """
    Get a compact file tree string for agent context.
    Format:
      src/
        main.py          (2.1KB, 2024-01-15)
        utils/
          helpers.py      (800B, 2024-01-15)
      package.json        (1.2KB, 2024-01-15)
    """
    files = collect_file_tree()
    if not files:
        return "(empty project — no source files found)"

    # Build tree structure
    lines: list[str] = []
    seen_dirs: set[str] = set()

    for fi in files:
        parts = fi.path.split("/")

        # Show directory prefixes we haven't shown yet
        for i in range(len(parts) - 1):
            dir_path = "/".join(parts[:i + 1])
            if dir_path not in seen_dirs:
                seen_dirs.add(dir_path)
                indent = "  " * i
                lines.append(f"{indent}{parts[i]}/")

        # Show file
        indent = "  " * (len(parts) - 1)
        size_str = _format_size(fi.size)
        lines.append(f"{indent}{parts[-1]}  ({size_str})")

    # Stats
    code_count = sum(1 for f in files if f.extension in CODE_EXTENSIONS)
    config_count = sum(1 for f in files if f.extension in CONFIG_EXTENSIONS)
    total_size = sum(f.size for f in files)

    header = (
        f"📁 Project: {PROJECT_ROOT.name} | "
        f"{len(files)} files ({code_count} code, {config_count} config) | "
        f"{_format_size(total_size)} total | "
        f"{get_os_info()}\n"
    )

    truncated = ""
    if len(files) >= MAX_TREE_FILES:
        truncated = f"\n(truncated at {MAX_TREE_FILES} files)"

    return header + "\n".join(lines) + truncated


def get_source_stats() -> dict:
    """
    Get source code statistics for metrics.
    """
    files = collect_file_tree()
    code_files = [f for f in files if f.extension in CODE_EXTENSIONS]
    config_files = [f for f in files if f.extension in CONFIG_EXTENSIONS]

    return {
        "total_files": len(files),
        "code_files": len(code_files),
        "config_files": len(config_files),
        "total_bytes": sum(f.size for f in files),
        "code_bytes": sum(f.size for f in code_files),
        "languages": list(set(f.extension for f in code_files)),
    }


def get_key_configs() -> str:
    """
    Read key configuration files content for context.
    """
    config_files = [
        "package.json", "requirements.txt", "pyproject.toml",
        "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
        "Makefile", "tsconfig.json", "vite.config.ts", "vite.config.js",
        "next.config.js", "next.config.mjs",
    ]

    parts: list[str] = []
    for name in config_files:
        fp = PROJECT_ROOT / name
        if fp.exists():
            try:
                content = fp.read_text(encoding="utf-8")[:800]  # Cap
                parts.append(f"--- {name} ---\n{content}")
            except Exception:
                pass

    return "\n\n".join(parts) if parts else "(no config files found)"


def _format_size(size: int) -> str:
    if size < 1024:
        return f"{size}B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f}KB"
    else:
        return f"{size / (1024 * 1024):.1f}MB"


def get_os_info() -> str:
    """Return a one-line OS summary string for context injection."""
    system = platform.system()
    machine = platform.machine()
    if system == "Darwin":
        os_name = "macOS"
        try:
            ver = platform.mac_ver()[0]
            if ver:
                os_name = f"macOS {ver}"
        except Exception:
            pass
    elif system == "Windows":
        os_name = f"Windows {platform.release()}"
    else:
        os_name = f"Linux {platform.release()}"
    return f"OS: {os_name} / {machine}"
