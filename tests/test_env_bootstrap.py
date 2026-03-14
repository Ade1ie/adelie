"""tests/test_env_bootstrap.py — Unit tests for the env bootstrap (ensure_env)."""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest import mock

import pytest

from adelie.env_strategy import (
    EnvProfile,
    detect_env,
    ensure_env,
    _bootstrap_npm,
    _bootstrap_python,
)


class TestEnsureEnv:
    def test_no_action_when_env_exists(self, tmp_path):
        """If node_modules already exists, ensure_env should not call npm install."""
        # Create package.json and node_modules
        (tmp_path / "package.json").write_text('{"name": "test"}', encoding="utf-8")
        (tmp_path / "node_modules" / ".bin").mkdir(parents=True)

        profile = detect_env(tmp_path)

        with mock.patch("adelie.env_strategy.subprocess.run") as mock_run:
            result = ensure_env(profile, tmp_path)
            mock_run.assert_not_called()

    def test_no_action_without_package_json(self, tmp_path):
        """No package.json = no npm bootstrap."""
        profile = EnvProfile()

        with mock.patch("adelie.env_strategy.subprocess.run") as mock_run:
            result = ensure_env(profile, tmp_path)
            mock_run.assert_not_called()

    def test_triggers_npm_when_node_modules_missing(self, tmp_path):
        """package.json exists but node_modules missing → should call npm install."""
        (tmp_path / "package.json").write_text('{"name": "test"}', encoding="utf-8")

        profile = detect_env(tmp_path)

        with mock.patch("adelie.env_strategy.subprocess.run") as mock_run:
            mock_run.return_value = mock.MagicMock(returncode=0, stderr="", stdout="")
            ensure_env(profile, tmp_path)
            # Should have called npm install
            assert mock_run.called
            first_call = mock_run.call_args_list[0]
            assert "npm" in first_call[0][0]
            assert "install" in first_call[0][0]

    def test_triggers_venv_when_missing(self, tmp_path):
        """requirements.txt exists but no venv → should create venv."""
        (tmp_path / "requirements.txt").write_text("flask", encoding="utf-8")

        profile = detect_env(tmp_path)

        with mock.patch("adelie.env_strategy.subprocess.run") as mock_run:
            with mock.patch("adelie.env_strategy.shutil.which", return_value="/usr/bin/python3"):
                mock_run.return_value = mock.MagicMock(returncode=0, stderr="", stdout="")
                ensure_env(profile, tmp_path)
                assert mock_run.called

    def test_skips_venv_if_pipenv(self, tmp_path):
        """If pipenv is detected, don't create a new venv."""
        (tmp_path / "requirements.txt").write_text("flask", encoding="utf-8")
        (tmp_path / "Pipfile").write_text("[packages]", encoding="utf-8")

        profile = detect_env(tmp_path)
        assert "pipenv" in profile.detected_envs

        with mock.patch("adelie.env_strategy.subprocess.run") as mock_run:
            ensure_env(profile, tmp_path)
            mock_run.assert_not_called()


class TestBootstrapNpm:
    def test_success_on_first_try(self, tmp_path):
        with mock.patch("adelie.env_strategy.subprocess.run") as mock_run:
            mock_run.return_value = mock.MagicMock(returncode=0, stderr="", stdout="")
            result = _bootstrap_npm(tmp_path)
            assert result is True
            assert mock_run.call_count == 1

    def test_fallback_to_legacy_peer_deps(self, tmp_path):
        with mock.patch("adelie.env_strategy.subprocess.run") as mock_run:
            # First call fails, second succeeds
            mock_run.side_effect = [
                mock.MagicMock(returncode=1, stderr="ERESOLVE", stdout=""),
                mock.MagicMock(returncode=0, stderr="", stdout=""),
            ]
            result = _bootstrap_npm(tmp_path)
            assert result is True
            assert mock_run.call_count == 2
            # Second call should have --legacy-peer-deps
            second_call_cmd = mock_run.call_args_list[1][0][0]
            assert "--legacy-peer-deps" in second_call_cmd

    def test_fallback_to_force(self, tmp_path):
        with mock.patch("adelie.env_strategy.subprocess.run") as mock_run:
            mock_run.side_effect = [
                mock.MagicMock(returncode=1, stderr="ERESOLVE", stdout=""),
                mock.MagicMock(returncode=1, stderr="ERESOLVE", stdout=""),
                mock.MagicMock(returncode=0, stderr="", stdout=""),
            ]
            result = _bootstrap_npm(tmp_path)
            assert result is True
            assert mock_run.call_count == 3
            third_call_cmd = mock_run.call_args_list[2][0][0]
            assert "--force" in third_call_cmd

    def test_all_strategies_fail(self, tmp_path):
        with mock.patch("adelie.env_strategy.subprocess.run") as mock_run:
            mock_run.return_value = mock.MagicMock(returncode=1, stderr="error", stdout="")
            result = _bootstrap_npm(tmp_path)
            assert result is False
            assert mock_run.call_count == 3

    def test_handles_timeout(self, tmp_path):
        with mock.patch("adelie.env_strategy.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="npm install", timeout=180)
            result = _bootstrap_npm(tmp_path)
            assert result is False


class TestBootstrapPython:
    def test_creates_venv_and_installs(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("flask", encoding="utf-8")

        with mock.patch("adelie.env_strategy.subprocess.run") as mock_run:
            with mock.patch("adelie.env_strategy.shutil.which", return_value="/usr/bin/python3"):
                mock_run.return_value = mock.MagicMock(returncode=0, stderr="", stdout="")
                # We need the venv "bin" dir to exist after creation for pip path
                venv_bin = tmp_path / ".venv" / "bin"

                def create_venv_dir(*args, **kwargs):
                    venv_bin.mkdir(parents=True, exist_ok=True)
                    (venv_bin / "pip").touch()
                    return mock.MagicMock(returncode=0, stderr="", stdout="")

                mock_run.side_effect = create_venv_dir
                result = _bootstrap_python(tmp_path)
                assert result is True

    def test_fails_without_python(self, tmp_path):
        with mock.patch("adelie.env_strategy.shutil.which", return_value=None):
            result = _bootstrap_python(tmp_path)
            assert result is False
