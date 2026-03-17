"""
adelie/skill_manager.py

Skills system — loads behavior protocols from .adelie/skills/*/SKILL.md.
Each skill defines agent-specific instructions that are dynamically injected
into agent prompts when applicable.

Format:
  .adelie/skills/<skill-name>/SKILL.md:
    ---
    name: react-specialist
    description: React/TypeScript best practices
    agents: [coder, reviewer]
    trigger: auto
    ---
    # React Development Rules
    - Use functional components
    - ...

Inspired by gemini-cli's .gemini/skills/ system.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from adelie.config import PROJECT_ROOT


@dataclass
class Skill:
    """A loaded skill."""
    name: str
    description: str
    agents: list[str]      # which agents this applies to
    trigger: str            # "auto" or "manual"
    content: str            # the instruction body
    path: str               # file path
    active: bool = True     # whether currently active


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


def _parse_skill_frontmatter(content: str) -> tuple[dict, str]:
    """Parse YAML-like frontmatter from a SKILL.md file."""
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
            value = value.strip()

            # Parse list values like [coder, reviewer]
            if value.startswith("[") and value.endswith("]"):
                items = [item.strip().strip("'\"") for item in value[1:-1].split(",")]
                metadata[key.strip()] = [i for i in items if i]
            else:
                metadata[key.strip()] = value

    return metadata, body


def load_skills() -> list[Skill]:
    """
    Load all skills from .adelie/skills/*/SKILL.md.

    Returns:
        List of Skill objects.
    """
    adelie_dir = _find_adelie_dir()
    if not adelie_dir:
        return []

    skills_dir = adelie_dir / "skills"
    if not skills_dir.exists():
        return []

    skills = []
    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue

        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            continue

        try:
            content = skill_file.read_text(encoding="utf-8").strip()
            if not content:
                continue

            metadata, body = _parse_skill_frontmatter(content)
            name = metadata.get("name", skill_dir.name)
            description = metadata.get("description", "")
            agents = metadata.get("agents", [])
            trigger = metadata.get("trigger", "auto")

            if isinstance(agents, str):
                agents = [agents]

            skills.append(Skill(
                name=name,
                description=description,
                agents=agents,
                trigger=trigger,
                content=body.strip(),
                path=str(skill_file),
                active=(trigger == "auto"),
            ))
        except Exception:
            continue

    return skills


def get_skills_for_agent(agent_name: str) -> list[Skill]:
    """
    Get all active skills applicable to a specific agent.

    Args:
        agent_name: Agent identifier (e.g. "coder", "reviewer", "expert")

    Returns:
        List of active Skill objects for this agent.
    """
    agent_lower = agent_name.lower()
    return [
        skill for skill in load_skills()
        if skill.active and (not skill.agents or agent_lower in [a.lower() for a in skill.agents])
    ]


def get_skills_prompt_section(agent_name: str) -> str:
    """
    Get skills formatted as a prompt section for the given agent.

    Args:
        agent_name: Agent identifier

    Returns:
        Formatted skills text, or empty string if no skills.
    """
    skills = get_skills_for_agent(agent_name)
    if not skills:
        return ""

    parts = ["\n## Active Skills"]
    for skill in skills:
        parts.append(f"\n### Skill: {skill.name}")
        if skill.description:
            parts.append(f"_{skill.description}_")
        parts.append(skill.content)

    return "\n".join(parts) + "\n"
