"""
adelie/agents/scanner_ai.py

Scanner AI — reads existing source code and generates KB documentation.

When Adelie is initialized on an existing project, Scanner AI:
1. Scans the project directory tree
2. Reads source files and config files
3. Uses LLM to analyze the codebase
4. Generates KB documents: architecture, tech stack, code map, dependencies

This runs automatically on first `adelie run` when KB is empty,
or manually via `adelie scan`.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from rich.console import Console

from adelie.config import WORKSPACE_PATH, KB_CATEGORIES
from adelie.kb import retriever
from adelie.llm_client import generate

console = Console()

# File extensions to scan
CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".svelte", ".vue",
    ".go", ".rs", ".java", ".rb", ".php", ".css", ".scss",
    ".html", ".sql",
}

CONFIG_FILES = [
    "package.json", "requirements.txt", "pyproject.toml", "setup.py",
    "Cargo.toml", "go.mod", "pom.xml", "build.gradle", "Gemfile",
    "composer.json", "tsconfig.json", "vite.config.ts", "vite.config.js",
    "next.config.js", "next.config.ts", "webpack.config.js",
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
    ".env.example", "Makefile", "Procfile",
    "tailwind.config.js", "postcss.config.js",
]

SKIP_DIRS = {
    "node_modules", "__pycache__", ".venv", "venv", ".git",
    ".adelie", "dist", "build", ".next", ".nuxt", "target",
    "coverage", ".cache", ".tox", "egg-info",
}

# Max chars per file to include in prompt (to avoid token overflow)
MAX_CHARS_PER_FILE = 800
MAX_FILES_TO_SCAN = 40

SYSTEM_PROMPT = """You are Scanner AI — a code analyst in an autonomous AI loop.

You receive a snapshot of an EXISTING project's source code and configuration.
Your job is to analyze this codebase and produce comprehensive documentation.

Output a single valid JSON array, where each element is a KB document:
[
  {
    "category": "skills",
    "filename": "architecture.md",
    "tags": ["architecture", "design"],
    "summary": "System architecture overview",
    "content": "# Architecture\\n\\n## Overview\\n..."
  },
  {
    "category": "skills",
    "filename": "project_vision.md",
    "tags": ["vision", "product"],
    "summary": "Project goals and target users",
    "content": "# Project Vision\\n..."
  }
]

You MUST generate these documents:
1. **skills/project_vision.md** — What the project does, target users, key features (inferred from code)
2. **skills/architecture.md** — System design, module structure, data flow
3. **skills/code_map.md** — Directory structure explanation, key files and their roles
4. **dependencies/tech_stack.md** — Languages, frameworks, libraries with versions
5. **logic/existing_features.md** — List of implemented features (inferred from routes, components, etc.)
6. **exports/roadmap.md** — Suggested improvements and next steps based on code analysis

