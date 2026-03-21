"""
adelie/agents/runner_ai.py

Runner AI — builds, runs, and deploys the project.

3-tier execution:
  Build  — install dependencies, compile (MID_1+)
  Run    — start dev server, run scripts (MID_1+)
  Deploy — docker, production deployment (MID_2+)

All commands go through a whitelist for security.
Process tracking for background servers.
Logs saved to .adelie/runner/.
"""

from __future__ import annotations

import json
import re
import shlex
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from rich.console import Console

from adelie.config import WORKSPACE_PATH, PROJECT_ROOT, SANDBOX_MODE
from adelie.llm_client import generate
from adelie.tool_registry import get_registry as get_tool_registry

console = Console()

RUNNER_ROOT = WORKSPACE_PATH.parent / "runner"
PROCESS_FILE = RUNNER_ROOT / "processes.json"

_IS_WINDOWS = sys.platform == "win32"

# Tiered command whitelist
BUILD_COMMANDS = [
    "npm", "npx", "pip", "pip3", "python", "python3",
    "yarn", "pnpm", "cargo", "go", "make", "mkdir", "cp", "mv",
]

RUN_COMMANDS = BUILD_COMMANDS + [
    "node", "uvicorn", "gunicorn", "flask", "fastapi",
    "next", "vite", "serve",
]

DEPLOY_COMMANDS = RUN_COMMANDS + [
    "docker", "docker-compose", "podman",
    "ssh", "scp", "rsync", "systemctl",
]

# Dangerous flags that can enable arbitrary code execution
BLOCKED_FLAGS = {"-c", "--eval", "eval", "exec", "--exec", "-e"}

# Dangerous shell metacharacters
BLOCKED_CHARS = {";", "|", "&&", "||", "`", "$(", ">>", "<<"}

EXEC_TIMEOUT_BUILD = 120
EXEC_TIMEOUT_RUN = 10  # Short timeout — we just check if it starts
EXEC_TIMEOUT_DEPLOY = 180


def _detect_available_tools() -> str:
    """Check which CLI tools are actually installed on this system."""
    tools_to_check = [
        "npm", "npx", "node", "yarn", "pnpm",
        "pip", "pip3", "python", "python3",
        "docker", "docker-compose", "podman",
        "cargo", "go", "make",
        "vite", "next",
    ]
    available = []
    unavailable = []
    for tool in tools_to_check:
        if shutil.which(tool):
            available.append(tool)
        else:
            unavailable.append(tool)

    lines = [f"Available: {', '.join(available)}"]
    if unavailable:
        lines.append(f"NOT INSTALLED (do NOT use): {', '.join(unavailable)}")
    return "\n".join(lines)


def _diagnose_build_error(stderr: str, stdout: str = "") -> list[dict]:
    """
    Parse build error output to extract actionable file/line/error information.

    Returns list of dicts: [{"file": ..., "line": ..., "error_type": ..., "message": ...}]
    """
    import re as _re
    diagnostics: list[dict] = []
    combined = (stderr + "\n" + stdout).strip()
    if not combined:
        return diagnostics

    # TypeScript / ESBuild errors: src/App.tsx(12,5): error TS2304: ...
    for m in _re.finditer(r'([^\s(]+\.\w+)\((\d+),\d+\):\s*error\s+(TS\d+):\s*(.+)', combined):
        diagnostics.append({
            "file": m.group(1), "line": int(m.group(2)),
            "error_type": m.group(3), "message": m.group(4).strip(),
        })

    # TypeScript alt: src/App.tsx:12:5 - error TS2304: ...
    for m in _re.finditer(r'([^\s:]+\.\w+):(\d+):\d+\s*-\s*error\s+(TS\d+):\s*(.+)', combined):
        diagnostics.append({
            "file": m.group(1), "line": int(m.group(2)),
            "error_type": m.group(3), "message": m.group(4).strip(),
        })

    # Python SyntaxError: File "x.py", line 12
    for m in _re.finditer(r'File "([^"]+)",\s*line\s*(\d+).*?(?:SyntaxError|IndentationError|NameError|ImportError|ModuleNotFoundError):\s*(.+)', combined, _re.DOTALL):
        diagnostics.append({
            "file": m.group(1), "line": int(m.group(2)),
            "error_type": "PythonError", "message": m.group(3).strip()[:200],
        })

    # Node/JS errors: ERROR in ./src/App.tsx 12:5
    for m in _re.finditer(r'ERROR\s+in\s+([^\s]+)\s+(\d+):\d+', combined):
        diagnostics.append({
            "file": m.group(1).lstrip("./"), "line": int(m.group(2)),
            "error_type": "BundleError", "message": "",
        })

    # npm ERR! / general errors — capture first 3 lines
    if not diagnostics:
        lines = [l.strip() for l in combined.splitlines() if l.strip() and not l.startswith(">")]
        error_lines = [l for l in lines if any(kw in l.lower() for kw in ["error", "failed", "cannot find", "not found"])]
        for line in error_lines[:3]:
            diagnostics.append({
                "file": "", "line": 0,
                "error_type": "BuildError", "message": line[:200],
            })

    return diagnostics[:10]  # Cap at 10

