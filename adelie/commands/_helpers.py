"""
adelie/commands/_helpers.py

Shared workspace-detection helpers and low-level utilities used by
all CLI command modules.  Previously lived in adelie/cli.py.
"""

from __future__ import annotations

import json
import os
import platform
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console

from adelie.i18n import t

console = Console()


# ── Workspace detection ───────────────────────────────────────────────────────

def _find_workspace_root() -> Path:
    """Find the nearest .adelie/ directory by walking up from cwd."""
    cwd = Path(os.environ.get("ADELIE_CWD", os.getcwd())).resolve()
    current = cwd
    while current != current.parent:
        if (current / ".adelie").is_dir():
            return current / ".adelie"
        current = current.parent
    return cwd / ".adelie"


def _workspace_config_path() -> Path:
    return _find_workspace_root() / "config.json"


def _load_workspace_config() -> dict:
    config_path = _workspace_config_path()
    if config_path.exists():
        try:
            return json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def _save_workspace_config(config: dict) -> None:
    config_path = _workspace_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")


def _update_env_file(updates: dict) -> None:
    """Update key=value pairs in .adelie/.env file."""
    ws_root = _find_workspace_root()
    env_path = ws_root / ".env"
    if not env_path.exists():
        lines = []
    else:
        lines = env_path.read_text(encoding="utf-8").splitlines()

    for key, value in updates.items():
        found = False
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith(f"{key}=") or stripped.startswith(f"# {key}="):
                lines[i] = f"{key}={value}"
                found = True
                break
        if not found:
            lines.append(f"{key}={value}")

    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _setup_env_from_workspace():
    """Apply workspace config.json values as environment variables."""
    ws_config = _load_workspace_config()
    env_map = {
        "loop_interval": "LOOP_INTERVAL_SECONDS",
    }
    for key, env_key in env_map.items():
        if key in ws_config and not os.environ.get(env_key):
            os.environ[env_key] = str(ws_config[key])

    ws_root = _find_workspace_root()
    if ws_root.exists():
        os.environ.setdefault("WORKSPACE_PATH", str(ws_root / "workspace"))

    env_file = ws_root / ".env"
    if not env_file.exists():
        project_root = ws_root.parent if ws_root.name == ".adelie" else ws_root
        env_file = project_root / ".env"
    if env_file.exists():
        load_dotenv(env_file)


def _ensure_adelie_config():
    _setup_env_from_workspace()
    import importlib
    import adelie.config as cfg
    importlib.reload(cfg)


def _validate_provider() -> None:
    _ensure_adelie_config()
    import adelie.config as cfg

    if cfg.LLM_PROVIDER == "gemini":
        if not cfg.GEMINI_API_KEY:
            console.print(
                "[bold red]ERROR: GEMINI_API_KEY is not set.[/bold red]\n"
                "Set it with: [bold]adelie config --api-key YOUR_KEY[/bold]\n"
                "Or switch to Ollama: [bold]adelie config --provider ollama[/bold]"
            )
            sys.exit(1)
    elif cfg.LLM_PROVIDER == "ollama":
        import requests
        try:
            requests.get(f"{cfg.OLLAMA_BASE_URL}/api/tags", timeout=3).raise_for_status()
        except Exception:
            console.print(
                f"[bold red]ERROR: Cannot connect to Ollama at {cfg.OLLAMA_BASE_URL}[/bold red]\n"
                "Start Ollama with: [bold]ollama serve[/bold]"
            )
            sys.exit(1)


# ── OS Detection ──────────────────────────────────────────────────────────────

def _detect_os() -> dict:
    """Detect the current OS, shell, and architecture."""
    system = platform.system()
    release = platform.release()
    machine = platform.machine()
    version = platform.version()

    if system == "Windows":
        shell = "PowerShell"
        comspec = os.environ.get("COMSPEC", "")
        if os.environ.get("PSModulePath"):
            shell = "PowerShell"
        elif "cmd.exe" in comspec.lower():
            shell = "cmd"
    else:
        shell_path = os.environ.get("SHELL", "/bin/sh")
        shell = Path(shell_path).name

    if system == "Darwin":
        os_name = "macOS"
        try:
            mac_ver = platform.mac_ver()[0]
            if mac_ver:
                release = mac_ver
        except Exception:
            pass
    elif system == "Windows":
        os_name = "Windows"
    else:
        os_name = "Linux"
        try:
            import distro  # type: ignore
            os_name = f"Linux ({distro.name(pretty=True)})"
        except ImportError:
            try:
                osrel = Path("/etc/os-release").read_text()
                for line in osrel.splitlines():
                    if line.startswith("PRETTY_NAME="):
                        pretty = line.split("=", 1)[1].strip('"')
                        os_name = f"Linux ({pretty})"
                        break
            except Exception:
                pass

    return {
        "system": system,
        "os_name": os_name,
        "release": release,
        "machine": machine,
        "version": version,
        "shell": shell,
    }


