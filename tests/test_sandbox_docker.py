"""tests/test_sandbox_docker.py — Tests for enhanced Docker sandbox configuration."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest


class TestDockerSandboxConfig:
    def test_default_values(self):
        from adelie.sandbox import DockerSandboxConfig
        config = DockerSandboxConfig()
        assert config.image == "adelie-sandbox:latest"
        assert config.workspace_access == "rw"
        assert config.network == "none"
        assert config.memory_limit == "512m"
        assert config.cpu_limit == 1.0
        assert config.read_only_root is False
        assert config.env == {}
        assert config.binds == []

    def test_custom_values(self):
        from adelie.sandbox import DockerSandboxConfig
        config = DockerSandboxConfig(
            image="custom:v1",
            workspace_access="ro",
            network="bridge",
            memory_limit="2g",
            cpu_limit=4.0,
            read_only_root=True,
            user="1000:1000",
            env={"FOO": "bar"},
            binds=["/data:/data:ro"],
        )
        assert config.image == "custom:v1"
        assert config.workspace_access == "ro"
        assert config.read_only_root is True
        assert config.user == "1000:1000"


class TestLoadDockerConfig:
    def test_load_no_config_file(self, tmp_path):
        from adelie.sandbox import load_docker_config
        config = load_docker_config(tmp_path)
        assert config.image == "adelie-sandbox:latest"
        assert config.network == "none"

    def test_load_valid_config(self, tmp_path):
        from adelie.sandbox import load_docker_config
        adelie_dir = tmp_path / ".adelie"
        adelie_dir.mkdir()
        (adelie_dir / "sandbox.json").write_text(json.dumps({
            "docker": {
                "image": "my-sandbox:v2",
                "workspaceAccess": "ro",
                "network": "bridge",
                "memoryLimit": "1g",
                "cpuLimit": 2.0,
                "readOnlyRoot": True,
                "env": {"NODE_ENV": "test"},
                "binds": ["/shared:/shared:ro"],
            }
        }), encoding="utf-8")

        config = load_docker_config(tmp_path)
        assert config.image == "my-sandbox:v2"
        assert config.workspace_access == "ro"
        assert config.network == "bridge"
        assert config.memory_limit == "1g"
        assert config.cpu_limit == 2.0
        assert config.read_only_root is True
        assert config.env == {"NODE_ENV": "test"}
        assert config.binds == ["/shared:/shared:ro"]

    def test_load_invalid_json(self, tmp_path):
        from adelie.sandbox import load_docker_config
        adelie_dir = tmp_path / ".adelie"
        adelie_dir.mkdir()
        (adelie_dir / "sandbox.json").write_text("not json", encoding="utf-8")
        config = load_docker_config(tmp_path)
        assert config.image == "adelie-sandbox:latest"  # defaults

    def test_load_empty_docker_section(self, tmp_path):
        from adelie.sandbox import load_docker_config
        adelie_dir = tmp_path / ".adelie"
        adelie_dir.mkdir()
        (adelie_dir / "sandbox.json").write_text(json.dumps({"docker": {}}), encoding="utf-8")
        config = load_docker_config(tmp_path)
        assert config.image == "adelie-sandbox:latest"


class TestBindSafety:
    def test_safe_bind(self):
        from adelie.sandbox import _is_safe_bind
        assert _is_safe_bind("/data:/data:ro") is True
        assert _is_safe_bind("/home/user/code:/code:rw") is True

    def test_blocked_etc(self):
        from adelie.sandbox import _is_safe_bind
        assert _is_safe_bind("/etc:/config:ro") is False

    def test_blocked_proc(self):
        from adelie.sandbox import _is_safe_bind
        assert _is_safe_bind("/proc:/proc") is False

    def test_blocked_sys(self):
        from adelie.sandbox import _is_safe_bind
        assert _is_safe_bind("/sys:/sys") is False

    def test_blocked_docker_socket(self):
        from adelie.sandbox import _is_safe_bind
        assert _is_safe_bind("/var/run/docker.sock:/docker.sock") is False

    def test_blocked_ssh(self):
        from adelie.sandbox import _is_safe_bind
        assert _is_safe_bind("/home/user/.ssh:/ssh:ro") is False

    def test_blocked_gnupg(self):
        from adelie.sandbox import _is_safe_bind
        assert _is_safe_bind("/home/user/.gnupg:/gnupg") is False


class TestWrapDocker:
    """Test docker command wrapping with mocked docker availability."""

    @patch("adelie.sandbox.is_docker_available", return_value=True)
    def test_default_config(self, mock_docker, tmp_path):
        from adelie.sandbox import _wrap_docker
        result = _wrap_docker("echo hello", project_root=tmp_path)
        assert "docker run --rm" in result
        assert "--network none" in result
        assert "--memory 512m" in result
        assert "echo hello" in result

    @patch("adelie.sandbox.is_docker_available", return_value=True)
    def test_workspace_rw(self, mock_docker, tmp_path):
        from adelie.sandbox import _wrap_docker
        result = _wrap_docker("ls", project_root=tmp_path)
        assert f"-v '{tmp_path}:/workspace'" in result

    @patch("adelie.sandbox.is_docker_available", return_value=True)
    def test_workspace_ro(self, mock_docker, tmp_path):
        from adelie.sandbox import _wrap_docker
        # Create config with ro access
        adelie_dir = tmp_path / ".adelie"
        adelie_dir.mkdir()
        (adelie_dir / "sandbox.json").write_text(json.dumps({
            "docker": {"workspaceAccess": "ro"}
        }), encoding="utf-8")

        result = _wrap_docker("ls", project_root=tmp_path)
        assert f"-v '{tmp_path}:/workspace:ro'" in result

    @patch("adelie.sandbox.is_docker_available", return_value=True)
    def test_workspace_none(self, mock_docker, tmp_path):
        from adelie.sandbox import _wrap_docker
        adelie_dir = tmp_path / ".adelie"
        adelie_dir.mkdir()
        (adelie_dir / "sandbox.json").write_text(json.dumps({
            "docker": {"workspaceAccess": "none"}
        }), encoding="utf-8")

        result = _wrap_docker("ls", project_root=tmp_path)
        assert "/workspace'" not in result or "/workspace:ro" not in result

    @patch("adelie.sandbox.is_docker_available", return_value=True)
    def test_read_only_root(self, mock_docker, tmp_path):
        from adelie.sandbox import _wrap_docker
        adelie_dir = tmp_path / ".adelie"
        adelie_dir.mkdir()
        (adelie_dir / "sandbox.json").write_text(json.dumps({
            "docker": {"readOnlyRoot": True}
        }), encoding="utf-8")

        result = _wrap_docker("ls", project_root=tmp_path)
        assert "--read-only" in result
        assert "--tmpfs /tmp:rw,noexec,nosuid" in result

    @patch("adelie.sandbox.is_docker_available", return_value=True)
    def test_custom_image(self, mock_docker, tmp_path):
        from adelie.sandbox import _wrap_docker
        result = _wrap_docker("ls", project_root=tmp_path, docker_image="custom:v1")
        assert "custom:v1" in result

    @patch("adelie.sandbox.is_docker_available", return_value=True)
    def test_env_vars(self, mock_docker, tmp_path):
        from adelie.sandbox import _wrap_docker
        adelie_dir = tmp_path / ".adelie"
        adelie_dir.mkdir()
        (adelie_dir / "sandbox.json").write_text(json.dumps({
            "docker": {"env": {"NODE_ENV": "test"}}
        }), encoding="utf-8")

        result = _wrap_docker("npm test", project_root=tmp_path)
        assert "-e 'NODE_ENV=test'" in result

    @patch("adelie.sandbox.is_docker_available", return_value=True)
    def test_dangerous_binds_filtered(self, mock_docker, tmp_path):
        from adelie.sandbox import _wrap_docker
        adelie_dir = tmp_path / ".adelie"
        adelie_dir.mkdir()
        (adelie_dir / "sandbox.json").write_text(json.dumps({
            "docker": {
                "binds": [
                    "/data:/data:ro",              # safe
                    "/etc/passwd:/etc:ro",          # blocked
                    "/var/run/docker.sock:/sock",   # blocked
                ]
            }
        }), encoding="utf-8")

        result = _wrap_docker("ls", project_root=tmp_path)
        assert "/data:/data:ro" in result
        assert "/etc/passwd" not in result
        assert "docker.sock" not in result

    @patch("adelie.sandbox.is_docker_available", return_value=False)
    def test_fallback_when_docker_unavailable(self, mock_docker, tmp_path):
        from adelie.sandbox import _wrap_docker
        result = _wrap_docker("echo hello", project_root=tmp_path)
        assert result == "echo hello"  # No wrapping


class TestSandboxModes:
    def test_sandbox_mode_enum(self):
        from adelie.sandbox import SandboxMode
        assert SandboxMode.NONE == "none"
        assert SandboxMode.SEATBELT == "seatbelt"
        assert SandboxMode.DOCKER == "docker"

    def test_get_sandbox_summary(self):
        from adelie.sandbox import get_sandbox_summary, SandboxMode
        summary = get_sandbox_summary(SandboxMode.DOCKER)
        assert "Docker" in summary
        assert "network isolated" in summary

    def test_wrap_command_none(self):
        from adelie.sandbox import wrap_command, SandboxMode
        result = wrap_command("echo hi", SandboxMode.NONE)
        assert result == "echo hi"

    def test_wrap_command_empty(self):
        from adelie.sandbox import wrap_command, SandboxMode
        result = wrap_command("", SandboxMode.DOCKER)
        assert result == ""