RULES:
- Analyze the ACTUAL code — don't guess or invent features not in the code
- Be specific: mention file paths, function names, component names
- Write in clear, structured markdown
- Include code snippets where helpful
- Note any issues, TODOs, or technical debt you spot
- category must be one of: skills, dependencies, errors, logic, exports, maintenance
"""


def _scan_project(project_root: Path) -> dict:
    """
    Scan project directory and collect source files.

    Returns:
        Dict with 'tree' (directory listing), 'files' (content), 'configs' (config content).
    """
    tree_lines = []
    source_files = []
    config_content = []

    # Collect directory tree
    for item in sorted(project_root.rglob("*")):
        rel = item.relative_to(project_root)
        # Skip hidden/ignored dirs
        if any(part in SKIP_DIRS or part.startswith(".") for part in rel.parts):
            continue
        depth = len(rel.parts) - 1
        if depth > 4:  # Max depth
            continue
        prefix = "  " * depth
        if item.is_dir():
            tree_lines.append(f"{prefix}{item.name}/")
        elif item.suffix in CODE_EXTENSIONS:
            size = item.stat().st_size
            tree_lines.append(f"{prefix}{item.name} ({size}B)")

    # Read config files
    for cfg_name in CONFIG_FILES:
        cfg_path = project_root / cfg_name
        if cfg_path.exists():
            try:
                content = cfg_path.read_text(encoding="utf-8")[:1500]
                config_content.append(f"--- {cfg_name} ---\n{content}")
            except Exception:
                pass

    # Read source files (prioritize key files)
    all_code_files = []
    for item in sorted(project_root.rglob("*")):
        rel = item.relative_to(project_root)
        if any(part in SKIP_DIRS or part.startswith(".") for part in rel.parts):
            continue
        if item.is_file() and item.suffix in CODE_EXTENSIONS:
            all_code_files.append((rel, item))

    # Prioritize: entry points, routes, models, components, tests
    priority_keywords = [
        "main", "app", "index", "server", "route", "api",
        "model", "schema", "auth", "config", "component",
        "page", "layout", "store", "util", "helper",
    ]

    def priority_score(rel_path: Path) -> int:
        name = rel_path.stem.lower()
        for i, kw in enumerate(priority_keywords):
            if kw in name:
                return i
        return 100

    all_code_files.sort(key=lambda x: priority_score(x[0]))

    for rel, full_path in all_code_files[:MAX_FILES_TO_SCAN]:
        try:
            content = full_path.read_text(encoding="utf-8")[:MAX_CHARS_PER_FILE]
            source_files.append(f"--- {rel} ---\n{content}")
        except Exception:
            pass

    return {
        "tree": "\n".join(tree_lines[:100]),
        "files": source_files,
        "configs": config_content,
        "total_files": len(all_code_files),
    }


def run_scan(
    project_root: Path | None = None,
    workspace_path: Path | None = None,
) -> list[dict]:
    """
    Scan existing project and generate KB documentation.

    Args:
        project_root: root of the existing project
        workspace_path: KB workspace path for writing files

    Returns:
        List of written KB files.
    """
    if project_root is None:
        project_root = WORKSPACE_PATH.parent
    if workspace_path is None:
        workspace_path = WORKSPACE_PATH

    console.print("[bold cyan]🔍 Scanner AI[/bold cyan] — analyzing existing codebase...")
    console.print(f"   [dim]Project: {project_root}[/dim]")

    # Scan the project
    scan = _scan_project(project_root)

    if not scan["files"] and not scan["configs"]:
        console.print("[yellow]  No source files found to analyze.[/yellow]")
        return []

    console.print(f"  Found {scan['total_files']} source file(s), scanning top {min(scan['total_files'], MAX_FILES_TO_SCAN)}...")

    # Build prompt
    user_prompt = (
        f"## Project Directory Tree\n```\n{scan['tree']}\n```\n\n"
        f"## Configuration Files\n\n"
        + "\n\n".join(scan["configs"])
        + f"\n\n## Source Code Files ({len(scan['files'])} files)\n\n"
        + "\n\n".join(scan["files"])
        + "\n\nAnalyze this codebase and generate KB documents. Output a JSON array."
    )

    try:
        raw = generate(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.3,
        )
    except Exception as e:
        console.print(f"[red]❌ Scanner AI LLM error: {e}[/red]")
        return []

    # Parse response
    try:
        documents = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if match:
            try:
                documents = json.loads(match.group())
            except json.JSONDecodeError:
                console.print("[yellow]⚠️  Scanner AI — invalid JSON response[/yellow]")
                return []
        else:
            console.print("[yellow]⚠️  Scanner AI — no JSON array found[/yellow]")
            return []

    if not isinstance(documents, list):
        return []

    # Write KB files
    written = []
    retriever.ensure_workspace()

    for doc in documents:
        category = doc.get("category", "skills")
        filename = doc.get("filename", "")
        tags = doc.get("tags", [])
        summary = doc.get("summary", "")
        content = doc.get("content", "")

        if not filename or not content:
            continue

        if category not in KB_CATEGORIES:
            category = "skills"

        rel_path = f"{category}/{filename}"
        full_path = workspace_path / category / filename

        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")

        retriever.update_index(rel_path, tags, summary)

        console.print(f"  [green]✓[/green] {rel_path}")
        written.append({"path": rel_path, "summary": summary})

    console.print(
        f"[bold cyan]🔍 Scanner AI[/bold cyan] — "
        f"generated {len(written)} KB document(s) from existing code."
    )

    # Auto-assign coders based on project structure
    coders = auto_assign_coders(project_root)
    if coders:
        console.print(
            f"[bold cyan]🔍 Scanner AI[/bold cyan] — "
            f"assigned {len(coders)} coder(s) from existing code."
        )

    return written


def auto_assign_coders(project_root: Path) -> list[dict]:
    """
    Analyze project structure and auto-register coders for existing code.

    Scans the directory structure and creates coder log entries
    so the coder system knows what already exists.
    """
    from adelie.agents.coder_ai import _get_coder_log_dir

    coders_registered = []

    # Group files by top-level directory → Layer 1 (domain) coders
    domain_files: dict[str, list[str]] = {}
    feature_files: dict[str, list[str]] = {}

    for item in sorted(project_root.rglob("*")):
        rel = item.relative_to(project_root)
        if any(part in SKIP_DIRS or part.startswith(".") for part in rel.parts):
            continue
        if not item.is_file() or item.suffix not in CODE_EXTENSIONS:
            continue

        parts = rel.parts
        if len(parts) < 2:
            continue

        # Layer 1: top-level dirs → domain coders (backend, frontend, src, etc.)
        domain = parts[0]
        domain_files.setdefault(domain, []).append(str(rel))

        # Layer 0: feature-level detection from deeper dirs
        if len(parts) >= 3:
            feature_key = f"{parts[0]}_{parts[1]}"
            feature_files.setdefault(feature_key, []).append(str(rel))

    # Register Layer 1 (domain) coders
    for domain, files in domain_files.items():
        if len(files) < 1:
            continue
        coder_name = _sanitize_coder_name(domain)
        log_dir = _get_coder_log_dir(1, coder_name)
        log_file = log_dir / "log.md"

        ts = datetime.now().isoformat(timespec="seconds")
        log_content = (
            f"# Coder Log: {coder_name} (Layer 1)\n\n"
            f"## {ts} — Initial scan\n"
            f"**Task**: Auto-assigned from existing project scan\n\n"
            f"**Existing files** ({len(files)}):\n"
            + "\n".join(f"- `{f}`" for f in files[:20])
            + ("\n- ... and more" if len(files) > 20 else "")
            + "\n"
        )
        log_file.write_text(log_content, encoding="utf-8")
        coders_registered.append({"layer": 1, "name": coder_name, "files": len(files)})
        console.print(f"  [green]✓[/green] Layer 1 coder: {coder_name} ({len(files)} files)")

    # Register Layer 0 (feature) coders for significant feature dirs
    for feature, files in feature_files.items():
        if len(files) < 2:  # Only register if 2+ files
            continue
        coder_name = _sanitize_coder_name(feature)
        log_dir = _get_coder_log_dir(0, coder_name)
        log_file = log_dir / "log.md"

        ts = datetime.now().isoformat(timespec="seconds")
        log_content = (
            f"# Coder Log: {coder_name} (Layer 0)\n\n"
            f"## {ts} — Initial scan\n"
            f"**Task**: Auto-assigned from existing project scan\n\n"
            f"**Existing files** ({len(files)}):\n"
            + "\n".join(f"- `{f}`" for f in files[:15])
            + "\n"
        )
        log_file.write_text(log_content, encoding="utf-8")
        coders_registered.append({"layer": 0, "name": coder_name, "files": len(files)})
        console.print(f"  [green]✓[/green] Layer 0 coder: {coder_name} ({len(files)} files)")

    # Register coders in registry
    if coders_registered:
        from adelie.agents.coder_manager import _load_registry, _save_registry, _register_coder
        registry = _load_registry()
        for c in coders_registered:
            _register_coder(registry, c["layer"], c["name"], "Auto-assigned from project scan")
        _save_registry(registry)

    return coders_registered


def _sanitize_coder_name(name: str) -> str:
    """Convert a directory name into a valid coder name."""
    return re.sub(r"[^a-zA-Z0-9_]", "_", name.lower()).strip("_")