def _generate_os_context(os_info: dict) -> str:
    """Generate English OS-specific context markdown for AI agent prompts."""
    system = os_info["system"]
    os_name = os_info["os_name"]
    release = os_info["release"]
    machine = os_info["machine"]
    shell = os_info["shell"]

    header = (
        f"## System Environment\n\n"
        f"- **OS**: {os_name} {release} / {machine}\n"
        f"- **Shell**: {shell}\n"
    )

    if system == "Windows":
        return header + (
            "- **Path separator**: `\\` (backslash)\n"
            "- **Line ending**: CRLF\n\n"
            "### Command Reference (use ONLY these for this OS)\n\n"
            "| Task | Command |\n"
            "|------|---------||\n"
            "| Delete file | `Remove-Item -Force <path>` |\n"
            "| Delete directory | `Remove-Item -Recurse -Force <path>` |\n"
            "| Copy file | `Copy-Item <src> <dst>` |\n"
            "| Move file | `Move-Item <src> <dst>` |\n"
            "| List files | `Get-ChildItem` or `ls` |\n"
            '| Set env variable | `$env:VAR = "value"` |\n'
            "| Chain commands | `cmd1; cmd2` (PowerShell) |\n"
            "| Run script | `.\\script.ps1` |\n"
            "| Null device | `$null` or `NUL` |\n\n"
            "### Docker on Windows\n"
            '- Use PowerShell-style volume mounts: `-v "${PWD}:/app"`\n'
            "- Container shell: use `/bin/sh` (NOT `/bin/bash` unless confirmed)\n"
            "- Line endings: ensure Dockerfiles use LF, not CRLF\n"
            "- Docker Desktop required (or WSL2 backend)\n\n"
            "### Testing & Build\n"
            "- Use `npx` or `npm run` for Node.js scripts\n"
            "- Python: `python` (not `python3`)\n"
            "- pytest: `python -m pytest`\n"
            "- Avoid `&&` for chaining — use `;` in PowerShell\n"
        )
    elif system == "Darwin":
        silicon_note = ""
        if machine == "arm64":
            silicon_note = (
                "- On Apple Silicon (arm64): be aware of `--platform linux/amd64` for x86 images\n"
                "- Homebrew packages are at `/opt/homebrew/`\n"
            )
        else:
            silicon_note = "- Homebrew packages are at `/usr/local/`\n"

        return header + (
            "- **Path separator**: `/` (forward slash)\n"
            "- **Line ending**: LF\n\n"
            "### Command Reference (use ONLY these for this OS)\n\n"
            "| Task | Command |\n"
            "|------|---------||\n"
            "| Delete file | `rm -f <path>` |\n"
            "| Delete directory | `rm -rf <path>` |\n"
            "| Copy file | `cp <src> <dst>` |\n"
            "| Move file | `mv <src> <dst>` |\n"
            "| List files | `ls -la` |\n"
            '| Set env variable | `export VAR="value"` |\n'
            "| Chain commands | `cmd1 && cmd2` |\n"
            "| Run script | `bash script.sh` or `./script.sh` |\n"
            "| Null device | `/dev/null` |\n\n"
            "### Docker on macOS\n"
            '- Volume mounts: `-v "$(pwd):/app"`\n'
            "- Container shell: `/bin/bash` or `/bin/sh`\n"
            "- Docker Desktop for Mac required\n"
            f"{silicon_note}\n"
            "### Testing & Build\n"
            "- Python: `python3` (not `python`)\n"
            "- pytest: `python3 -m pytest`\n"
            "- Use `&&` for command chaining\n"
        )
    else:  # Linux
        return header + (
            "- **Path separator**: `/` (forward slash)\n"
            "- **Line ending**: LF\n\n"
            "### Command Reference (use ONLY these for this OS)\n\n"
            "| Task | Command |\n"
            "|------|---------||\n"
            "| Delete file | `rm -f <path>` |\n"
            "| Delete directory | `rm -rf <path>` |\n"
            "| Copy file | `cp <src> <dst>` |\n"
            "| Move file | `mv <src> <dst>` |\n"
            "| List files | `ls -la` |\n"
            '| Set env variable | `export VAR="value"` |\n'
            "| Chain commands | `cmd1 && cmd2` |\n"
            "| Run script | `bash script.sh` or `./script.sh` |\n"
            "| Null device | `/dev/null` |\n\n"
            "### Docker on Linux\n"
            '- Volume mounts: `-v "$(pwd):/app"`\n'
            "- Container shell: `/bin/bash` or `/bin/sh`\n"
            "- May need `sudo` for Docker commands (unless user is in docker group)\n"
            "- Native Docker Engine — no Docker Desktop needed\n\n"
            "### Testing & Build\n"
            "- Python: `python3` (not `python` on most distros)\n"
            "- pytest: `python3 -m pytest`\n"
            "- Use `&&` for command chaining\n"
        )


