"""tests/test_env_strategy.py — Tests for Environment Strategy module."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def empty_project(tmp_path):
    """Project with no environment markers."""
    return tmp_path


@pytest.fixture
def venv_project(tmp_path):
    """Project with a Python venv."""
    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "python").write_text("#!/usr/bin/env python3", encoding="utf-8")
    (venv_bin / "pip").write_text("#!/usr/bin/env pip", encoding="utf-8")
    (venv_bin / "activate").write_text("# activation script", encoding="utf-8")
    return tmp_path


@pytest.fixture
def npm_project(tmp_path):
    """Project with node_modules."""
    bin_dir = tmp_path / "node_modules" / ".bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "node").write_text("#!/usr/bin/env node", encoding="utf-8")
    (bin_dir / "eslint").write_text("#!/usr/bin/env eslint", encoding="utf-8")
    (tmp_path / "package.json").write_text('{"name": "test"}', encoding="utf-8")
    return tmp_path


@pytest.fixture
def docker_project(tmp_path):
    """Project with Dockerfile."""
    (tmp_path / "Dockerfile").write_text("FROM python:3.12\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def full_project(tmp_path):
    """Project with venv + npm + Docker."""
    # venv
    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "python").write_text("#!/usr/bin/env python3", encoding="utf-8")
    (venv_bin / "pip").write_text("#!/usr/bin/env pip", encoding="utf-8")
    (venv_bin / "activate").write_text("# activation script", encoding="utf-8")
    # npm
    bin_dir = tmp_path / "node_modules" / ".bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "node").write_text("#!/usr/bin/env node", encoding="utf-8")
    # Docker
    (tmp_path / "Dockerfile").write_text("FROM python:3.12\n", encoding="utf-8")
    (tmp_path / "docker-compose.yml").write_text("version: '3'\n", encoding="utf-8")
    return tmp_path


# ── Detection Tests ──────────────────────────────────────────────────────────


class TestDetectEnv:
    def test_empty_project_returns_system(self, empty_project):
        from adelie.env_strategy import detect_env
        profile = detect_env(empty_project)
        assert profile.env_type == "system"
        assert profile.python_bin is None
        assert profile.detected_envs == []

    def test_detects_venv(self, venv_project):
        from adelie.env_strategy import detect_env
        profile = detect_env(venv_project)
        assert profile.env_type == "venv"
        assert "venv" in profile.detected_envs
        assert profile.python_bin is not None
        assert ".venv/bin/python" in profile.python_bin
        assert profile.pip_bin is not None
        assert profile.shell_wrapper is not None
        assert "activate" in profile.shell_wrapper

    def test_detects_npm(self, npm_project):
        from adelie.env_strategy import detect_env
        profile = detect_env(npm_project)
        assert "npm" in profile.detected_envs
        assert profile.npm_prefix is not None
        assert "node_modules/.bin/" in profile.npm_prefix

    def test_detects_docker(self, docker_project):
        from adelie.env_strategy import detect_env
        profile = detect_env(docker_project)
        assert "docker" in profile.detected_envs
        assert profile.docker_image is not None

    def test_detects_multiple_envs(self, full_project):
        from adelie.env_strategy import detect_env
        profile = detect_env(full_project)
        assert "venv" in profile.detected_envs
        assert "npm" in profile.detected_envs
        assert "docker" in profile.detected_envs
        assert "docker-compose" in profile.detected_envs

    def test_detects_pipenv(self, tmp_path):
        (tmp_path / "Pipfile").write_text("[packages]\nflask = '*'\n", encoding="utf-8")
        from adelie.env_strategy import detect_env
        profile = detect_env(tmp_path)
        assert profile.env_type == "pipenv"
        assert "pipenv" in profile.detected_envs

    def test_detects_poetry(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            '[tool.poetry]\nname = "test"\n', encoding="utf-8"
        )
        from adelie.env_strategy import detect_env
        profile = detect_env(tmp_path)
        assert profile.env_type == "poetry"
        assert "poetry" in profile.detected_envs


# ── Strategy Selection Tests ─────────────────────────────────────────────────


class TestSelectStrategy:
    def test_initial_always_direct(self, venv_project):
        from adelie.env_strategy import detect_env, select_strategy, EnvStrategy
        profile = detect_env(venv_project)
        assert select_strategy(profile, "initial") == EnvStrategy.DIRECT

    def test_mid_always_direct(self, venv_project):
        from adelie.env_strategy import detect_env, select_strategy, EnvStrategy
        profile = detect_env(venv_project)
        assert select_strategy(profile, "mid") == EnvStrategy.DIRECT

    def test_mid_1_direct_with_resolver_fallback(self, venv_project):
        from adelie.env_strategy import detect_env, select_strategy, EnvStrategy
        profile = detect_env(venv_project)
        # mid_1 prefers direct first
        assert select_strategy(profile, "mid_1") == EnvStrategy.DIRECT

    def test_mid_2_prefers_resolver(self, venv_project):
        from adelie.env_strategy import detect_env, select_strategy, EnvStrategy
        profile = detect_env(venv_project)
        # mid_2 prefers resolver
        assert select_strategy(profile, "mid_2") == EnvStrategy.RESOLVER

    def test_mid_2_falls_to_resolver_without_docker(self, venv_project):
        from adelie.env_strategy import detect_env, select_strategy, EnvStrategy
        profile = detect_env(venv_project)
        # No Docker → resolver (first feasible in [resolver, docker])
        assert select_strategy(profile, "mid_2") == EnvStrategy.RESOLVER

    @patch("shutil.which", return_value="/usr/bin/docker")
    def test_late_prefers_docker_when_available(self, mock_which, full_project):
        from adelie.env_strategy import detect_env, select_strategy, EnvStrategy
        profile = detect_env(full_project)
        result = select_strategy(profile, "late")
        assert result == EnvStrategy.DOCKER

    def test_late_falls_back_without_docker(self, venv_project):
        from adelie.env_strategy import detect_env, select_strategy, EnvStrategy
        profile = detect_env(venv_project)
        # No Docker available → falls back to resolver
        result = select_strategy(profile, "late")
        assert result in (EnvStrategy.RESOLVER, EnvStrategy.DIRECT)

    def test_system_env_always_direct(self, empty_project):
        from adelie.env_strategy import detect_env, select_strategy, EnvStrategy
        profile = detect_env(empty_project)
        # System env can't use resolver or docker
        for phase in ("initial", "mid", "mid_1", "mid_2", "late", "evolve"):
            assert select_strategy(profile, phase) == EnvStrategy.DIRECT


# ── Command Wrapping Tests ───────────────────────────────────────────────────


class TestWrapCommand:
    def test_direct_replaces_python_binary(self, venv_project):
        from adelie.env_strategy import detect_env, wrap_command, EnvStrategy
        profile = detect_env(venv_project)
        result = wrap_command("python test.py", profile, EnvStrategy.DIRECT)
        assert ".venv/bin/python" in result
        assert "test.py" in result

    def test_direct_replaces_pip_binary(self, venv_project):
        from adelie.env_strategy import detect_env, wrap_command, EnvStrategy
        profile = detect_env(venv_project)
        result = wrap_command("pip install flask", profile, EnvStrategy.DIRECT)
        assert ".venv/bin/pip" in result
        assert "install flask" in result

    def test_direct_leaves_unknown_commands(self, venv_project):
        from adelie.env_strategy import detect_env, wrap_command, EnvStrategy
        profile = detect_env(venv_project)
        result = wrap_command("make build", profile, EnvStrategy.DIRECT)
        assert result == "make build"

    def test_direct_replaces_node_binary(self, npm_project):
        from adelie.env_strategy import detect_env, wrap_command, EnvStrategy
        profile = detect_env(npm_project)
        result = wrap_command("eslint src/", profile, EnvStrategy.DIRECT)
        assert "node_modules/.bin/eslint" in result

    def test_resolver_wraps_with_activation(self, venv_project):
        from adelie.env_strategy import detect_env, wrap_command, EnvStrategy
        profile = detect_env(venv_project)
        result = wrap_command("pip install flask", profile, EnvStrategy.RESOLVER)
        assert "bash -c" in result
        assert "activate" in result
        assert "pip install flask" in result

    def test_resolver_uses_pipenv_prefix(self, tmp_path):
        (tmp_path / "Pipfile").write_text("[packages]\n", encoding="utf-8")
        from adelie.env_strategy import detect_env, wrap_command, EnvStrategy
        profile = detect_env(tmp_path)
        result = wrap_command("python test.py", profile, EnvStrategy.RESOLVER)
        assert "pipenv run" in result

    def test_resolver_uses_poetry_prefix(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            '[tool.poetry]\nname = "x"\n', encoding="utf-8"
        )
        from adelie.env_strategy import detect_env, wrap_command, EnvStrategy
        profile = detect_env(tmp_path)
        result = wrap_command("python test.py", profile, EnvStrategy.RESOLVER)
        assert "poetry run" in result

    def test_docker_wraps_with_docker_run(self, docker_project):
        from adelie.env_strategy import detect_env, wrap_command, EnvStrategy
        profile = detect_env(docker_project)
        result = wrap_command("npm test", profile, EnvStrategy.DOCKER)
        assert "docker run" in result
        assert "npm test" in result

    def test_empty_command_unchanged(self, venv_project):
        from adelie.env_strategy import detect_env, wrap_command, EnvStrategy
        profile = detect_env(venv_project)
        assert wrap_command("", profile, EnvStrategy.DIRECT) == ""
        assert wrap_command("  ", profile, EnvStrategy.RESOLVER) == "  "

    def test_system_env_no_changes(self, empty_project):
        from adelie.env_strategy import detect_env, wrap_command, EnvStrategy
        profile = detect_env(empty_project)
        assert wrap_command("python test.py", profile, EnvStrategy.DIRECT) == "python test.py"


# ── Phase Integration Tests ──────────────────────────────────────────────────


class TestPhaseIntegration:
    def test_all_phases_have_env_strategies(self):
        from adelie.phases import PHASE_INFO
        for phase_key, info in PHASE_INFO.items():
            assert "env_strategies" in info, f"Phase {phase_key} missing env_strategies"
            assert len(info["env_strategies"]) > 0

    def test_phase_strategy_map_covers_all_phases(self):
        from adelie.env_strategy import PHASE_STRATEGY_MAP
        from adelie.phases import Phase
        for phase in Phase:
            assert phase.value in PHASE_STRATEGY_MAP, f"Phase {phase.value} not in PHASE_STRATEGY_MAP"


# ── Helper Function Tests ────────────────────────────────────────────────────


class TestHelpers:
    def test_get_env_summary(self, venv_project):
        from adelie.env_strategy import detect_env, get_env_summary, EnvStrategy
        profile = detect_env(venv_project)
        summary = get_env_summary(profile, EnvStrategy.DIRECT)
        assert "venv" in summary
        assert "direct" in summary

    def test_get_env_summary_system(self, empty_project):
        from adelie.env_strategy import detect_env, get_env_summary, EnvStrategy
        profile = detect_env(empty_project)
        summary = get_env_summary(profile, EnvStrategy.DIRECT)
        assert "system" in summary
