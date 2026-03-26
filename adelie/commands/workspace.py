"""
adelie/commands/workspace.py

Commands: adelie init, adelie ws
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table

from adelie.commands._helpers import (
    _find_workspace_root,
    _load_workspace_config,
    _save_workspace_config,
    _detect_os,
    _generate_os_context,
)
from adelie.i18n import t

console = Console()


def _detect_project(target: Path) -> dict:
    """Detect existing project type, languages, and frameworks."""
    info: dict = {"is_existing": False, "has_code": False, "languages": [], "frameworks": [], "name": target.name}

    markers = {
        "package.json": ("javascript", "Node.js"),
        "requirements.txt": ("python", None),
        "pyproject.toml": ("python", None),
        "setup.py": ("python", None),
        "Cargo.toml": ("rust", None),
        "go.mod": ("go", None),
        "pom.xml": ("java", "Maven"),
        "build.gradle": ("java", "Gradle"),
        "Gemfile": ("ruby", "Rails"),
        "composer.json": ("php", "Laravel"),
    }

    for marker, (lang, framework) in markers.items():
        if (target / marker).exists():
            info["is_existing"] = True
            if lang not in info["languages"]:
                info["languages"].append(lang)
            if framework and framework not in info["frameworks"]:
                info["frameworks"].append(framework)

    pkg_json = target / "package.json"
    if pkg_json.exists():
        try:
            pkg = json.loads(pkg_json.read_text(encoding="utf-8"))
            info["name"] = pkg.get("name", info["name"])
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            fw_map = {
                "next": "Next.js", "react": "React", "vue": "Vue",
                "svelte": "Svelte", "express": "Express", "fastify": "Fastify",
                "nuxt": "Nuxt", "angular": "Angular",
            }
            for dep, fw in fw_map.items():
                if dep in deps and fw not in info["frameworks"]:
                    info["frameworks"].append(fw)
        except Exception:
            pass

    if (target / ".git").exists():
        info["is_existing"] = True

    code_extensions = {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java", ".rb", ".php", ".svelte", ".vue"}
    for ext in code_extensions:
        if list(target.rglob(f"*{ext}"))[:1]:
            info["has_code"] = True
            break

    return info


def cmd_init(args) -> None:
    """Initialize a new Adelie workspace."""
    from adelie import registry

    # Resolve relative to user's actual CWD (ADELIE_CWD), not the Python process
    # cwd (which is set to PKG_ROOT so that 'from adelie import ...' works).
    import os
    user_cwd = Path(os.environ.get("ADELIE_CWD", os.getcwd())).resolve()
    raw_dir = args.directory if args.directory != "." else str(user_cwd)
    target = (user_cwd / raw_dir).resolve() if not Path(raw_dir).is_absolute() else Path(raw_dir).resolve()

    adelie_dir = target / ".adelie"

    if adelie_dir.exists() and not args.force:
        console.print(f"[yellow]WARN: {t('init.already_exists')} — {target}[/yellow]")
        console.print(f"[dim]   {t('init.use_force')}[/dim]")
        return

    console.print(f"[bold cyan]{t('init.title')}[/bold cyan]")
    console.print(f"   [dim]{t('init.dir')}: {target}[/dim]")

    project_info = _detect_project(target)
    if project_info["is_existing"]:
        console.print(f"[green]  +[/green] {t('init.detected')}")
        if project_info.get("name"):
            console.print(f"    {t('init.name')}: [bold]{project_info['name']}[/bold]")
        if project_info.get("languages"):
            console.print(f"    {t('init.languages')}: {', '.join(project_info['languages'])}")
        if project_info.get("frameworks"):
            console.print(f"    {t('init.frameworks')}: {', '.join(project_info['frameworks'])}")

    categories = ["skills", "dependencies", "errors", "logic", "exports", "maintenance"]
    workspace_dir = adelie_dir / "workspace"
    for cat in categories:
        (workspace_dir / cat).mkdir(parents=True, exist_ok=True)

    index_file = workspace_dir / "index.json"
    if not index_file.exists():
        index_file.write_text("{}", encoding="utf-8")

    specs_dir = adelie_dir / "specs"
    specs_dir.mkdir(parents=True, exist_ok=True)

    os_info = _detect_os()
    console.print(
        f"[green]  +[/green] OS detected: [bold]{os_info['os_name']} {os_info['release']}[/bold] "
        f"({os_info['machine']}, {os_info['shell']})"
    )

    default_config: dict = {"loop_interval": 30}

    if project_info["is_existing"] and project_info.get("has_code"):
        default_config["phase"] = "mid"
        console.print(f"[green]  +[/green] {t('init.phase_mid')}")
    else:
        default_config["phase"] = "initial"

    if project_info["is_existing"]:
        default_config["project"] = {
            "name": project_info.get("name", target.name),
            "languages": project_info.get("languages", []),
            "frameworks": project_info.get("frameworks", []),
            "detected_at": datetime.now().isoformat(timespec="seconds"),
        }

    default_config["os"] = {
        "system": os_info["system"],
        "os_name": os_info["os_name"],
        "release": os_info["release"],
        "machine": os_info["machine"],
        "shell": os_info["shell"],
        "detected_at": datetime.now().isoformat(timespec="seconds"),
    }

    config_path = adelie_dir / "config.json"
    if not config_path.exists() or args.force:
        config_path.write_text(json.dumps(default_config, indent=2, ensure_ascii=False), encoding="utf-8")

    context_file = adelie_dir / "context.md"
    os_context = _generate_os_context(os_info)
    if not context_file.exists() or args.force:
        context_file.write_text(os_context, encoding="utf-8")
        console.print(f"[green]  +[/green] Generated context.md (OS-specific prompts)")
    else:
        existing = context_file.read_text(encoding="utf-8")
        if "## System Environment" not in existing:
            context_file.write_text(existing.rstrip() + "\n\n" + os_context, encoding="utf-8")
            console.print(f"[green]  +[/green] Updated context.md with OS info")

    env_file = adelie_dir / ".env"
    if not env_file.exists() or args.force:
        env_template = """# ── Adelie LLM Configuration ─────────────────────────────────────────
