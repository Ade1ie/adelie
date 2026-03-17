"""
adelie/command_loader.py

Loads user-defined custom commands from .adelie/commands/*.md files.
Each file defines a reusable command template with YAML frontmatter.

Format:
  ---
  name: review-code
  description: Review staged changes and fix issues
  ---
  ## Instructions
  Target: {{args}}
  1. Review the code changes
  2. Fix any issues found

Inspired by gemini-cli's .gemini/commands/*.toml system.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from adelie.config import PROJECT_ROOT


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


def _parse_frontmatter(content: str) -> tuple[dict, str]:
    """
    Parse YAML-like frontmatter from a markdown file.

    Returns:
        (metadata_dict, body_text)
    """
    match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)', content, re.DOTALL)
    if not match:
        return {}, content

    frontmatter = match.group(1)
    body = match.group(2)

    metadata = {}
    for line in frontmatter.strip().split("\n"):
        line = line.strip()
        if ":" in line:
            key, value = line.split(":", 1)
            metadata[key.strip()] = value.strip()

    return metadata, body


class Command:
    """A loaded custom command."""

    def __init__(self, name: str, description: str, template: str, path: str):
        self.name = name
        self.description = description
        self.template = template
        self.path = path

    def render(self, args: str = "") -> str:
        """Render the command template with arguments."""
        return self.template.replace("{{args}}", args)


def load_commands() -> list[Command]:
    """
    Load all custom commands from .adelie/commands/*.md.

    Returns:
        List of Command objects.
    """
    adelie_dir = _find_adelie_dir()
    if not adelie_dir:
        return []

    commands_dir = adelie_dir / "commands"
    if not commands_dir.exists():
        return []

    commands = []
    for f in sorted(commands_dir.glob("*.md")):
        try:
            content = f.read_text(encoding="utf-8").strip()
            if not content:
                continue

            metadata, body = _parse_frontmatter(content)
            name = metadata.get("name", f.stem)
            description = metadata.get("description", "")

            commands.append(Command(
                name=name,
                description=description,
                template=body.strip(),
                path=str(f),
            ))
        except Exception:
            continue

    return commands


def get_command(name: str) -> Optional[Command]:
    """
    Get a specific custom command by name.

    Args:
        name: Command name (without leading /)

    Returns:
        Command object or None.
    """
    for cmd in load_commands():
        if cmd.name == name:
            return cmd
    return None


def list_command_names() -> list[str]:
    """Get list of available custom command names."""
    return [cmd.name for cmd in load_commands()]