SYSTEM_PROMPT = """You are Runner AI — a DevOps engineer in an autonomous AI loop.

You receive the project's current source files and must generate commands to
build, run, or deploy the project.

Output a single valid JSON object:
{
  "build_commands": [
    {
      "command": "pip install -r requirements.txt",
      "description": "Install Python dependencies",
      "cwd": ".",
      "tier": "build"
    }
  ],
  "run_commands": [
    {
      "command": "python -m uvicorn main:app --port 8000",
      "description": "Start the backend API server",
      "cwd": ".",
      "tier": "run",
      "background": true
    }
  ],
  "deploy_commands": [
    {
      "command": "docker build -t myapp .",
      "description": "Build Docker image",
      "cwd": ".",
      "tier": "deploy"
    }
  ]
}

RULES:
- Only include commands relevant to the current project
- Set background=true for long-running servers
- Use relative paths for cwd
- Be specific about ports and configurations
- Check if dependencies are installed before running
- Separate build from run from deploy clearly
"""


def _is_allowed(cmd: str, tier: str) -> bool:
    """Check if command is safe and allowed for the given tier."""
    # Block shell metacharacters
    for meta in BLOCKED_CHARS:
        if meta in cmd:
            return False
    try:
        parts = shlex.split(cmd)
    except ValueError:
        return False
    if not parts:
        return False
    first_word = parts[0].rsplit("/", 1)[-1]
    # Block dangerous flags
    if any(flag in BLOCKED_FLAGS for flag in parts[1:]):
        return False
    if tier == "deploy":
        return first_word in DEPLOY_COMMANDS
    elif tier == "run":
        return first_word in RUN_COMMANDS
    return first_word in BUILD_COMMANDS