# Provider: "gemini" or "ollama"
LLM_PROVIDER=ollama

# ── Gemini ───────────────────────────────────────────────────────────
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.0-flash

# ── Ollama (로컬) ────────────────────────────────────────────────────
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2

# ── Ollama Cloud (ollama.com 클라우드 사용 시) ────────────────────────
# OLLAMA_BASE_URL=https://ollama.com
# OLLAMA_API_KEY=your-ollama-cloud-api-key

# ── Fallback Chain ───────────────────────────────────────────────────
# FALLBACK_MODELS=gemini:gemini-2.5-flash,ollama:llama3.2
"""
        env_file.write_text(env_template, encoding="utf-8")

    gitignore = adelie_dir / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("workspace/\nconfig.json\n.env\n", encoding="utf-8")

    registry.register(str(target))

    console.print(f"[green]  +[/green] {t('init.created_ws')}")
    console.print(f"[green]  +[/green] {t('init.created_env')}")
    console.print(f"[green]  +[/green] {t('init.created_specs')}")
    console.print(f"[green]  +[/green] {t('init.registered')}")
    console.print(f"\n[bold green]{t('init.done')}[/bold green]")
    console.print(f"\n  adelie config                    [dim]# View settings[/dim]")
    console.print(f"  adelie run --goal \"your goal\"     [dim]# Start AI loop[/dim]")
    console.print(f"  adelie ws                         [dim]# List all workspaces[/dim]")
    console.print(f"\n  [dim]{t('init.specs_hint')}[/dim]")


def cmd_ws(args) -> None:
    """List or manage registered workspaces."""
    from adelie import registry

    if args.ws_action == "remove":
        if args.number is None:
            console.print(f"[red]ERROR: Specify workspace number: adelie ws remove <N>[/red]")
            return

        ws = registry.get_by_index(args.number)
        if not ws:
            console.print(f"[red]ERROR: Invalid workspace number: {args.number}[/red]")
            return

        ws_path = Path(ws["path"])
        adelie_dir = ws_path / ".adelie"

        if registry.remove(args.number):
            console.print(f"[green]OK: {t('ws.removed', n=args.number)}[/green]")

            if adelie_dir.exists():
                answer = input(f"   {t('ws.delete_data')}").strip().lower()
                if answer == "y":
                    shutil.rmtree(adelie_dir, ignore_errors=True)
                    console.print(f"   [dim]Deleted {adelie_dir}[/dim]")
                else:
                    console.print(f"   [dim].adelie data kept at {adelie_dir}[/dim]")
        else:
            console.print(f"[red]ERROR: Failed to remove workspace #{args.number}[/red]")
        return

    workspaces = registry.get_all()
    if not workspaces:
        console.print(f"[yellow]{t('ws.none')}[/yellow]")
        console.print("[dim]Initialize one with: adelie init[/dim]")
        return

    table = Table(title=t('ws.title'), show_header=True, border_style="cyan")
    table.add_column("#", style="bold cyan", justify="right")
    table.add_column("Directory", style="bold")
    table.add_column("Last Goal", max_width=40)
    table.add_column("Last Used")

    for i, ws in enumerate(workspaces, 1):
        path = ws.get("path", "")
        goal = ws.get("last_goal", "—") or "—"
        if len(goal) > 37:
            goal = goal[:37] + "…"
        last_used = ws.get("last_used", "")[:16].replace("T", " ")
        table.add_row(str(i), path, goal, last_used)

    console.print(table)
    console.print(f"\n[dim]Resume with: adelie run ws <#>[/dim]")
