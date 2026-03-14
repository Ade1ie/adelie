"""
adelie/agents/coder_manager.py

Coder Manager — orchestrates multi-layer coder execution.

Receives coder_tasks from Expert AI and dispatches them to the
appropriate layer coders in order: Layer 0 → Layer 1 → Layer 2.

Manages the coder registry (.adelie/coder/registry.json) which
tracks all active coders and their status.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from rich.console import Console

from adelie.agents.coder_ai import run_coder, CODER_ROOT
from adelie.config import WORKSPACE_PATH, PROJECT_ROOT
from adelie.kb import retriever

console = Console()

REGISTRY_PATH = CODER_ROOT / "registry.json"


def _load_registry() -> dict:
    """Load or initialize the coder registry."""
    CODER_ROOT.mkdir(parents=True, exist_ok=True)
    if REGISTRY_PATH.exists():
        return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    return {"coders": [], "last_updated": None}


def _save_registry(registry: dict) -> None:
    """Persist the coder registry."""
    registry["last_updated"] = datetime.now().isoformat(timespec="seconds")
    REGISTRY_PATH.write_text(
        json.dumps(registry, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _get_kb_context() -> str:
    """Read key KB files to provide as context to coders."""
    categories = retriever.list_categories()
    context_parts = []

    # Read architecture, roadmap, tech_stack, implementation_plan
    important_keywords = [
        "architecture", "roadmap", "tech_stack", "vision",
        "implementation", "coding_standard",
    ]

    for cat_dir in WORKSPACE_PATH.iterdir():
        if not cat_dir.is_dir():
            continue
        for f in cat_dir.glob("*.md"):
            if any(kw in f.stem.lower() for kw in important_keywords):
                try:
                    content = f.read_text(encoding="utf-8")
                    rel = f.relative_to(WORKSPACE_PATH)
                    context_parts.append(f"--- {rel} ---\n{content}")
                except Exception:
                    pass

    if not context_parts:
        return "(KB is empty — no architecture or roadmap defined yet.)"

    # Add project file tree for context
    from adelie.project_context import get_tree_summary, get_key_configs
    context_parts.append(f"--- PROJECT FILE TREE ---\n{get_tree_summary()}")
    context_parts.append(f"--- KEY CONFIG FILES ---\n{get_key_configs()}")

    return "\n\n".join(context_parts)


def _register_coder(registry: dict, layer: int, name: str, task: str) -> None:
    """Add or update a coder in the registry."""
    # Check if already registered
    for coder in registry["coders"]:
        if coder["layer"] == layer and coder["name"] == name:
            coder["last_task"] = task
            coder["last_run"] = datetime.now().isoformat(timespec="seconds")
            return

    registry["coders"].append({
        "layer": layer,
        "name": name,
        "created": datetime.now().isoformat(timespec="seconds"),
        "last_task": task,
        "last_run": datetime.now().isoformat(timespec="seconds"),
    })


def _find_existing_files(workspace_root: Path) -> list[str]:
    """Find existing source code files in the workspace."""
    code_extensions = {
        ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css",
        ".json", ".yaml", ".yml", ".toml", ".sh", ".sql",
        ".svelte", ".vue", ".go", ".rs",
    }
    files = []
    for f in workspace_root.rglob("*"):
        if f.is_file() and f.suffix in code_extensions:
            # Skip hidden dirs, node_modules, .venv, __pycache__
            rel = f.relative_to(workspace_root).as_posix()
            if any(
                part.startswith(".") or part in ("node_modules", "__pycache__", ".venv")
                for part in rel.split("/")
            ):
                continue
            files.append(rel)
    return sorted(files)[:30]  # Cap at 30 files to avoid context overflow


def run_coders(
    coder_tasks: list[dict],
    max_active_layer: int = 2,
) -> dict:
    """
    Execute coder tasks organized by layer.

    Args:
        coder_tasks: list from Expert AI, each with:
            - layer: 0, 1, or 2
            - name: coder identifier
            - task: what to build
            - files: optional list of relevant existing files
        max_active_layer: highest layer to activate (phase-dependent)

    Returns:
        Summary dict of all coder results.
    """
    if not coder_tasks:
        return {"total_files": 0, "coders_run": 0}

    # In INITIAL phase (max_active_layer=-1), coders should not run
    if max_active_layer < 0:
        console.print("[dim]⏭  Coders disabled in current phase — skipping all tasks.[/dim]")
        return {"total_files": 0, "coders_run": 0}

    registry = _load_registry()
    kb_context = _get_kb_context()
    workspace_root = PROJECT_ROOT

    # Group tasks by layer
    by_layer: dict[int, list[dict]] = {0: [], 1: [], 2: []}
    for task in coder_tasks:
        layer = task.get("layer", 0)
        if layer > max_active_layer:
            # Auto-downgrade instead of skipping — the work is still valuable
            original_layer = layer
            layer = max_active_layer
            task["layer"] = layer
            console.print(
                f"[yellow]⬇️  Downgraded '{task.get('name', '?')}' from Layer {original_layer} "
                f"→ Layer {layer} (max active in current phase)[/yellow]"
            )
        by_layer.setdefault(layer, []).append(task)

    total_files = 0
    coders_run = 0

    # Execute layer by layer: 0 → 1 → 2
    for layer_num in sorted(by_layer.keys()):
        tasks = by_layer[layer_num]
        if not tasks:
            continue

        console.print(f"\n[bold]━━━ Layer {layer_num} Coders ━━━[/bold]")

        for task_info in tasks:
            name = task_info.get("name", "unnamed")
            task_desc = task_info.get("task", "")
            relevant = task_info.get("files", [])
            task_feedback = task_info.get("feedback")

            if not task_desc:
                continue

            # Find existing project files for context
            if not relevant:
                relevant = _find_existing_files(workspace_root)

            # Run the coder
            results = run_coder(
                coder_name=name,
                layer=layer_num,
                task=task_desc,
                context=kb_context,
                workspace_root=workspace_root,
                relevant_files=relevant,
                feedback=task_feedback,
            )

            _register_coder(registry, layer_num, name, task_desc)
            total_files += len(results)
            coders_run += 1

    _save_registry(registry)

    summary = {
        "total_files": total_files,
        "coders_run": coders_run,
    }

    if total_files > 0:
        console.print(
            f"\n[bold green]✅ Coders done — {total_files} file(s) "
            f"by {coders_run} coder(s)[/bold green]"
        )
    else:
        console.print("[dim]No code files generated this cycle.[/dim]")

    return summary
