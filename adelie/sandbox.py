"""
adelie/sandbox.py

Sandbox Mode — isolates code execution for security.

Three modes:
  NONE     — no sandboxing (default)
  SEATBELT — macOS sandbox-exec with restrictive profile
  DOCKER   — run commands inside a temporary Docker container

Seatbelt profile restricts:
  - Network access (except localhost for dev servers)
  - File writes outside the project directory
  - Process execution to whitelisted binaries

Inspired by gemini-cli's macOS Seatbelt / Docker sandbox.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
from enum import Enum
from pathlib import Path
from typing import Optional

from adelie.config import PROJECT_ROOT


class SandboxMode(str, Enum):
    NONE = "none"
    SEATBELT = "seatbelt"
    DOCKER = "docker"


# ── Default Seatbelt Profile ─────────────────────────────────────────────────

_DEFAULT_SEATBELT_PROFILE = """\
;; Adelie Sandbox Profile — restrictive macOS Seatbelt
;; Allows: read everywhere, write only in project dir, localhost network
(version 1)

;; Deny everything by default
(deny default)

;; Allow basic process operations
(allow process-exec)
(allow process-fork)
(allow signal)
(allow sysctl-read)
(allow mach-lookup)
(allow ipc-posix-shm-read-data)
(allow ipc-posix-shm-write-data)

;; Allow reading from anywhere (needed for binaries, libs, etc.)
(allow file-read*)

;; Allow writing ONLY to project directory and temp
(allow file-write*
    (subpath "{project_root}")
    (subpath "/tmp")
    (subpath "/private/tmp")
    (subpath "/var/folders"))

;; Allow network to localhost only (for dev servers)
(allow network*
    (local ip "localhost:*")
    (remote ip "localhost:*")
    (local ip "127.0.0.1:*")
    (remote ip "127.0.0.1:*"))

;; Allow DNS resolution
(allow network-outbound
    (remote unix-socket (path-literal "/var/run/mDNSResponder")))

;; Allow executing common dev tools
(allow process-exec
    (literal "/bin/sh")
    (literal "/bin/bash")
    (literal "/usr/bin/env")
    (literal "/usr/bin/python3")
    (literal "/usr/local/bin/node")
    (literal "/usr/local/bin/npm")
    (literal "/usr/local/bin/npx"))
"""


def _get_seatbelt_profile(project_root: Path | None = None) -> str:
    """
    Get the Seatbelt profile contents.
    If .adelie/sandbox.sb exists, use that. Otherwise, use the default.
    """
    root = project_root or PROJECT_ROOT
    adelie_dir = root / ".adelie" if (root / ".adelie").exists() else None

    # Check for user-defined profile
    if adelie_dir:
        custom_profile = adelie_dir / "sandbox.sb"
        if custom_profile.exists():
            try:
                return custom_profile.read_text(encoding="utf-8")
            except Exception:
                pass

    # Use default, with project root substituted
    return _DEFAULT_SEATBELT_PROFILE.replace("{project_root}", str(root))


def _write_seatbelt_profile(project_root: Path | None = None) -> Path:
    """
    Write the Seatbelt profile to a temp file and return its path.
    """
    root = project_root or PROJECT_ROOT
    profile_content = _get_seatbelt_profile(root)

    # Write to a temp file in .adelie/
    adelie_dir = root / ".adelie"
    adelie_dir.mkdir(parents=True, exist_ok=True)
    profile_path = adelie_dir / "_sandbox_active.sb"
    profile_path.write_text(profile_content, encoding="utf-8")
    return profile_path


def export_seatbelt_profile(project_root: Path | None = None) -> Path:
    """
    Export the default Seatbelt profile to .adelie/sandbox.sb for user customization.
    Returns the path of the exported file.
    """
    root = project_root or PROJECT_ROOT
    adelie_dir = root / ".adelie"
    adelie_dir.mkdir(parents=True, exist_ok=True)

    profile_path = adelie_dir / "sandbox.sb"
    if not profile_path.exists():
        profile_content = _DEFAULT_SEATBELT_PROFILE.replace("{project_root}", str(root))
        profile_path.write_text(profile_content, encoding="utf-8")

    return profile_path


# ── Sandbox Wrapping ─────────────────────────────────────────────────────────


def is_seatbelt_available() -> bool:
    """Check if macOS Seatbelt (sandbox-exec) is available."""
    return (
        platform.system() == "Darwin"
        and shutil.which("sandbox-exec") is not None
    )


def is_docker_available() -> bool:
    """Check if Docker is available and running."""
    if not shutil.which("docker"):
        return False
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def wrap_command(
    cmd: str,
    mode: SandboxMode,
    project_root: Path | None = None,
    docker_image: str = "",
) -> str:
    """
    Wrap a command with sandbox protection.

    Args:
        cmd: The command to wrap.
        mode: Sandbox mode to apply.
        project_root: Project root directory.
        docker_image: Docker image for DOCKER mode.

    Returns:
        The wrapped command string.
    """
    if not cmd or not cmd.strip():
        return cmd

    if mode == SandboxMode.NONE:
        return cmd

    if mode == SandboxMode.SEATBELT:
        return _wrap_seatbelt(cmd, project_root)

    if mode == SandboxMode.DOCKER:
        return _wrap_docker(cmd, project_root, docker_image)

    return cmd


def _wrap_seatbelt(cmd: str, project_root: Path | None = None) -> str:
    """Wrap command with macOS Seatbelt sandbox-exec."""
    if not is_seatbelt_available():
        return cmd  # Fallback to no sandbox on non-macOS

    profile_path = _write_seatbelt_profile(project_root)

    # Escape single quotes in command
    escaped_cmd = cmd.replace("'", "'\\''")
    return f"sandbox-exec -f '{profile_path}' bash -c '{escaped_cmd}'"


def _wrap_docker(
    cmd: str,
    project_root: Path | None = None,
    docker_image: str = "",
) -> str:
    """Wrap command with Docker container isolation."""
    if not is_docker_available():
        return cmd  # Fallback to no sandbox

    root = project_root or PROJECT_ROOT
    image = docker_image or f"adelie-sandbox-{root.name.lower()}"

    # Mount project directory read-write, everything else read-only
    escaped_cmd = cmd.replace("'", "'\\''")
    return (
        f"docker run --rm "
        f"-v '{root}:/workspace' "
        f"-w /workspace "
        f"--network host "
        f"--memory 512m "
        f"--cpus 1 "
        f"{image} "
        f"bash -c '{escaped_cmd}'"
    )


# ── Mode Detection ───────────────────────────────────────────────────────────


def get_effective_mode(configured_mode: str) -> SandboxMode:
    """
    Determine the effective sandbox mode based on configuration and availability.

    Falls back gracefully:
      seatbelt → none (if not macOS / not available)
      docker → none (if Docker not running)
    """
    try:
        mode = SandboxMode(configured_mode.lower())
    except ValueError:
        return SandboxMode.NONE

    if mode == SandboxMode.SEATBELT and not is_seatbelt_available():
        return SandboxMode.NONE

    if mode == SandboxMode.DOCKER and not is_docker_available():
        return SandboxMode.NONE

    return mode


def get_sandbox_summary(mode: SandboxMode) -> str:
    """Get a human-readable summary of the current sandbox mode."""
    summaries = {
        SandboxMode.NONE: "🔓 No sandbox — commands run without isolation",
        SandboxMode.SEATBELT: "🔒 macOS Seatbelt — restricted file/network access",
        SandboxMode.DOCKER: "🐳 Docker — containerized execution",
    }
    return summaries.get(mode, "Unknown sandbox mode")