# ── Auto Goal Generation ──────────────────────────────────────────────────────

def _auto_generate_goal() -> str | None:
    """
    Auto-generate project Main Goal from spec files + project structure.
    Returns the generated goal summary, or None if no specs found.
    """
    import adelie.config as cfg
    from adelie.kb import retriever

    ws_root = _find_workspace_root()
    specs_dir = ws_root / "specs"
    goal_path = cfg.WORKSPACE_PATH / "logic" / "project_goal.md"

    if goal_path.exists():
        content = goal_path.read_text(encoding="utf-8")
        for line in content.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("**") and not line.startswith("<!--"):
                return line[:200]
        return "Project goal defined (see project_goal.md)"

    spec_contents = ""
    if specs_dir.exists():
        for f in sorted(specs_dir.iterdir()):
            if f.is_file() and not f.name.startswith(".") and f.suffix in (".md", ".txt", ".pdf", ".docx"):
                try:
                    text = f.read_text(encoding="utf-8")
                    spec_contents += f"\n### {f.name}\n{text[:3000]}\n"
                except Exception:
                    pass

    if not spec_contents.strip():
        return None

    from adelie.project_context import get_tree_summary
    file_tree = get_tree_summary()

    kb_summary = ""
    try:
        retriever.ensure_workspace()
        kb_summary = retriever.get_index_summary()
    except Exception:
        pass

    prompt = f"""You are analyzing a software project to create a comprehensive project roadmap.
Your output will be used as the "Main Goal" document that guides ALL AI agents working on this project.

## Spec Files (provided by user)
{spec_contents}

## Project Structure
{file_tree}

{f"## Existing Knowledge Base{chr(10)}{kb_summary}" if kb_summary else ""}

Based on the above, create a structured project roadmap in markdown.
The document should include:

1. **Vision** — One paragraph summary of what this project aims to achieve
2. **Objectives** — Numbered list of major objectives with measurable criteria
3. **Technical Requirements** — Technologies, frameworks, architecture decisions
4. **Milestones** — Phased delivery plan
5. **Constraints & Notes** — Any important constraints or considerations

Be thorough and specific — this document guides ALL AI agents.
Output ONLY the markdown content, no extra commentary."""

    console.print("[bold cyan]🎯 Auto-generating Main Goal from spec files...[/bold cyan]")

    try:
        from adelie.llm_client import generate
        result = generate(
            system_prompt="You are a project planning expert. Analyze the given specs and project structure to create a clear, actionable project roadmap.",
            user_prompt=prompt,
            temperature=0.3,
        )

        goal_path.parent.mkdir(parents=True, exist_ok=True)
        header = (
            f"<!-- auto-generated from specs at {datetime.now().isoformat(timespec='seconds')} -->\n"
            f"<!-- regenerate with: adelie goal reset -->\n\n"
        )
        goal_path.write_text(header + result, encoding="utf-8")

        retriever.update_index(
            "logic/project_goal.md",
            tags=["goal", "project", "roadmap", "priority"],
            summary="Auto-generated project Main Goal from spec files",
        )

        console.print("[green]  ✓ Main Goal generated → project_goal.md[/green]")

        first_line = ""
        for line in result.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                first_line = line[:120]
                break
        return first_line or "Project goal auto-generated from specs"

    except Exception as e:
        console.print(f"[yellow]⚠️  Auto goal generation failed: {e}[/yellow]")
        console.print("[dim]   Continuing without Main Goal — set manually with: adelie goal set \"...\"[/dim]")
        return None
