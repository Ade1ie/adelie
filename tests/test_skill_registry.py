"""tests/test_skill_registry.py — Tests for the enhanced SkillRegistry."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


@pytest.fixture
def skills_env(tmp_path):
    """Create an isolated skill registry environment."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    return {"skills_dir": skills_dir, "tmp_path": tmp_path}


def _create_skill_dir(skills_dir: Path, name: str, content: str = "") -> Path:
    """Helper: create a skill directory with SKILL.md."""
    d = skills_dir / name
    d.mkdir(parents=True, exist_ok=True)
    skill_content = content or f"""---
name: {name}
description: Test skill {name}
agents: [coder]
trigger: auto
---
# {name} instructions
Do the thing.
"""
    (d / "SKILL.md").write_text(skill_content, encoding="utf-8")
    return d


class TestSkillManifestEntry:
    def test_create_entry(self):
        from adelie.skill_manager import SkillManifestEntry
        entry = SkillManifestEntry(
            name="test-skill",
            source="https://github.com/user/test-skill",
            version="abc1234",
            installed_at="2024-01-01T00:00:00",
            updated_at="2024-01-01T00:00:00",
        )
        assert entry.name == "test-skill"
        assert entry.source.startswith("https://")


class TestSkillRegistryInit:
    def test_creates_directory(self, skills_env):
        import shutil
        shutil.rmtree(skills_env["skills_dir"])
        from adelie.skill_manager import SkillRegistry
        registry = SkillRegistry(skills_dir=skills_env["skills_dir"])
        assert skills_env["skills_dir"].exists()

    def test_manifest_path(self, skills_env):
        from adelie.skill_manager import SkillRegistry
        registry = SkillRegistry(skills_dir=skills_env["skills_dir"])
        assert registry._manifest_path == skills_env["skills_dir"] / "manifest.json"


class TestSkillRegistryInstallLocal:
    def test_install_from_local_dir(self, skills_env):
        from adelie.skill_manager import SkillRegistry

        # Create a source skill directory
        source_dir = skills_env["tmp_path"] / "source_skill"
        _create_skill_dir(source_dir.parent, source_dir.name)

        with patch("adelie.skill_manager.PROJECT_ROOT", skills_env["tmp_path"]):
            with patch("adelie.skill_manager._find_adelie_dir", return_value=skills_env["tmp_path"]):
                registry = SkillRegistry(skills_dir=skills_env["skills_dir"])
                result = registry.install(str(source_dir), name="my-skill")

        # Check files were copied
        assert (skills_env["skills_dir"] / "my-skill" / "SKILL.md").exists()

        # Check manifest
        manifest = json.loads(registry._manifest_path.read_text())
        assert "my-skill" in manifest
        assert manifest["my-skill"]["source"] == str(source_dir)
        assert manifest["my-skill"]["version"] == "local"

    def test_install_already_exists(self, skills_env):
        from adelie.skill_manager import SkillRegistry
        _create_skill_dir(skills_env["skills_dir"], "existing")
        registry = SkillRegistry(skills_dir=skills_env["skills_dir"])
        result = registry.install(str(skills_env["tmp_path"] / "whatever"), name="existing")
        assert result is None

    def test_install_nonexistent_source(self, skills_env):
        from adelie.skill_manager import SkillRegistry
        registry = SkillRegistry(skills_dir=skills_env["skills_dir"])
        result = registry.install("/does/not/exist", name="bad")
        assert result is None

    def test_install_no_skill_md(self, skills_env):
        from adelie.skill_manager import SkillRegistry
        # Create a source dir without SKILL.md
        source = skills_env["tmp_path"] / "no_skill"
        source.mkdir()
        (source / "readme.txt").write_text("hi")

        registry = SkillRegistry(skills_dir=skills_env["skills_dir"])
        result = registry.install(str(source), name="no-skill-md")

        assert result is None
        assert not (skills_env["skills_dir"] / "no-skill-md").exists()


class TestSkillRegistryUninstall:
    def test_uninstall_existing(self, skills_env):
        from adelie.skill_manager import SkillRegistry
        _create_skill_dir(skills_env["skills_dir"], "removeme")

        registry = SkillRegistry(skills_dir=skills_env["skills_dir"])
        registry._manifest_path.write_text(
            json.dumps({"removeme": {"source": "local", "version": "1.0"}}),
            encoding="utf-8",
        )

        result = registry.uninstall("removeme")
        assert result is True
        assert not (skills_env["skills_dir"] / "removeme").exists()

        manifest = json.loads(registry._manifest_path.read_text())
        assert "removeme" not in manifest

    def test_uninstall_nonexistent(self, skills_env):
        from adelie.skill_manager import SkillRegistry
        registry = SkillRegistry(skills_dir=skills_env["skills_dir"])
        assert registry.uninstall("nope") is False


