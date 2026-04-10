"""
adelie/agents/coder_ai.py

Coder AI agent — generates actual source code files.

Each coder instance is identified by its layer (0/1/2) and name.
It receives a task, reads relevant context, generates code via the LLM,
writes source files to the workspace, and logs its work to
.adelie/coder/layer/{N}/{name}/log.md.

Layer hierarchy:
  Layer 0 — Feature coders (e.g., backend_login, frontend_login)
  Layer 1 — Connector/domain coders (e.g., backend, frontend)
            Can read Layer 0 logs.
  Layer 2 — Infrastructure coders (e.g., devops, deploy)
            Can read Layer 0 + Layer 1 logs.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from rich.console import Console

from adelie.config import WORKSPACE_PATH, PROJECT_ROOT
from adelie.llm_client import generate
from adelie.rules_loader import get_rules_prompt_section, get_context_prompt_section
from adelie.prompt_loader import load_prompt
from adelie.skill_manager import get_skills_prompt_section

console = Console()

# ── Coder workspace root ──────────────────────────────────────────────────────

CODER_ROOT = WORKSPACE_PATH.parent / "coder"
STAGING_ROOT = WORKSPACE_PATH.parent / "staging"

_FALLBACK_PROMPT = """You are Coder AI — a software engineer in an autonomous AI loop.
Output a single valid JSON array of files to create/update."""

SYSTEM_PROMPT = load_prompt("coder", _FALLBACK_PROMPT)


def _get_coder_log_dir(layer: int, coder_name: str) -> Path:
    """Get or create the log directory for a coder."""
    log_dir = CODER_ROOT / "layer" / str(layer) / coder_name
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def _read_lower_layer_logs(layer: int) -> str:
    """Read logs from all layers below the given layer."""
    if layer == 0:
        return ""

    logs = []
    for lower in range(0, layer):
        layer_dir = CODER_ROOT / "layer" / str(lower)
        if not layer_dir.exists():
            continue
        for coder_dir in sorted(layer_dir.iterdir()):
            if coder_dir.is_dir():
                log_file = coder_dir / "log.md"
                if log_file.exists():
                    content = log_file.read_text(encoding="utf-8")
                    logs.append(
                        f"--- Layer {lower} / {coder_dir.name} ---\n{content}"
                    )

    if not logs:
        return "\n(No lower layer logs available yet.)\n"
    return "\n\n".join(logs)


def _read_existing_files(workspace_root: Path, filepaths: list[str]) -> str:
    """Read existing source files from the workspace if they exist."""
    parts = []

    # Auto-include key config files if not already in the list
    key_configs = [
        "package.json", "tsconfig.json",
        "vite.config.ts", "vite.config.js",
        "next.config.js", "next.config.mjs", "next.config.ts",
        "nuxt.config.ts", "nuxt.config.js",
        "svelte.config.js", "remix.config.js", "angular.json",
        "index.html", "requirements.txt", "pyproject.toml",
    ]
    filepath_set = set(filepaths)
    for cfg in key_configs:
        if cfg not in filepath_set:
            cfg_path = workspace_root / cfg
            if cfg_path.exists():
                filepaths = list(filepaths) + [cfg]

    for fp in filepaths:
        full = workspace_root / fp
        if full.exists() and full.is_file():
            try:
                content = full.read_text(encoding="utf-8")
                parts.append(f"--- {fp} ---\n{content}")
            except Exception:
                pass
    if not parts:
        return "(No existing files found.)"
    return "\n\n".join(parts)


def run_coder(
    coder_name: str,
    layer: int,
    task: str,
    context: str,
    workspace_root: Path | None = None,
    relevant_files: list[str] | None = None,
    feedback: str | None = None,
) -> list[dict]:
    """
    Execute a single coder: generate code via LLM, write files, log work.

    Args:
        coder_name: identifier like "backend_login"
        layer: 0, 1, or 2
        task: description of what to build
        context: KB content (architecture, roadmap, etc.)
        workspace_root: project root (where src/ lives)
        relevant_files: list of existing file paths to provide as context

    Returns:
        List of dicts with written file info.
    """
    if workspace_root is None:
        workspace_root = PROJECT_ROOT

    console.print(
        f"[bold cyan]🔧 Coder [{layer}] {coder_name}[/bold cyan] — {task[:60]}..."
    )

    # Build user prompt with all context
    lower_logs = _read_lower_layer_logs(layer)
    existing = _read_existing_files(workspace_root, relevant_files or [])

    # Get project file tree for context
    try:
        from adelie.project_context import get_tree_summary
        project_tree = get_tree_summary()
    except Exception:
        project_tree = "(file tree unavailable)"

    # Get active policy constraints (if any)
    policy_section = ""
    try:
        from adelie.policy_engine import PolicyEngine
        engine = PolicyEngine()
        policy_section = engine.get_prompt_summary()
    except Exception:
        pass

    user_prompt = (
        f"## Task\n{task}\n\n"
        f"## Layer\nThis is a Layer {layer} coder.\n"
        f"- Layer 0: Feature-level (individual features)\n"
        f"- Layer 1: Domain-level (connects features into backend/frontend/etc)\n"
        f"- Layer 2: Infrastructure-level (deployment, CI/CD, project config)\n\n"
        f"## Project File Tree\n{project_tree}\n\n"
        f"{get_context_prompt_section()}"
        f"{get_rules_prompt_section()}"
        f"{get_skills_prompt_section('coder')}"
        f"{policy_section}"
        f"## KB Context\n{context}\n\n"
        f"## Existing Source Files\n{existing}\n\n"
        f"## Lower Layer Coder Logs\n{lower_logs}\n\n"
    )

    if feedback:
        user_prompt += (
            f"## ⚠️ REVIEWER FEEDBACK (FIX THESE ISSUES)\n{feedback}\n\n"
            f"The previous code was REJECTED. Fix ALL the issues above and regenerate the code.\n\n"
        )

    user_prompt += "Generate the source code files. Output a JSON array."

    # Call LLM with retry on JSON parse failure
    MAX_CODER_JSON_RETRIES = 1
    operations = None
    current_prompt = user_prompt

    for attempt in range(MAX_CODER_JSON_RETRIES + 1):
        try:
            raw = generate(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=current_prompt,
                temperature=0.2,
            )
        except Exception as e:
            console.print(f"[red]❌ Coder [{layer}] {coder_name} LLM error: {e}[/red]")
            return []

        # Parse response
        try:
            operations = json.loads(raw)
            if isinstance(operations, list):
                break
            else:
                console.print(
                    f"[yellow]⚠️  Coder [{layer}] {coder_name} — response is not a list (attempt {attempt + 1})[/yellow]"
                )
                operations = None
        except json.JSONDecodeError:
            # Try to extract JSON array from response
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            if match:
                try:
                    operations = json.loads(match.group())
                    if isinstance(operations, list):
                        break
                except json.JSONDecodeError:
                    pass

            if attempt < MAX_CODER_JSON_RETRIES:
                console.print(
                    f"[yellow]⚠️  Coder [{layer}] {coder_name} — invalid JSON (retry {attempt + 1})[/yellow]"
                )
                current_prompt = (
                    user_prompt
                    + "\n\n⚠️ PREVIOUS OUTPUT WAS NOT VALID JSON. "
                    "Output ONLY a raw JSON array — no markdown fences, no extra text. "
                    "The output must start with [ and end with ]."
                )
                continue

            console.print(
                f"[yellow]⚠️  Coder [{layer}] {coder_name} — JSON parse failed after retries[/yellow]"
            )
            return []

    if not operations or not isinstance(operations, list):
        return []

    # Write files
    written = []
    log_entries = []

    for op in operations:
        filepath = op.get("filepath", "").strip()
        content = op.get("content", "")
        description = op.get("description", "")
        language = op.get("language", "")

        if not filepath or not content:
            continue

        # Sanitize — prevent writing outside staging area
        # Check absolute paths and genuine parent-directory traversal.
        # Use Path.parts for segment-level check so bracket paths like
        # [..nextauth] or [...slug] (Next.js catch-all routes) are allowed.
        parts = Path(filepath).parts
        if filepath.startswith("/") or ".." in parts:
            console.print(
                f"[yellow]⚠️  Skipped unsafe path: {filepath}[/yellow]"
            )
            continue
        # Resolve-based check: ensure the final path is under STAGING_ROOT
        resolved_out = (STAGING_ROOT / filepath).resolve()
        if not str(resolved_out).startswith(str(STAGING_ROOT.resolve())):
            console.print(
                f"[yellow]⚠️  Skipped path escaping staging: {filepath}[/yellow]"
            )
            continue

        out_path = STAGING_ROOT / filepath
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")

        console.print(f"  [green]✓[/green] {filepath} ({language}) [staged]")
        written.append({
            "filepath": filepath,
            "language": language,
            "description": description,
            "staged": True,
        })
        log_entries.append(
            f"- `{filepath}` — {description}"
        )

    # Write coder log
    if written:
        log_dir = _get_coder_log_dir(layer, coder_name)
        log_file = log_dir / "log.md"

        ts = datetime.now().isoformat(timespec="seconds")
        new_entry = (
            f"\n## {ts}\n"
            f"**Task**: {task}\n\n"
            f"**Files written**:\n"
            + "\n".join(log_entries)
            + "\n"
        )

        # Append to existing log
        existing_log = ""
        if log_file.exists():
            existing_log = log_file.read_text(encoding="utf-8")

        if not existing_log:
            existing_log = f"# Coder Log: {coder_name} (Layer {layer})\n"

        log_file.write_text(
            existing_log + new_entry, encoding="utf-8"
        )

    console.print(
        f"[bold cyan]🔧 Coder [{layer}] {coder_name}[/bold cyan] — "
        f"{len(written)} file(s) written."
    )

    return written
