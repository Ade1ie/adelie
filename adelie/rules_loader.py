"""
adelie/rules_loader.py

Loads project-specific rules from .adelie/rules.md.
Rules are injected into agent prompts (Coder, Reviewer, Expert)
to enforce project-specific coding standards.

Inspired by gemini-cli's strict-development-rules.md approach.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from adelie.config import PROJECT_ROOT


def _find_adelie_dir() -> Optional[Path]:
    """Find the .adelie directory from PROJECT_ROOT upwards."""
    current = PROJECT_ROOT
    for _ in range(5):  # max 5 levels up
        adelie_dir = current / ".adelie"
        if adelie_dir.is_dir():
            return adelie_dir
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def load_rules() -> str:
    """
    Load project rules from .adelie/rules.md.

    Returns:
        Rules content as string, or empty string if no rules file exists.
    """
    adelie_dir = _find_adelie_dir()
    if not adelie_dir:
        return ""

    rules_path = adelie_dir / "rules.md"
    if not rules_path.exists():
        return ""

    try:
        content = rules_path.read_text(encoding="utf-8").strip()
        if not content:
            return ""
        return content
    except Exception:
        return ""


def get_rules_prompt_section() -> str:
    """
    Get rules formatted as a prompt section.
    Returns empty string if no rules, otherwise wraps in a header.
    """
    rules = load_rules()
    if not rules:
        return ""

    return (
        "\n## Project Rules (from .adelie/rules.md)\n"
        "The following project-specific rules MUST be followed:\n\n"
        f"{rules}\n"
    )


# ── Context File (.adelie/context.md) ─────────────────────────────────────────

def load_context() -> str:
    """
    Load project context from .adelie/context.md.
    This is a persistent file with project info injected into ALL agent prompts.

    Returns:
        Context content as string, or empty string if no context file exists.
    """
    adelie_dir = _find_adelie_dir()
    if not adelie_dir:
        return ""

    context_path = adelie_dir / "context.md"
    if not context_path.exists():
        return ""

    try:
        content = context_path.read_text(encoding="utf-8").strip()
        if not content:
            return ""
        return content
    except Exception:
        return ""


def get_context_prompt_section() -> str:
    """
    Get context formatted as a prompt section.
    Returns empty string if no context, otherwise wraps in a header.
    """
    context = load_context()
    if not context:
        return ""

    return (
        "\n## Project Context (from .adelie/context.md)\n"
        f"{context}\n"
    )