def _execute(cmd: str, cwd: Path, timeout: int, background: bool = False) -> dict:
    """Execute a command safely."""
    result = {
        "command": cmd,
        "returncode": -1,
        "stdout": "",
        "stderr": "",
        "timed_out": False,
        "pid": None,
    }

    try:
        if background:
            # Start and don't wait
            if _IS_WINDOWS:
                proc = subprocess.Popen(
                    cmd,
                    cwd=str(cwd),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    shell=True,
                )
            else:
                try:
                    parts = shlex.split(cmd)
                except ValueError:
                    result["stderr"] = "Malformed command"
                    return result
                proc = subprocess.Popen(
                    parts,
                    cwd=str(cwd),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
            result["pid"] = proc.pid
            result["returncode"] = 0
            result["stdout"] = f"Started background process (PID: {proc.pid})"
        else:
            if _IS_WINDOWS:
                proc = subprocess.run(
                    cmd,
                    cwd=str(cwd),
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    shell=True,
                )
            else:
                try:
                    parts = shlex.split(cmd)
                except ValueError:
                    result["stderr"] = "Malformed command"
                    return result
                proc = subprocess.run(
                    parts,
                    cwd=str(cwd),
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
            result["returncode"] = proc.returncode
            result["stdout"] = proc.stdout[-2000:]
            result["stderr"] = proc.stderr[-2000:]
    except subprocess.TimeoutExpired:
        result["timed_out"] = True
        result["stderr"] = f"Timed out after {timeout}s"
    except Exception as e:
        result["stderr"] = str(e)

    return result


def _extract_port(cmd: str) -> int | None:
    """Try to extract a port number from a command string."""
    import re
    # Match common port patterns: --port 8000, :8000, -p 3000
    patterns = [
        r'--port[= ]+(\d+)',
        r'-p[= ]+(\d+)',
        r':(\d{4,5})\b',
        r'localhost:(\d+)',
    ]
    for pat in patterns:
        match = re.search(pat, cmd)
        if match:
            port = int(match.group(1))
            if 1024 <= port <= 65535:
                return port
    return None


def _save_process(pid: int, cmd: str, description: str, port: int | None = None) -> None:
    """Track a background process with optional port info."""
    RUNNER_ROOT.mkdir(parents=True, exist_ok=True)
    processes = _load_processes()

    entry = {
        "pid": pid,
        "command": cmd,
        "description": description,
        "started": datetime.now().isoformat(timespec="seconds"),
    }
    # Auto-detect port from command if not provided
    detected_port = port or _extract_port(cmd)
    if detected_port:
        entry["port"] = detected_port
    processes.append(entry)
    PROCESS_FILE.write_text(json.dumps(processes, indent=2), encoding="utf-8")


def _load_processes() -> list[dict]:
    """Load tracked processes."""
    if PROCESS_FILE.exists():
        try:
            return json.loads(PROCESS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _cleanup_dead_processes() -> None:
    """Remove dead processes from tracking file."""
    if not PROCESS_FILE.exists():
        return
    import os
    processes = _load_processes()
    alive = []
    for proc in processes:
        pid = proc.get("pid")
        if pid:
            try:
                if sys.platform == "win32":
                    import ctypes
                    handle = ctypes.windll.kernel32.OpenProcess(0x00100000, 0, pid)
                    is_alive = bool(handle)
                    if handle:
                        ctypes.windll.kernel32.CloseHandle(handle)
                else:
                    os.kill(pid, 0)
                    is_alive = True
            except (ProcessLookupError, PermissionError, OSError):
                is_alive = False
            if is_alive:
                alive.append(proc)
    RUNNER_ROOT.mkdir(parents=True, exist_ok=True)
    PROCESS_FILE.write_text(json.dumps(alive, indent=2), encoding="utf-8")


def _is_similar_running(description: str) -> int | None:
    """Check if a process with similar description is already running."""
    import os
    processes = _load_processes()
    for proc in processes:
        if proc.get("description", "").lower() == description.lower():
            pid = proc.get("pid")
            if pid:
                try:
                    if sys.platform == "win32":
                        import ctypes
                        handle = ctypes.windll.kernel32.OpenProcess(0x00100000, 0, pid)
                        is_alive = bool(handle)
                        if handle:
                            ctypes.windll.kernel32.CloseHandle(handle)
                    else:
                        os.kill(pid, 0)
                        is_alive = True
                except (ProcessLookupError, PermissionError, OSError):
                    is_alive = False
                if is_alive:
                    return pid  # Still alive
    return None


def run_pipeline(
    source_files: list[dict],
    max_tier: str = "deploy",
    workspace_root: Path | None = None,
) -> dict:
    """
    Generate and execute build/run/deploy commands.

    Args:
        source_files: list of project files for context
        max_tier: "build", "run", or "deploy"
        workspace_root: project root

    Returns:
        Summary of execution results.
    """
    if workspace_root is None:
        workspace_root = PROJECT_ROOT

    console.print(f"[bold blue]🚀 Runner AI[/bold blue] — tier: {max_tier}")

    # ── Environment Strategy ──────────────────────────────────────────────
    from adelie.env_strategy import detect_env, select_strategy, wrap_command, get_env_summary, get_current_phase, ensure_env
    env_profile = detect_env(workspace_root)
    env_profile = ensure_env(env_profile, workspace_root)
    env_strategy = select_strategy(env_profile, phase=get_current_phase())
    console.print(f"  [dim]🌐 {get_env_summary(env_profile, env_strategy)}[/dim]")

    # ── Sandbox Mode ──────────────────────────────────────────────────────
    from adelie.sandbox import get_effective_mode, get_sandbox_summary, SandboxMode
    sandbox_mode = get_effective_mode(SANDBOX_MODE)
    if sandbox_mode != SandboxMode.NONE:
        console.print(f"  [dim]{get_sandbox_summary(sandbox_mode)}[/dim]")

    # Cleanup dead processes first
    _cleanup_dead_processes()

    # Read source files for context
    file_list = []
    for finfo in source_files:
        fp = finfo.get("filepath", "")
        full_path = workspace_root / fp
        if full_path.exists():
            try:
                content = full_path.read_text(encoding="utf-8")
                # Only include first 500 chars per file for context
                file_list.append(f"--- {fp} ---\n{content[:500]}")
            except Exception:
                file_list.append(f"--- {fp} ---")

    # Also check for common config files
    for config in ["package.json", "requirements.txt", "Dockerfile", "docker-compose.yml", "pyproject.toml"]:
        cfg_path = workspace_root / config
        if cfg_path.exists():
            try:
                content = cfg_path.read_text(encoding="utf-8")
                file_list.append(f"--- {config} ---\n{content[:500]}")
            except Exception:
                pass

    # Detect available tools on this system
    tools_info = _detect_available_tools()

    user_prompt = (
        f"## System Tools\n{tools_info}\n\n"
        f"CRITICAL: Only generate commands using tools listed as 'Available' above.\n"
        f"Do NOT generate commands for tools listed as 'NOT INSTALLED'.\n\n"
        f"## Project Files\n\n"
        + "\n\n".join(file_list[:20])
        + f"\n\n## Max Tier: {max_tier}\n"
        f"Generate build/run/deploy commands. Output a JSON object."
    )

    try:
        raw = generate(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.2,
        )
    except Exception as e:
        console.print(f"[red]❌ Runner AI LLM error: {e}[/red]")
        return {"executed": 0, "succeeded": 0, "failed": 0, "errors": []}

    # Parse
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                return {"executed": 0, "succeeded": 0, "failed": 0, "errors": []}
        else:
            return {"executed": 0, "succeeded": 0, "failed": 0, "errors": []}

    RUNNER_ROOT.mkdir(parents=True, exist_ok=True)

    tier_order = ["build", "run", "deploy"]
    max_idx = tier_order.index(max_tier) if max_tier in tier_order else 0

    executed = 0
    succeeded = 0
    failed = 0
    errors = []
    log_entries = []

    for tier in tier_order[:max_idx + 1]:
        commands = data.get(f"{tier}_commands", [])
        if not commands:
            continue

        console.print(f"\n  [bold]━━━ {tier.upper()} ━━━[/bold]")
        timeout = {
            "build": EXEC_TIMEOUT_BUILD,
            "run": EXEC_TIMEOUT_RUN,
            "deploy": EXEC_TIMEOUT_DEPLOY,
        }.get(tier, 60)

        for cmd_info in commands:
            cmd = cmd_info.get("command", "")
            desc = cmd_info.get("description", "")
            cwd_rel = cmd_info.get("cwd", ".")
            background = cmd_info.get("background", False)

            if not cmd:
                continue

            # Skip if same service already running (background)
            if background:
                existing_pid = _is_similar_running(desc)
                if existing_pid:
                    console.print(f"  [dim]⏭  {desc} already running (PID {existing_pid})[/dim]")
                    continue

            if not _is_allowed(cmd, tier):
                console.print(f"  [red]🚫 Blocked: {cmd}[/red]")
                continue

            # Wrap command with environment strategy
            cmd = wrap_command(cmd, env_profile, env_strategy)

            # Apply sandbox wrapping
            if sandbox_mode != SandboxMode.NONE:
                from adelie.sandbox import wrap_command as sandbox_wrap
                cmd = sandbox_wrap(cmd, sandbox_mode, workspace_root)

            cwd = workspace_root / cwd_rel
            console.print(f"  [blue]▶[/blue] {desc}: {cmd}")

            result = _execute(cmd, cwd, timeout, background)
            executed += 1

            if result["returncode"] == 0:
                succeeded += 1
                console.print(f"  [green]✅ OK[/green]")
                if result["pid"]:
                    _save_process(result["pid"], cmd, desc)
            else:
                failed += 1
                console.print(f"  [red]❌ Failed (rc={result['returncode']})[/red]")
                if result["stderr"]:
                    console.print(f"  [dim]{result['stderr'][:200]}[/dim]")
                errors.append({
                    "command": cmd,
                    "description": desc,
                    "tier": tier,
                    "stderr": result.get("stderr", "")[:500],
                    "stdout": result.get("stdout", "")[:500],
                    "returncode": result["returncode"],
                    "diagnostics": _diagnose_build_error(
                        result.get("stderr", ""), result.get("stdout", "")
                    ),
                })

            log_entries.append({
                "tier": tier,
                "command": cmd,
                "description": desc,
                "result": result,
            })

    # Save log
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = RUNNER_ROOT / f"{max_tier}_log_{ts}.md"

    report = (
        f"# Runner Log — {datetime.now().isoformat(timespec='seconds')}\n"
        f"**Tier**: {max_tier} | Executed: {executed} | "
        f"Succeeded: {succeeded} | Failed: {failed}\n\n"
    )
    for entry in log_entries:
        icon = "✅" if entry["result"]["returncode"] == 0 else "❌"
        report += (
            f"## {icon} [{entry['tier'].upper()}] {entry['description']}\n"
            f"- Command: `{entry['command']}`\n"
            f"- Return: {entry['result']['returncode']}\n"
        )
        # Include error output for failed commands
        if entry["result"]["returncode"] != 0:
            stderr = entry["result"].get("stderr", "")
            stdout = entry["result"].get("stdout", "")
            if stderr:
                report += f"- Stderr:\n```\n{stderr[:800]}\n```\n"
            if stdout:
                report += f"- Stdout:\n```\n{stdout[:400]}\n```\n"
        report += "\n"

    log_path.write_text(report, encoding="utf-8")

    console.print(
        f"[bold blue]🚀 Runner AI[/bold blue] — "
        f"{succeeded}/{executed} succeeded, {failed} failed"
    )

    return {"executed": executed, "succeeded": succeeded, "failed": failed, "errors": errors}