class TestSkillRegistryList:
    def test_list_empty(self, skills_env):
        from adelie.skill_manager import SkillRegistry
        registry = SkillRegistry(skills_dir=skills_env["skills_dir"])
        assert registry.list_skills() == []

    def test_list_with_skills(self, skills_env):
        from adelie.skill_manager import SkillRegistry
        _create_skill_dir(skills_env["skills_dir"], "alpha")
        _create_skill_dir(skills_env["skills_dir"], "beta")

        registry = SkillRegistry(skills_dir=skills_env["skills_dir"])
        skills = registry.list_skills()

        assert len(skills) == 2
        assert skills[0]["name"] == "alpha"
        assert skills[1]["name"] == "beta"
        assert skills[0]["has_skill_md"] is True

    def test_list_with_manifest(self, skills_env):
        from adelie.skill_manager import SkillRegistry
        _create_skill_dir(skills_env["skills_dir"], "tracked")

        registry = SkillRegistry(skills_dir=skills_env["skills_dir"])
        registry._manifest_path.write_text(json.dumps({
            "tracked": {
                "source": "https://github.com/user/tracked",
                "version": "abc123",
                "installed_at": "2024-01-01",
                "updated_at": "2024-06-01",
            }
        }))

        skills = registry.list_skills()
        assert len(skills) == 1
        assert skills[0]["source"] == "https://github.com/user/tracked"
        assert skills[0]["version"] == "abc123"

    def test_list_skips_underscore_dirs(self, skills_env):
        from adelie.skill_manager import SkillRegistry
        _create_skill_dir(skills_env["skills_dir"], "_internal")
        _create_skill_dir(skills_env["skills_dir"], "visible")

        registry = SkillRegistry(skills_dir=skills_env["skills_dir"])
        skills = registry.list_skills()
        assert len(skills) == 1
        assert skills[0]["name"] == "visible"


class TestSkillRegistryManifest:
    def test_load_empty_manifest(self, skills_env):
        from adelie.skill_manager import SkillRegistry
        registry = SkillRegistry(skills_dir=skills_env["skills_dir"])
        assert registry._load_manifest() == {}

    def test_save_and_load_manifest(self, skills_env):
        from adelie.skill_manager import SkillRegistry, SkillManifestEntry
        registry = SkillRegistry(skills_dir=skills_env["skills_dir"])
        entry = SkillManifestEntry(
            name="test",
            source="local",
            version="1.0",
            installed_at="2024-01-01",
            updated_at="2024-01-01",
        )
        registry._save_manifest_entry(entry)

        manifest = registry._load_manifest()
        assert "test" in manifest
        assert manifest["test"]["version"] == "1.0"

    def test_remove_manifest_entry(self, skills_env):
        from adelie.skill_manager import SkillRegistry
        registry = SkillRegistry(skills_dir=skills_env["skills_dir"])
        registry._manifest_path.write_text(json.dumps({"a": {}, "b": {}}))

        registry._remove_manifest_entry("a")
        manifest = registry._load_manifest()
        assert "a" not in manifest
        assert "b" in manifest

    def test_invalid_manifest_json(self, skills_env):
        from adelie.skill_manager import SkillRegistry
        registry = SkillRegistry(skills_dir=skills_env["skills_dir"])
        registry._manifest_path.write_text("not json")
        assert registry._load_manifest() == {}


class TestSkillRegistryHelpers:
    def test_is_git_url(self):
        from adelie.skill_manager import SkillRegistry
        assert SkillRegistry._is_git_url("https://github.com/user/repo") is True
        assert SkillRegistry._is_git_url("git@github.com:user/repo.git") is True
        assert SkillRegistry._is_git_url("/local/path") is False
        assert SkillRegistry._is_git_url("relative/path") is False

    def test_infer_name(self):
        from adelie.skill_manager import SkillRegistry
        assert SkillRegistry._infer_name("https://github.com/user/my-skill") == "my-skill"
        assert SkillRegistry._infer_name("https://github.com/user/repo.git") == "repo"
        assert SkillRegistry._infer_name("/local/path/skill-name") == "skill-name"
        assert SkillRegistry._infer_name("/local/path/skill-name/") == "skill-name"
