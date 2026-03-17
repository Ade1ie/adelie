"""tests/test_sandbox.py — Tests for Sandbox Mode module."""
from __future__ import annotations

import platform
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# ── SandboxMode Enum Tests ───────────────────────────────────────────────────


class TestSandboxMode:
    def test_enum_values(self):
        from adelie.sandbox import SandboxMode
        assert SandboxMode.NONE.value == "none"
        assert SandboxMode.SEATBELT.value == "seatbelt"
        assert SandboxMode.DOCKER.value == "docker"

    def test_enum_from_string(self):
        from adelie.sandbox import SandboxMode
        assert SandboxMode("none") == SandboxMode.NONE
        assert SandboxMode("seatbelt") == SandboxMode.SEATBELT
        assert SandboxMode("docker") == SandboxMode.DOCKER


# ── Seatbelt Profile Tests ──────────────────────────────────────────────────


class TestSeatbeltProfile:
    def test_default_profile_contains_deny_default(self, tmp_path):
        from adelie.sandbox import _get_seatbelt_profile
        profile = _get_seatbelt_profile(tmp_path)
        assert "(deny default)" in profile
        assert "(allow file-read*)" in profile

    def test_default_profile_substitutes_project_root(self, tmp_path):
        from adelie.sandbox import _get_seatbelt_profile
        profile = _get_seatbelt_profile(tmp_path)
        assert str(tmp_path) in profile
        assert "{project_root}" not in profile

    def test_custom_profile_used_when_exists(self, tmp_path):
        adelie_dir = tmp_path / ".adelie"
        adelie_dir.mkdir()
        custom = adelie_dir / "sandbox.sb"
        custom.write_text(";; Custom sandbox profile\n(version 1)\n", encoding="utf-8")

        from adelie.sandbox import _get_seatbelt_profile
        profile = _get_seatbelt_profile(tmp_path)
        assert ";; Custom sandbox profile" in profile

    def test_write_seatbelt_profile(self, tmp_path):
        adelie_dir = tmp_path / ".adelie"
        adelie_dir.mkdir()

        from adelie.sandbox import _write_seatbelt_profile
        profile_path = _write_seatbelt_profile(tmp_path)
        assert profile_path.exists()
        assert profile_path.name == "_sandbox_active.sb"

    def test_export_seatbelt_profile(self, tmp_path):
        from adelie.sandbox import export_seatbelt_profile
        path = export_seatbelt_profile(tmp_path)
        assert path.exists()
        assert path.name == "sandbox.sb"
        content = path.read_text()
        assert "(deny default)" in content


# ── Command Wrapping Tests ───────────────────────────────────────────────────


class TestWrapCommand:
    def test_none_mode_returns_unchanged(self):
        from adelie.sandbox import wrap_command, SandboxMode
        assert wrap_command("echo hello", SandboxMode.NONE) == "echo hello"

    def test_empty_command_unchanged(self):
        from adelie.sandbox import wrap_command, SandboxMode
        assert wrap_command("", SandboxMode.SEATBELT) == ""
        assert wrap_command("  ", SandboxMode.DOCKER) == "  "

    @patch("adelie.sandbox.is_seatbelt_available", return_value=True)
    def test_seatbelt_wraps_with_sandbox_exec(self, mock_avail, tmp_path):
        from adelie.sandbox import wrap_command, SandboxMode
        result = wrap_command("python test.py", SandboxMode.SEATBELT, tmp_path)
        assert "sandbox-exec" in result
        assert "python test.py" in result
        assert "-f" in result

    @patch("adelie.sandbox.is_seatbelt_available", return_value=False)
    def test_seatbelt_fallback_on_non_macos(self, mock_avail):
        from adelie.sandbox import wrap_command, SandboxMode
        result = wrap_command("python test.py", SandboxMode.SEATBELT)
        assert result == "python test.py"  # Fallback to no sandbox

    @patch("adelie.sandbox.is_docker_available", return_value=True)
    def test_docker_wraps_with_docker_run(self, mock_avail, tmp_path):
        from adelie.sandbox import wrap_command, SandboxMode
        result = wrap_command("npm test", SandboxMode.DOCKER, tmp_path)
        assert "docker run" in result
        assert "--rm" in result
        assert "npm test" in result
        assert "--memory" in result

    @patch("adelie.sandbox.is_docker_available", return_value=False)
    def test_docker_fallback_when_unavailable(self, mock_avail):
        from adelie.sandbox import wrap_command, SandboxMode
        result = wrap_command("npm test", SandboxMode.DOCKER)
        assert result == "npm test"  # Fallback


# ── Effective Mode Tests ─────────────────────────────────────────────────────


class TestEffectiveMode:
    def test_none_always_available(self):
        from adelie.sandbox import get_effective_mode, SandboxMode
        assert get_effective_mode("none") == SandboxMode.NONE

    def test_invalid_mode_returns_none(self):
        from adelie.sandbox import get_effective_mode, SandboxMode
        assert get_effective_mode("invalid") == SandboxMode.NONE
        assert get_effective_mode("") == SandboxMode.NONE

    @patch("adelie.sandbox.is_seatbelt_available", return_value=True)
    def test_seatbelt_when_available(self, mock_avail):
        from adelie.sandbox import get_effective_mode, SandboxMode
        assert get_effective_mode("seatbelt") == SandboxMode.SEATBELT

    @patch("adelie.sandbox.is_seatbelt_available", return_value=False)
    def test_seatbelt_fallback_to_none(self, mock_avail):
        from adelie.sandbox import get_effective_mode, SandboxMode
        assert get_effective_mode("seatbelt") == SandboxMode.NONE

    @patch("adelie.sandbox.is_docker_available", return_value=True)
    def test_docker_when_available(self, mock_avail):
        from adelie.sandbox import get_effective_mode, SandboxMode
        assert get_effective_mode("docker") == SandboxMode.DOCKER

    @patch("adelie.sandbox.is_docker_available", return_value=False)
    def test_docker_fallback_to_none(self, mock_avail):
        from adelie.sandbox import get_effective_mode, SandboxMode
        assert get_effective_mode("docker") == SandboxMode.NONE


# ── Summary Tests ────────────────────────────────────────────────────────────


class TestSummary:
    def test_sandbox_summary_none(self):
        from adelie.sandbox import get_sandbox_summary, SandboxMode
        summary = get_sandbox_summary(SandboxMode.NONE)
        assert "No sandbox" in summary

    def test_sandbox_summary_seatbelt(self):
        from adelie.sandbox import get_sandbox_summary, SandboxMode
        summary = get_sandbox_summary(SandboxMode.SEATBELT)
        assert "Seatbelt" in summary

    def test_sandbox_summary_docker(self):
        from adelie.sandbox import get_sandbox_summary, SandboxMode
        summary = get_sandbox_summary(SandboxMode.DOCKER)
        assert "Docker" in summary


# ── Availability Detection Tests ─────────────────────────────────────────────


class TestAvailability:
    @patch("platform.system", return_value="Darwin")
    @patch("shutil.which", return_value="/usr/bin/sandbox-exec")
    def test_seatbelt_available_on_macos(self, mock_which, mock_sys):
        from adelie.sandbox import is_seatbelt_available
        assert is_seatbelt_available()

    @patch("platform.system", return_value="Linux")
    def test_seatbelt_unavailable_on_linux(self, mock_sys):
        from adelie.sandbox import is_seatbelt_available
        assert not is_seatbelt_available()

    @patch("shutil.which", return_value=None)
    def test_docker_unavailable_when_not_installed(self, mock_which):
        from adelie.sandbox import is_docker_available
        assert not is_docker_available()
