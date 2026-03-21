"""tests/test_os_detection.py — Tests for OS detection and context generation."""
from __future__ import annotations

import json
import platform
from unittest.mock import patch, MagicMock
from pathlib import Path

import pytest


# ── _detect_os tests ─────────────────────────────────────────────────────────

class TestDetectOS:
    def test_returns_valid_dict(self):
        """_detect_os returns a dict with all required keys."""
        from adelie.cli import _detect_os
        result = _detect_os()

        assert isinstance(result, dict)
        assert "system" in result
        assert "os_name" in result
        assert "release" in result
        assert "machine" in result
        assert "shell" in result
        assert result["system"] in ("Windows", "Linux", "Darwin")

    @patch("platform.system", return_value="Windows")
    @patch("platform.release", return_value="11")
    @patch("platform.machine", return_value="AMD64")
    @patch("platform.version", return_value="10.0.26100")
    def test_windows_detection(self, _v, _m, _r, _s, monkeypatch):
        monkeypatch.setenv("PSModulePath", "C:\\something")
        from adelie.cli import _detect_os
        result = _detect_os()

        assert result["system"] == "Windows"
        assert result["os_name"] == "Windows"
        assert result["shell"] == "PowerShell"

    @patch("platform.system", return_value="Darwin")
    @patch("platform.release", return_value="24.3.0")
    @patch("platform.machine", return_value="arm64")
    @patch("platform.version", return_value="Darwin Kernel")
    @patch("platform.mac_ver", return_value=("15.3", ("", "", ""), ""))
    def test_macos_detection(self, _mv, _v, _m, _r, _s, monkeypatch):
        monkeypatch.setenv("SHELL", "/bin/zsh")
        from adelie.cli import _detect_os
        result = _detect_os()

        assert result["system"] == "Darwin"
        assert result["os_name"] == "macOS"
        assert result["release"] == "15.3"
        assert result["shell"] == "zsh"

    @patch("platform.system", return_value="Linux")
    @patch("platform.release", return_value="5.15.0-91-generic")
    @patch("platform.machine", return_value="x86_64")
    @patch("platform.version", return_value="#101-Ubuntu")
    def test_linux_detection(self, _v, _m, _r, _s, monkeypatch):
        monkeypatch.setenv("SHELL", "/bin/bash")
        from adelie.cli import _detect_os
        result = _detect_os()

        assert result["system"] == "Linux"
        assert "Linux" in result["os_name"]
        assert result["shell"] == "bash"


# ── _generate_os_context tests ───────────────────────────────────────────────

class TestGenerateOSContext:
    def test_windows_context_has_powershell(self):
        from adelie.cli import _generate_os_context
        ctx = _generate_os_context({
            "system": "Windows", "os_name": "Windows",
            "release": "11", "machine": "AMD64", "shell": "PowerShell",
        })
        assert "## System Environment" in ctx
        assert "PowerShell" in ctx
        assert "Remove-Item" in ctx
        assert "Docker on Windows" in ctx
        assert "$env:" in ctx

    def test_macos_context_has_zsh(self):
        from adelie.cli import _generate_os_context
        ctx = _generate_os_context({
            "system": "Darwin", "os_name": "macOS",
            "release": "15.3", "machine": "arm64", "shell": "zsh",
        })
        assert "## System Environment" in ctx
        assert "zsh" in ctx
        assert "rm -f" in ctx
        assert "Docker on macOS" in ctx
        assert "Apple Silicon" in ctx

    def test_macos_intel_no_silicon_note(self):
        from adelie.cli import _generate_os_context
        ctx = _generate_os_context({
            "system": "Darwin", "os_name": "macOS",
            "release": "14.0", "machine": "x86_64", "shell": "zsh",
        })
        assert "Apple Silicon" not in ctx
        assert "/usr/local/" in ctx

    def test_linux_context_has_bash(self):
        from adelie.cli import _generate_os_context
        ctx = _generate_os_context({
            "system": "Linux", "os_name": "Linux (Ubuntu 22.04)",
            "release": "5.15.0", "machine": "x86_64", "shell": "bash",
        })
        assert "## System Environment" in ctx
        assert "bash" in ctx
        assert "rm -f" in ctx
        assert "Docker on Linux" in ctx
        assert "sudo" in ctx

    def test_context_is_english(self):
        """All OS contexts should be in English."""
        from adelie.cli import _generate_os_context
        for system in ["Windows", "Darwin", "Linux"]:
            ctx = _generate_os_context({
                "system": system, "os_name": "Test",
                "release": "1.0", "machine": "x86_64", "shell": "sh",
            })
            assert "System Environment" in ctx
            assert "Command Reference" in ctx
            assert "Testing & Build" in ctx


# ── cmd_init integration (context.md generation) ─────────────────────────────

class TestInitOSContext:
    def test_init_creates_context_md(self, tmp_path, monkeypatch):
        """adelie init should create .adelie/context.md with OS info."""
        import argparse
        import adelie.registry as reg_module
        monkeypatch.setattr(reg_module, "register", lambda path: None)

        from adelie.cli import cmd_init
        args = argparse.Namespace(directory=str(tmp_path), force=False)
        cmd_init(args)

        context_file = tmp_path / ".adelie" / "context.md"
        assert context_file.exists()
        content = context_file.read_text(encoding="utf-8")
        assert "## System Environment" in content

    def test_init_saves_os_to_config(self, tmp_path, monkeypatch):
        """adelie init should save OS info in config.json."""
        import argparse
        import adelie.registry as reg_module
        monkeypatch.setattr(reg_module, "register", lambda path: None)

        from adelie.cli import cmd_init
        args = argparse.Namespace(directory=str(tmp_path), force=False)
        cmd_init(args)

        config_path = tmp_path / ".adelie" / "config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        assert "os" in config
        assert config["os"]["system"] in ("Windows", "Linux", "Darwin")
        assert "shell" in config["os"]


# ── project_context.get_os_info tests ────────────────────────────────────────

class TestGetOSInfo:
    def test_returns_string(self):
        from adelie.project_context import get_os_info
        result = get_os_info()
        assert isinstance(result, str)
        assert "OS:" in result

    @patch("platform.system", return_value="Windows")
    @patch("platform.release", return_value="11")
    @patch("platform.machine", return_value="AMD64")
    def test_windows_info(self, _m, _r, _s):
        from adelie.project_context import get_os_info
        result = get_os_info()
        assert "Windows" in result
        assert "AMD64" in result

    @patch("platform.system", return_value="Darwin")
    @patch("platform.machine", return_value="arm64")
    @patch("platform.mac_ver", return_value=("15.3", ("", "", ""), ""))
    def test_macos_info(self, _mv, _m, _s):
        from adelie.project_context import get_os_info
        result = get_os_info()
        assert "macOS" in result
        assert "arm64" in result
