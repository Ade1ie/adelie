"""
adelie/prompt_loader.py

Loads agent system prompts with a cascading override system:
  1. .adelie/prompts/{agent_name}.md  (user override — highest priority)
  2. adelie/prompts/{agent_name}.md   (package defaults)
  3. Hardcoded fallback string

Also composes the final prompt by injecting:
  - Project rules (.adelie/rules.md)
  - Project context (.adelie/context.md)  [Phase 5]
  - Active skills                         [Phase 4]

Inspired by gemini-cli's promptProvider.ts system.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

from adelie.config import PROJECT_ROOT


# Package-level prompts directory (inside the adelie package)
_PACKAGE_PROMPTS_DIR = Path(__file__).parent / "prompts"


def _find_adelie_dir() -> Optional[Path]:
    """Find the .adelie directory from PROJECT_ROOT upwards."""
    current = PROJECT_ROOT
    for _ in range(5):
        adelie_dir = current / ".adelie"
        if adelie_dir.is_dir():
            return adelie_dir
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def load_prompt(agent_name: str, fallback: str) -> str:
    """
    Load a system prompt for the given agent.

    Search order:
      1. .adelie/prompts/{agent_name}.md   (user override)
      2. adelie/prompts/{agent_name}.md    (package default)
      3. fallback string                   (hardcoded)

    Args:
        agent_name: Agent identifier (e.g. "expert", "coder", "reviewer")
        fallback: Hardcoded fallback prompt string

    Returns:
        The prompt content string.
    """
    # 1. User override
    adelie_dir = _find_adelie_dir()
    if adelie_dir:
        user_prompt_path = adelie_dir / "prompts" / f"{agent_name}.md"
        if user_prompt_path.exists():
            try:
                content = user_prompt_path.read_text(encoding="utf-8").strip()
                if content:
                    return content
            except Exception:
                pass

    # 2. Package default
    pkg_prompt_path = _PACKAGE_PROMPTS_DIR / f"{agent_name}.md"
    if pkg_prompt_path.exists():
        try:
            content = pkg_prompt_path.read_text(encoding="utf-8").strip()
            if content:
                return content
        except Exception:
            pass

    # 3. Hardcoded fallback
    return fallback


def list_prompts() -> list[dict]:
    """
    List all available prompts and their sources.

    Returns:
        List of dicts: {"agent": name, "source": "user"|"package"|"fallback", "path": str}
    """
    results = []
    adelie_dir = _find_adelie_dir()

    # Scan package defaults
    if _PACKAGE_PROMPTS_DIR.exists():
        for f in sorted(_PACKAGE_PROMPTS_DIR.glob("*.md")):
            agent_name = f.stem
            source = "package"
            path = str(f)

            # Check if user override exists
            if adelie_dir:
                user_path = adelie_dir / "prompts" / f.name
                if user_path.exists():
                    source = "user"
                    path = str(user_path)

            results.append({"agent": agent_name, "source": source, "path": path})

    # Check for user overrides that don't have package defaults
    if adelie_dir:
        user_prompts_dir = adelie_dir / "prompts"
        if user_prompts_dir.exists():
            pkg_names = {f.stem for f in _PACKAGE_PROMPTS_DIR.glob("*.md")} if _PACKAGE_PROMPTS_DIR.exists() else set()
            for f in sorted(user_prompts_dir.glob("*.md")):
                if f.stem not in pkg_names:
                    results.append({"agent": f.stem, "source": "user", "path": str(f)})

    return results


def export_prompts() -> list[str]:
    """
    Export package default prompts to .adelie/prompts/ for user customization.

    Returns:
        List of exported file paths.
    """
    adelie_dir = _find_adelie_dir()
    if not adelie_dir:
        return []

    user_prompts_dir = adelie_dir / "prompts"
    user_prompts_dir.mkdir(parents=True, exist_ok=True)

    exported = []
    if _PACKAGE_PROMPTS_DIR.exists():
        for src in _PACKAGE_PROMPTS_DIR.glob("*.md"):
            dst = user_prompts_dir / src.name
            if not dst.exists():  # Don't overwrite existing user customizations
                shutil.copy2(src, dst)
                exported.append(str(dst))

    return exported


def reset_prompts() -> list[str]:
    """
    Remove user-customized prompts (restoring package defaults).

    Returns:
        List of removed file paths.
    """
    adelie_dir = _find_adelie_dir()
    if not adelie_dir:
        return []

    user_prompts_dir = adelie_dir / "prompts"
    if not user_prompts_dir.exists():
        return []

    removed = []
    for f in user_prompts_dir.glob("*.md"):
        f.unlink()
        removed.append(str(f))

    # Remove the directory if empty
    try:
        user_prompts_dir.rmdir()
    except OSError:
        pass

    return removed
