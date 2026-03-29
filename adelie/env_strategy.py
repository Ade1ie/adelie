"""
adelie/env_strategy.py

Environment Strategy — flexible execution environment management.

Detects the project's programming environment (venv, pipenv, poetry, npm, docker)
and selects the optimal execution strategy based on the project type and
the current development phase.

Three strategies:
  DIRECT   — Replace binary paths directly (.venv/bin/python instead of python)
  RESOLVER — Wrap commands with shell-based env activation
  DOCKER   — Execute commands inside a Docker container

Strategy selection follows the project phase:
  initial~mid  → DIRECT
  mid_1        → DIRECT, fallback to RESOLVER
  mid_2+       → RESOLVER preferred, DOCKER when available
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from rich.console import Console

console = Console()


# ── Strategy Enum ─────────────────────────────────────────────────────────────


class EnvStrategy(str, Enum):
    DIRECT = "direct"       # Path substitution: python → .venv/bin/python
    RESOLVER = "resolver"   # Shell wrapper: bash -c "source activate && cmd"
    DOCKER = "docker"       # Container execution: docker exec ... cmd


# ── Environment Profile ──────────────────────────────────────────────────────


@dataclass
class EnvProfile:
    """Detected project environment profile."""

    env_type: str = "system"          # venv, pipenv, poetry, npm, docker, system
    strategy: EnvStrategy = EnvStrategy.DIRECT

    # Python paths (filled if Python env detected)
    python_bin: Optional[str] = None  # e.g. ".venv/bin/python"
    pip_bin: Optional[str] = None     # e.g. ".venv/bin/pip"

    # Node paths (filled if Node env detected)
    node_bin: Optional[str] = None    # e.g. "./node_modules/.bin/node"
    npm_prefix: Optional[str] = None  # e.g. "./node_modules/.bin/"

    # Docker info (filled if Dockerfile exists)
    docker_image: Optional[str] = None
    docker_service: Optional[str] = None  # from docker-compose

    # Shell activation wrapper (for RESOLVER strategy)
    shell_wrapper: Optional[str] = None   # e.g. "source .venv/bin/activate"

    # All detected env types (a project can have both Python + Node)
    detected_envs: list[str] = field(default_factory=list)


# ── Phase-to-Strategy mapping ────────────────────────────────────────────────

# Ordered preference per phase (first available wins)
PHASE_STRATEGY_MAP: dict[str, list[EnvStrategy]] = {
    "initial":  [EnvStrategy.DIRECT],
    "mid":      [EnvStrategy.DIRECT],
    "mid_1":    [EnvStrategy.DIRECT, EnvStrategy.RESOLVER],
    "mid_2":    [EnvStrategy.RESOLVER, EnvStrategy.DOCKER],
    "late":     [EnvStrategy.DOCKER, EnvStrategy.RESOLVER, EnvStrategy.DIRECT],
    "evolve":   [EnvStrategy.DOCKER, EnvStrategy.RESOLVER, EnvStrategy.DIRECT],
}


# ── Binary replacement maps ──────────────────────────────────────────────────

# Commands that should be replaced with venv-specific binaries
PYTHON_BINARY_MAP = {
    "python":  "python",
    "python3": "python3",
    "pip":     "pip",
    "pip3":    "pip3",
    "pytest":  "pytest",
}

NODE_BINARY_MAP = {
    "node":   "node",
    "npx":    "npx",
    "tsc":    "tsc",
    "eslint": "eslint",
    "vitest": "vitest",
    "jest":   "jest",
}


# ── Detection ────────────────────────────────────────────────────────────────


def detect_env(project_root: Path) -> EnvProfile:
    """
    Scan project root for environment markers and build an EnvProfile.

    Detection order:
      1. Python venv / pipenv / poetry
      2. Node.js npm / yarn / pnpm
      3. Docker / docker-compose

    Returns an EnvProfile with all detected environments.
    """
    profile = EnvProfile()
    detected: list[str] = []

    # ── Python environments ───────────────────────────────────────────────

    # Standard venv
    _is_win = sys.platform == "win32"
    for venv_dir in [".venv", "venv"]:
        venv_path = project_root / venv_dir
        if venv_path.is_dir():
            bin_dir = venv_path / "bin"
            if not bin_dir.exists():
                bin_dir = venv_path / "Scripts"  # Windows
            if bin_dir.exists():
                profile.python_bin = str(bin_dir / "python")
                profile.pip_bin = str(bin_dir / "pip")
                # Windows: use activate.bat; Unix: source activate
                if _is_win:
                    activate_script = bin_dir / "activate.bat"
                    profile.shell_wrapper = f"{activate_script} &&"
                else:
                    profile.shell_wrapper = f"source {bin_dir / 'activate'}"
                profile.env_type = "venv"
                detected.append("venv")
                break

    # Pipenv
    if (project_root / "Pipfile").exists() and "venv" not in detected:
        profile.env_type = "pipenv"
        profile.shell_wrapper = "pipenv shell"
        detected.append("pipenv")
        # Try to find Pipenv's venv path
        if shutil.which("pipenv"):
            profile.python_bin = "pipenv run python"
            profile.pip_bin = "pipenv run pip"

    # Poetry
    if (project_root / "pyproject.toml").exists() and "venv" not in detected and "pipenv" not in detected:
        pyproject = (project_root / "pyproject.toml").read_text(encoding="utf-8", errors="replace")
        if "[tool.poetry]" in pyproject:
            profile.env_type = "poetry"
            profile.shell_wrapper = "poetry shell"
            detected.append("poetry")
            if shutil.which("poetry"):
                profile.python_bin = "poetry run python"
                profile.pip_bin = "poetry run pip"

    # ── Node.js environments ─────────────────────────────────────────────

    node_modules_bin = project_root / "node_modules" / ".bin"
    if node_modules_bin.is_dir():
        profile.node_bin = str(node_modules_bin / "node") if (node_modules_bin / "node").exists() else None
        profile.npm_prefix = str(node_modules_bin) + os.sep
        if profile.env_type == "system":
            profile.env_type = "npm"
        detected.append("npm")

    # ── Docker ────────────────────────────────────────────────────────────

    if (project_root / "Dockerfile").exists():
        detected.append("docker")
        # Try to extract image name from Dockerfile or use project dir name
        profile.docker_image = project_root.name.lower().replace(" ", "-")

    for compose_file in ["docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"]:
        if (project_root / compose_file).exists():
            detected.append("docker-compose")
            if "docker" not in detected:
                detected.append("docker")
            break

    profile.detected_envs = detected
    return profile


# ── Auto Bootstrap ───────────────────────────────────────────────────────────


def ensure_env(profile: EnvProfile, project_root: Path) -> EnvProfile:
    """
    Ensure that required environments are installed.
    If node_modules or venv is missing, auto-install them.

    Modifies the profile in-place and returns the updated profile
    (re-detected after installation).

    Args:
        profile:      previously detected environment profile
        project_root: project root directory

    Returns:
        Updated EnvProfile after bootstrapping.
    """
    bootstrapped = False

    # ── Node.js: package.json exists but node_modules missing ─────────────
    if (project_root / "package.json").exists():
        node_modules = project_root / "node_modules"
        if not node_modules.is_dir():
            console.print("[yellow]  📦 node_modules not found — bootstrapping npm environment…[/yellow]")
            bootstrapped = _bootstrap_npm(project_root)

    # ── Python: requirements.txt exists but no venv ──────────────────────
    if (project_root / "requirements.txt").exists():
        has_venv = any(
            (project_root / d).is_dir() for d in [".venv", "venv"]
        )
        if not has_venv and "pipenv" not in profile.detected_envs and "poetry" not in profile.detected_envs:
            console.print("[yellow]  📦 Python venv not found — bootstrapping virtual environment…[/yellow]")
            bootstrapped = _bootstrap_python(project_root) or bootstrapped

    # Re-detect environment if bootstrapping happened
    if bootstrapped:
        return detect_env(project_root)

    return profile


def _bootstrap_npm(project_root: Path) -> bool:
    """
    Install npm dependencies with progressive fallback:
      1. npm install
      2. npm install --legacy-peer-deps  (dependency conflicts)
      3. npm install --force             (last resort)

    Returns True if any attempt succeeded.
    """
    import sys
    _win = sys.platform == "win32"
    strategies = [
        ("npm install", "npm install"),
        ("npm install --legacy-peer-deps", "npm install --legacy-peer-deps"),
        ("npm install --force", "npm install --force"),
    ]

    for label, cmd in strategies:
        console.print(f"  [dim]  ▶ {label}…[/dim]")
        try:
            if _win:
                result = subprocess.run(
                    cmd,
                    cwd=str(project_root),
                    capture_output=True,
                    text=True,
                    timeout=180,
                    shell=True,
                )
            else:
                result = subprocess.run(
                    cmd.split(),
                    cwd=str(project_root),
                    capture_output=True,
                    text=True,
                    timeout=180,
                )
            if result.returncode == 0:
                console.print(f"  [green]  ✅ {label} succeeded[/green]")
                return True
            else:
                stderr_short = result.stderr.strip()[-200:] if result.stderr else ""
                console.print(f"  [dim]  ⚠️ {label} failed — trying fallback…[/dim]")
                if stderr_short:
                    console.print(f"  [dim]    {stderr_short}[/dim]")
        except subprocess.TimeoutExpired:
            console.print(f"  [dim]  ⏱️ {label} timed out — trying fallback…[/dim]")
        except Exception as e:
            console.print(f"  [dim]  ❌ {label} error: {e}[/dim]")

    console.print("[red]  ❌ All npm install strategies failed[/red]")
    return False


def _bootstrap_python(project_root: Path) -> bool:
    """
    Create a Python venv and install requirements:
      1. python3 -m venv .venv
      2. .venv/bin/pip install -r requirements.txt

    Returns True if succeeded.
    """
    venv_path = project_root / ".venv"

    # Step 1: Create venv
    python_bin = shutil.which("python3") or shutil.which("python")
    if not python_bin:
        console.print("  [red]  ❌ python3 not found on system[/red]")
        return False

    console.print("  [dim]  ▶ Creating .venv…[/dim]")
    try:
        result = subprocess.run(
            [python_bin, "-m", "venv", str(venv_path)],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            console.print(f"  [red]  ❌ venv creation failed: {result.stderr[:200]}[/red]")
            return False
    except Exception as e:
        console.print(f"  [red]  ❌ venv creation error: {e}[/red]")
        return False

    # Step 2: Install requirements
    pip_bin = str(venv_path / "bin" / "pip")
    if not Path(pip_bin).exists():
        pip_bin = str(venv_path / "Scripts" / "pip")  # Windows

    req_file = project_root / "requirements.txt"
    if req_file.exists():
        console.print("  [dim]  ▶ Installing requirements…[/dim]")
        try:
            result = subprocess.run(
                [pip_bin, "install", "-r", str(req_file)],
                cwd=str(project_root),
                capture_output=True,
                text=True,
                timeout=180,
            )
            if result.returncode == 0:
                console.print("  [green]  ✅ Python environment ready[/green]")
                return True
            else:
                console.print(f"  [yellow]  ⚠️ pip install had issues: {result.stderr[:200]}[/yellow]")
                return True  # venv still usable
        except Exception as e:
            console.print(f"  [yellow]  ⚠️ pip install error: {e}[/yellow]")
            return True  # venv still usable
    else:
        console.print("  [green]  ✅ Python venv created (no requirements.txt)[/green]")
        return True


# ── Strategy Selection ───────────────────────────────────────────────────────


def select_strategy(profile: EnvProfile, phase: str) -> EnvStrategy:
    """
    Select the optimal execution strategy based on phase and environment.

    Logic:
      1. Get the phase's preferred strategy order
      2. Check each strategy's feasibility for the detected environment
      3. Return the first feasible strategy (with fallback to DIRECT)

    Args:
        profile: detected environment profile
        phase:   current project phase (e.g. "mid", "mid_2")

    Returns:
        The selected EnvStrategy.
    """
    preferences = PHASE_STRATEGY_MAP.get(phase, [EnvStrategy.DIRECT])

    for strategy in preferences:
        if _is_strategy_feasible(strategy, profile):
            return strategy

    # Ultimate fallback
    return EnvStrategy.DIRECT


def _is_strategy_feasible(strategy: EnvStrategy, profile: EnvProfile) -> bool:
    """Check whether a strategy can actually work with the detected env."""

    if strategy == EnvStrategy.DIRECT:
        # Always feasible — worst case just uses system binaries
        return True

    elif strategy == EnvStrategy.RESOLVER:
        # Need a shell wrapper or a tool-specific prefix (pipenv run, poetry run)
        return bool(profile.shell_wrapper or profile.python_bin)

    elif strategy == EnvStrategy.DOCKER:
        # Need Docker installed AND a Dockerfile/compose in the project
        if "docker" not in profile.detected_envs:
            return False
        return shutil.which("docker") is not None

    return False


# ── Command Wrapping ─────────────────────────────────────────────────────────


def wrap_command(cmd: str, profile: EnvProfile, strategy: EnvStrategy) -> str:
    """
    Transform a command according to the selected strategy.

    DIRECT:
      python test.py → .venv/bin/python test.py
      pip install flask → .venv/bin/pip install flask
      npm test → npm test (unchanged if no node_modules/.bin)

    RESOLVER:
      pip install flask → bash -c "source .venv/bin/activate && pip install flask"
      poetry projects: → poetry run pip install flask

    DOCKER:
      npm test → docker exec <container> npm test

    Args:
        cmd:      original command string
        profile:  detected environment profile
        strategy: selected execution strategy

    Returns:
        The wrapped command string.
    """
    if not cmd or not cmd.strip():
        return cmd

    if strategy == EnvStrategy.DIRECT:
        return _wrap_direct(cmd, profile)
    elif strategy == EnvStrategy.RESOLVER:
        return _wrap_resolver(cmd, profile)
    elif strategy == EnvStrategy.DOCKER:
        return _wrap_docker(cmd, profile)

    return cmd


def _wrap_direct(cmd: str, profile: EnvProfile) -> str:
    """Replace binary names with their environment-specific paths."""
    parts = cmd.split()
    if not parts:
        return cmd

    first = parts[0].rsplit("/", 1)[-1]  # Get base command name

    # Python binary replacement
    if first in PYTHON_BINARY_MAP and profile.python_bin:
        # For pipenv/poetry "run" prefixes, use the full prefix
        if profile.python_bin.startswith(("pipenv run", "poetry run")):
            prefix = profile.python_bin.rsplit(" ", 1)[0]  # "pipenv run" or "poetry run"
            return f"{prefix} {cmd}"
        else:
            # Direct path replacement (venv)
            bin_dir = str(Path(profile.python_bin).parent)
            actual_bin = bin_dir + "/" + first
            parts[0] = actual_bin
            return " ".join(parts)

    # Node binary replacement
    if first in NODE_BINARY_MAP and profile.npm_prefix:
        actual_bin = profile.npm_prefix + first
        if Path(actual_bin).exists():
            parts[0] = actual_bin
            return " ".join(parts)

    return cmd


def _wrap_resolver(cmd: str, profile: EnvProfile) -> str:
    """Wrap command with shell-based environment activation."""

    # For pipenv/poetry: use "pipenv run" / "poetry run" prefix
    if profile.env_type == "pipenv":
        return f"pipenv run {cmd}"
    elif profile.env_type == "poetry":
        return f"poetry run {cmd}"

    # For standard venv: wrap with activation
    if profile.shell_wrapper:
        if sys.platform == "win32" and profile.shell_wrapper.endswith("&&"):
            # Windows: cmd /c "activate.bat && command"
            escaped_cmd = cmd.replace('"', '\\"')
            return f'cmd /c "{profile.shell_wrapper} {escaped_cmd}"'
        elif "source" in profile.shell_wrapper:
            # Unix: bash -c "source activate && command"
            escaped_cmd = cmd.replace("'", "'\\''")
            return f"bash -c '{profile.shell_wrapper} && {escaped_cmd}'"

    # Fallback to direct if no resolver available
    return _wrap_direct(cmd, profile)


def _wrap_docker(cmd: str, profile: EnvProfile) -> str:
    """Wrap command for Docker execution."""

    # If docker-compose is available, prefer exec
    if "docker-compose" in profile.detected_envs and profile.docker_service:
        return f"docker-compose exec {profile.docker_service} {cmd}"

    # Use docker run with the detected image
    if profile.docker_image:
        return f"docker run --rm {profile.docker_image} {cmd}"

    # Fallback to resolver if Docker isn't fully configured
    return _wrap_resolver(cmd, profile)


# ── Convenience ──────────────────────────────────────────────────────────────


def get_env_summary(profile: EnvProfile, strategy: EnvStrategy) -> str:
    """Get a human-readable summary for logging."""
    envs = ", ".join(profile.detected_envs) if profile.detected_envs else "system"
    return f"env={profile.env_type} detected=[{envs}] strategy={strategy.value}"


def get_current_phase() -> str:
    """Read the current phase from config.json."""
    try:
        import json
        from adelie.config import ADELIE_ROOT
        config_path = ADELIE_ROOT / "config.json"
        if config_path.exists():
            data = json.loads(config_path.read_text(encoding="utf-8"))
            return data.get("phase", "initial")
    except Exception:
        pass
    return "initial"
