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


# ── Skill Registry ───────────────────────────────────────────────────────────


@dataclass
class SkillManifestEntry:
    """A registry entry for an installed skill."""
    name: str
    source: str             # "local", git URL, or directory path
    version: str            # e.g. "1.0.0" or commit hash
    installed_at: str       # ISO timestamp
    updated_at: str         # ISO timestamp


class SkillRegistry:
    """
    Manages skill installation, updates, and lifecycle.

    Skills can be installed from:
      - Git repositories:  adelie skill install https://github.com/user/skill
      - Local directories: adelie skill install /path/to/skill

    Installed skills live in .adelie/skills/<name>/.
    Manifest stored in .adelie/skills/manifest.json.

    Inspired by OpenClaw's skills-install.ts / skills-status.ts.
    """

    def __init__(self, skills_dir: Optional[Path] = None):
        self._dir = skills_dir or self._resolve_skills_dir()
        self._dir.mkdir(parents=True, exist_ok=True)
        self._manifest_path = self._dir / "manifest.json"

    @staticmethod
    def _resolve_skills_dir() -> Path:
        adelie_dir = _find_adelie_dir()
        if adelie_dir:
            return adelie_dir / "skills"
        return PROJECT_ROOT / ".adelie" / "skills"

    # ── Install ──────────────────────────────────────────────────────────

    def install(self, source: str, name: str = "") -> Optional[Skill]:
        """
        Install a skill from a Git URL or local path.

        Args:
            source: Git URL (https://...) or local directory path.
            name:   Override skill name (default: inferred from source).

        Returns:
            Installed Skill object, or None on failure.
        """
        import shutil
        import subprocess as _sp
        from datetime import datetime

        inferred_name = name or self._infer_name(source)
        target = self._dir / inferred_name

        if target.exists():
            return None  # Already installed — use update instead

        try:
            if self._is_git_url(source):
                _sp.run(
                    ["git", "clone", "--depth", "1", source, str(target)],
                    capture_output=True, text=True, timeout=60,
                    check=True,
                )
            else:
                src_path = Path(source)
                if src_path.is_dir():
                    shutil.copytree(src_path, target)
                else:
                    return None
        except Exception:
            if target.exists():
                shutil.rmtree(target)
            return None

        # Verify SKILL.md exists
        if not (target / "SKILL.md").exists():
            shutil.rmtree(target)
            return None

        # Update manifest
        now = datetime.now().isoformat(timespec="seconds")
        version = self._get_git_version(target) if self._is_git_url(source) else "local"
        entry = SkillManifestEntry(
            name=inferred_name,
            source=source,
            version=version,
            installed_at=now,
            updated_at=now,
        )
        self._save_manifest_entry(entry)

        # Load and return the skill
        skills = load_skills()
        return next((s for s in skills if s.name == inferred_name), None)

    # ── Uninstall ────────────────────────────────────────────────────────

    def uninstall(self, name: str) -> bool:
        """Remove an installed skill."""
        import shutil
        target = self._dir / name
        if not target.exists():
            return False

        shutil.rmtree(target)
        self._remove_manifest_entry(name)
        return True

    # ── Update ───────────────────────────────────────────────────────────

    def update(self, name: str = "") -> dict[str, bool]:
        """
        Update skill(s) from their original source.

        Args:
            name: Specific skill to update, or "" for all.

        Returns:
            Dict of {skill_name: success}.
        """
        import subprocess as _sp
        from datetime import datetime

        manifest = self._load_manifest()
        targets = {name: manifest[name]} if name and name in manifest else manifest
        results = {}

        for skill_name, entry_data in targets.items():
            source = entry_data.get("source", "")
            target = self._dir / skill_name

            if not target.exists() or not self._is_git_url(source):
                results[skill_name] = False
                continue

            try:
                _sp.run(
                    ["git", "-C", str(target), "pull", "--ff-only"],
                    capture_output=True, text=True, timeout=60,
                    check=True,
                )
                # Update manifest timestamp + version
                now = datetime.now().isoformat(timespec="seconds")
                entry_data["updated_at"] = now
                entry_data["version"] = self._get_git_version(target)
                self._save_manifest_raw(manifest)
                results[skill_name] = True
            except Exception:
                results[skill_name] = False

        return results

    # ── List ─────────────────────────────────────────────────────────────

    def list_skills(self) -> list[dict]:
        """
        List all installed skills with metadata.

        Returns:
            List of dicts: {name, source, version, installed_at, updated_at, has_skill_md}.
        """
        manifest = self._load_manifest()
        result = []

        for skill_dir in sorted(self._dir.iterdir()):
            if not skill_dir.is_dir() or skill_dir.name.startswith("_"):
                continue

            entry = manifest.get(skill_dir.name, {})
            result.append({
                "name": skill_dir.name,
                "source": entry.get("source", "local"),
                "version": entry.get("version", "unknown"),
                "installed_at": entry.get("installed_at", ""),
                "updated_at": entry.get("updated_at", ""),
                "has_skill_md": (skill_dir / "SKILL.md").exists(),
            })

        return result

    # ── Manifest ─────────────────────────────────────────────────────────

    def _load_manifest(self) -> dict:
        import json
        if not self._manifest_path.exists():
            return {}
        try:
            return json.loads(self._manifest_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_manifest_raw(self, data: dict) -> None:
        import json
        self._manifest_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _save_manifest_entry(self, entry: SkillManifestEntry) -> None:
        manifest = self._load_manifest()
        manifest[entry.name] = {
            "source": entry.source,
            "version": entry.version,
            "installed_at": entry.installed_at,
            "updated_at": entry.updated_at,
        }
        self._save_manifest_raw(manifest)

    def _remove_manifest_entry(self, name: str) -> None:
        manifest = self._load_manifest()
        manifest.pop(name, None)
        self._save_manifest_raw(manifest)

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _is_git_url(source: str) -> bool:
        return source.startswith("https://") or source.startswith("git@")

    @staticmethod
    def _infer_name(source: str) -> str:
        """Infer skill name from source URL or path."""
        clean = source.rstrip("/").rstrip(".git")
        return clean.split("/")[-1]

    @staticmethod
    def _get_git_version(repo_path: Path) -> str:
        """Get short git hash of HEAD."""
        import subprocess as _sp
        try:
            result = _sp.run(
                ["git", "-C", str(repo_path), "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, timeout=10,
            )
            return result.stdout.strip() if result.returncode == 0 else "unknown"
        except Exception:
            return "unknown"

