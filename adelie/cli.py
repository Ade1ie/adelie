#!/usr/bin/env python3
"""
adelie/cli.py — Adelie CLI

All commands are dispatched from here. Invoked by the Node.js wrapper (bin/adelie.js)
or directly via `python adelie/cli.py`.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Ensure the package root is in sys.path (for direct execution or Node.js wrapper)
_PKG_ROOT = os.environ.get("ADELIE_PKG_ROOT", str(Path(__file__).resolve().parent.parent))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

# ── Workspace detection ──────────────────────────────────────────────────────

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


def _setup_env_from_workspace():
    """Apply workspace config.json values as environment variables."""
    ws_config = _load_workspace_config()
    env_map = {
        "provider": "LLM_PROVIDER",
        "gemini_api_key": "GEMINI_API_KEY",
        "gemini_model": "GEMINI_MODEL",
        "ollama_base_url": "OLLAMA_BASE_URL",
        "ollama_model": "OLLAMA_MODEL",
        "loop_interval": "LOOP_INTERVAL_SECONDS",
    }
    for key, env_key in env_map.items():
        if key in ws_config and not os.environ.get(env_key):
            os.environ[env_key] = str(ws_config[key])

    ws_root = _find_workspace_root()
    if ws_root.exists():
        os.environ.setdefault("WORKSPACE_PATH", str(ws_root / "workspace"))

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
                "[bold red]❌ GEMINI_API_KEY is not set.[/bold red]\n"
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
                f"[bold red]❌ Cannot connect to Ollama at {cfg.OLLAMA_BASE_URL}[/bold red]\n"
                "Start Ollama with: [bold]ollama serve[/bold]"
            )
            sys.exit(1)


# ═══════════════════════════════════════════════════════════════════════════════
# COMMANDS
# ═══════════════════════════════════════════════════════════════════════════════


def cmd_help(args: argparse.Namespace) -> None:
    """Show detailed help for all commands."""
    help_text = """
[bold cyan]🐧 Adelie — Command Reference[/bold cyan]

[bold]Workspace[/bold]
  [green]adelie init[/green] [dim][dir][/dim]             Initialize workspace in directory (default: .)
  [green]adelie ws[/green]                       List all registered workspaces
  [green]adelie ws remove[/green] [dim]<N>[/dim]           Remove workspace #N from registry

[bold]Run[/bold]
  [green]adelie run[/green] [dim]--goal "..."[/dim]        Start AI loop in current workspace
  [green]adelie run ws[/green] [dim]<N>[/dim]              Resume AI loop in workspace #N
  [green]adelie run once[/green] [dim]--goal "..."[/dim]   Run exactly one cycle then exit

[bold]Configuration[/bold]
  [green]adelie config[/green]                    Show current configuration
  [green]adelie config --provider[/green] [dim]ollama[/dim]  Switch LLM provider
  [green]adelie config --model[/green] [dim]gemma3:12b[/dim]  Set model
  [green]adelie config --interval[/green] [dim]60[/dim]     Set loop interval (seconds)
  [green]adelie config --api-key[/green] [dim]KEY[/dim]     Set Gemini API key
  [green]adelie config --ollama-url[/green] [dim]URL[/dim]  Set Ollama server URL

[bold]Monitoring[/bold]
  [green]adelie status[/green]                    System health & provider status
  [green]adelie inform[/green]                    Generate project status report (Inform AI)
  [green]adelie phase[/green]                     Show current project phase
  [green]adelie phase set[/green] [dim]<phase>[/dim]      Set project phase (initial/mid/mid_1/mid_2/late/evolve)

[bold]Knowledge Base[/bold]
  [green]adelie kb[/green]                        Show KB file counts
  [green]adelie kb --clear-errors[/green]          Clear error files
  [green]adelie kb --reset[/green]                Reset entire KB (destructive!)

[bold]Project Management[/bold]
  [green]adelie goal[/green]                      Show current project goal
  [green]adelie goal set[/green] [dim]"goal text"[/dim]   Set project goal (saved to KB)
  [green]adelie feedback[/green] [dim]"message"[/dim]      Send feedback to the AI loop
  [green]adelie feedback --list[/green]            Show pending feedback
  [green]adelie git[/green]                       Show git status & recent commits
  [green]adelie research[/green] [dim]"topic"[/dim]          Search the web and save findings to KB
  [green]adelie research --list[/green]            Show recent research results
  [green]adelie metrics[/green]                    Show recent cycle metrics
  [green]adelie metrics --agents[/green]           Show per-agent token usage
  [green]adelie metrics --trend[/green]            Show performance trend
  [green]adelie metrics --last[/green] [dim]N[/dim]          Show last N cycles (default: 20)

[bold]Ollama[/bold]
  [green]adelie ollama list[/green]               List installed models
  [green]adelie ollama pull[/green] [dim]<model>[/dim]      Download a model
  [green]adelie ollama remove[/green] [dim]<model>[/dim]    Remove a model
  [green]adelie ollama run[/green] [dim][model][/dim]       Interactive chat with model

[bold]Telegram[/bold]
  [green]adelie telegram setup[/green]            Setup bot token (from @BotFather)
  [green]adelie telegram start[/green] [dim][--ws N][/dim]  Start bot for a workspace
"""
    console.print(help_text)


# ── Auto Spec Sync ───────────────────────────────────────────────────────────


def _sync_specs() -> None:
    """
    Auto-detect and load spec files from .adelie/specs/ into KB.
    Tracks processed files via a manifest to avoid re-processing unchanged files.
    """
    ws_root = _find_workspace_root()
    specs_dir = ws_root / "specs"
    if not specs_dir.exists():
        return

    from adelie.spec_loader import SUPPORTED_EXTENSIONS, load_spec
    import adelie.config as cfg

    # Load manifest (tracks which files have been synced)
    manifest_path = specs_dir / ".manifest.json"
    manifest: dict = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            manifest = {}

    # Scan for spec files
    new_count = 0
    updated_count = 0

    for file_path in sorted(specs_dir.iterdir()):
        if file_path.is_dir() or file_path.name.startswith("."):
            continue

        ext = file_path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            continue

        # Check if file is new or modified
        file_key = file_path.name
        file_mtime = file_path.stat().st_mtime
        prev_mtime = manifest.get(file_key, {}).get("mtime", 0)

        if file_mtime <= prev_mtime:
            continue  # Already processed, no changes

        is_update = file_key in manifest
        try:
            load_spec(
                file_path=file_path,
                workspace_path=cfg.WORKSPACE_PATH,
                category="logic",
            )
            manifest[file_key] = {
                "mtime": file_mtime,
                "synced_at": datetime.now().isoformat(timespec="seconds"),
            }
            if is_update:
                updated_count += 1
            else:
                new_count += 1
        except Exception as e:
            console.print(f"[yellow]⚠️  Failed to sync {file_path.name}: {e}[/yellow]")

    # Save manifest
    if new_count > 0 or updated_count > 0:
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        parts = []
        if new_count:
            parts.append(f"{new_count} new")
        if updated_count:
            parts.append(f"{updated_count} updated")
        console.print(f"[green]📄 Auto-synced specs: {', '.join(parts)}[/green]")


# ═══════════════════════════════════════════════════════════════════════════════
# INIT
# ═══════════════════════════════════════════════════════════════════════════════


def cmd_init(args: argparse.Namespace) -> None:
    """Initialize a new Adelie workspace."""
    from adelie import registry

    target = Path(args.directory).resolve()
    adelie_dir = target / ".adelie"

    if adelie_dir.exists() and not args.force:
        console.print(f"[yellow]⚠️  .adelie/ already exists in {target}[/yellow]")
        console.print("[dim]   Use --force to reinitialize[/dim]")
        return

    console.print(f"[bold cyan]🐧 Adelie — Initializing workspace[/bold cyan]")
    console.print(f"   [dim]Directory: {target}[/dim]")

    # ── Detect existing project ──────────────────────────────────────────
    project_info = _detect_project(target)
    if project_info["is_existing"]:
        console.print(f"[green]  ✓[/green] Detected existing project")
        if project_info.get("name"):
            console.print(f"    Name: [bold]{project_info['name']}[/bold]")
        if project_info.get("languages"):
            console.print(f"    Languages: {', '.join(project_info['languages'])}")
        if project_info.get("frameworks"):
            console.print(f"    Frameworks: {', '.join(project_info['frameworks'])}")

    # ── Create workspace structure ───────────────────────────────────────
    categories = ["skills", "dependencies", "errors", "logic", "exports", "maintenance"]
    workspace_dir = adelie_dir / "workspace"
    for cat in categories:
        (workspace_dir / cat).mkdir(parents=True, exist_ok=True)

    index_file = workspace_dir / "index.json"
    if not index_file.exists():
        index_file.write_text("{}", encoding="utf-8")

    # ── Create specs folder ──────────────────────────────────────────────
    specs_dir = adelie_dir / "specs"
    specs_dir.mkdir(parents=True, exist_ok=True)

    # ── Create config ────────────────────────────────────────────────────
    default_config = {
        "provider": "ollama",
        "ollama_base_url": "http://localhost:11434",
        "ollama_model": "gemma3:12b",
        "gemini_api_key": "",
        "gemini_model": "gemini-2.0-flash",
        "loop_interval": 30,
    }

    # If existing project with code, start from MID phase
    if project_info["is_existing"] and project_info.get("has_code"):
        default_config["phase"] = "mid"
        console.print(f"[green]  ✓[/green] Phase set to 🔨 중기 (existing code detected)")
    else:
        default_config["phase"] = "initial"

    # Save project info
    if project_info["is_existing"]:
        default_config["project"] = {
            "name": project_info.get("name", target.name),
            "languages": project_info.get("languages", []),
            "frameworks": project_info.get("frameworks", []),
            "detected_at": datetime.now().isoformat(timespec="seconds"),
        }

    config_path = adelie_dir / "config.json"
    if not config_path.exists() or args.force:
        config_path.write_text(json.dumps(default_config, indent=2, ensure_ascii=False), encoding="utf-8")

    gitignore = adelie_dir / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("workspace/\nconfig.json\n", encoding="utf-8")

    # Register in global registry
    registry.register(str(target))

    console.print("[green]  ✓[/green] Created .adelie/ workspace structure")
    console.print("[green]  ✓[/green] Created .adelie/specs/ (drop spec files here)")
    console.print("[green]  ✓[/green] Registered in global workspace list")
    console.print(f"\n[bold green]✅ Workspace initialized![/bold green]")
    console.print(f"\n  adelie config                    [dim]# View settings[/dim]")
    console.print(f"  adelie run --goal \"your goal\"     [dim]# Start AI loop[/dim]")
    console.print(f"  adelie ws                         [dim]# List all workspaces[/dim]")
    console.print(f"\n  [dim]📄 Spec files: .adelie/specs/ 에 MD/PDF/DOCX 파일을 넣으면 자동 인식됩니다[/dim]")


def _detect_project(target: Path) -> dict:
    """Detect existing project type, languages, and frameworks."""
    info: dict = {"is_existing": False, "has_code": False, "languages": [], "frameworks": [], "name": target.name}

    # Check for project markers
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

    # Detect frameworks from package.json
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

    # Check for .git
    if (target / ".git").exists():
        info["is_existing"] = True

    # Check for actual source code
    code_extensions = {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java", ".rb", ".php", ".svelte", ".vue"}
    for ext in code_extensions:
        if list(target.rglob(f"*{ext}"))[:1]:  # Just check if any exist
            info["has_code"] = True
            break

    return info


def cmd_ws(args: argparse.Namespace) -> None:
    """List or manage registered workspaces."""
    from adelie import registry

    if args.ws_action == "remove":
        if args.number is None:
            console.print("[red]❌ Specify workspace number: adelie ws remove <N>[/red]")
            return

        # Get workspace info before removing
        ws = registry.get_by_index(args.number)
        if not ws:
            console.print(f"[red]❌ Invalid workspace number: {args.number}[/red]")
            return

        ws_path = Path(ws["path"])
        adelie_dir = ws_path / ".adelie"

        if registry.remove(args.number):
            console.print(f"[green]✅ Workspace #{args.number} removed from registry[/green]")

            # Ask if user wants to delete .adelie files too
            if adelie_dir.exists():
                answer = input(f"   🗑️  Also delete .adelie data at {adelie_dir}? (y/N): ").strip().lower()
                if answer == "y":
                    import shutil
                    shutil.rmtree(adelie_dir, ignore_errors=True)
                    console.print(f"   [dim]🗑️  Deleted {adelie_dir}[/dim]")
                else:
                    console.print(f"   [dim]📁 .adelie data kept at {adelie_dir}[/dim]")
        else:
            console.print(f"[red]❌ Failed to remove workspace #{args.number}[/red]")
        return

    workspaces = registry.get_all()
    if not workspaces:
        console.print("[yellow]No workspaces registered yet.[/yellow]")
        console.print("[dim]Initialize one with: adelie init[/dim]")
        return

    table = Table(title="🐧 Adelie Workspaces", show_header=True, border_style="cyan")
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


def cmd_run(args: argparse.Namespace) -> None:
    """Run the AI loop — either in current workspace or by workspace number."""
    from adelie import registry

    # adelie run ws <N>
    if args.workspace_num is not None:
        ws = registry.get_by_index(args.workspace_num)
        if not ws:
            console.print(f"[red]❌ Workspace #{args.workspace_num} not found. Use 'adelie ws' to list.[/red]")
            sys.exit(1)

        ws_path = ws["path"]
        adelie_dir = Path(ws_path) / ".adelie"
        if not adelie_dir.exists():
            console.print(f"[red]❌ .adelie/ not found in {ws_path}[/red]")
            sys.exit(1)

        # Set environment to target workspace
        os.environ["ADELIE_CWD"] = ws_path
        os.environ["WORKSPACE_PATH"] = str(adelie_dir / "workspace")

        # Load that workspace's config
        config_path = adelie_dir / "config.json"
        if config_path.exists():
            ws_config = json.loads(config_path.read_text(encoding="utf-8"))
            env_map = {
                "provider": "LLM_PROVIDER",
                "gemini_api_key": "GEMINI_API_KEY",
                "gemini_model": "GEMINI_MODEL",
                "ollama_base_url": "OLLAMA_BASE_URL",
                "ollama_model": "OLLAMA_MODEL",
                "loop_interval": "LOOP_INTERVAL_SECONDS",
            }
            for key, env_key in env_map.items():
                if key in ws_config:
                    os.environ[env_key] = str(ws_config[key])

        # Use last goal if no new goal specified
        goal = args.goal
        if goal == "Operate and improve the Adelie autonomous AI system" and ws.get("last_goal"):
            goal = ws["last_goal"]

        console.print(f"[bold cyan]🐧 Resuming workspace #{args.workspace_num}[/bold cyan]")
        console.print(f"   [dim]{ws_path}[/dim]")

        registry.update_last_used(ws_path, goal)
    else:
        goal = args.goal
        ws_root = _find_workspace_root()
        if ws_root.exists():
            registry.update_last_used(str(ws_root.parent), goal)

    _validate_provider()

    # Auto-sync spec files from .adelie/specs/
    _sync_specs()

    # Get current phase from workspace config
    ws_config = _load_workspace_config()
    phase = ws_config.get("phase", "initial")

    if args.once:
        from adelie.orchestrator import Orchestrator
        orchestrator = Orchestrator(goal=goal, phase=phase)
        result = orchestrator.run_once()
        console.print("\n[bold]Expert AI decision:[/bold]")
        console.print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        from adelie.orchestrator import Orchestrator
        from adelie.interactive import AdelieApp
        orchestrator = Orchestrator(goal=goal, phase=phase)
        AdelieApp(orchestrator).run()


def cmd_status(args: argparse.Namespace) -> None:
    """Show current system status."""
    _ensure_adelie_config()
    from adelie.llm_client import get_provider_info
    from adelie.kb import retriever
    import adelie.config as cfg

    retriever.ensure_workspace()

    table = Table(title="🐧 Adelie Status", show_header=False, border_style="cyan")
    table.add_column("Key", style="bold")
    table.add_column("Value")

    table.add_row("LLM Provider", get_provider_info())
    table.add_row("Loop Interval", f"{cfg.LOOP_INTERVAL_SECONDS}s")
    table.add_row("Workspace", str(cfg.WORKSPACE_PATH))

    categories = retriever.list_categories()
    total = sum(categories.values())
    kb_summary = ", ".join(f"{k}: {v}" for k, v in categories.items() if v > 0)
    table.add_row("KB Files", f"{total} total ({kb_summary or 'empty'})")

    console.print(table)

    if cfg.LLM_PROVIDER == "gemini":
        if cfg.GEMINI_API_KEY:
            console.print("[green]✅ Gemini API key configured[/green]")
        else:
            console.print("[red]❌ GEMINI_API_KEY not set[/red]")
    elif cfg.LLM_PROVIDER == "ollama":
        import requests
        try:
            r = requests.get(f"{cfg.OLLAMA_BASE_URL}/api/tags", timeout=3)
            r.raise_for_status()
            models = [m["name"] for m in r.json().get("models", [])]
            console.print(f"[green]✅ Ollama connected — {len(models)} model(s) available[/green]")
            for m in models:
                marker = "  →" if cfg.OLLAMA_MODEL in m else "   "
                console.print(f"[dim]{marker} {m}[/dim]")
        except Exception:
            console.print(f"[red]❌ Cannot connect to Ollama at {cfg.OLLAMA_BASE_URL}[/red]")


def cmd_phase(args: argparse.Namespace) -> None:
    """Show or set the current project lifecycle phase."""
    _ensure_adelie_config()
    ws_config = _load_workspace_config()
    from adelie.phases import Phase, get_all_phases, get_phase_label, PHASE_INFO

    if args.phase_action == "set":
        valid = [p.value for p in Phase]
        if args.phase_value not in valid:
            console.print(f"[red]❌ Invalid phase. Choose from: {', '.join(valid)}[/red]")
            return
        ws_config["phase"] = args.phase_value
        _save_workspace_config(ws_config)
        label = get_phase_label(args.phase_value)
        console.print(f"[green]✅ Phase set → {label}[/green]")
        return

    # Show current phase with full lifecycle visualization
    current = ws_config.get("phase", "initial")
    phases = get_all_phases()

    console.print(f"\n[bold cyan]🐧 Adelie — Project Phase[/bold cyan]\n")

    for value, label in phases:
        if value == current:
            console.print(f"  [bold green]▶ {label}[/bold green]  ← [bold]현재[/bold]")
            info = PHASE_INFO.get(value, {})
            console.print(f"    [dim]목표: {info.get('goal', '')}[/dim]")
            console.print(f"    [dim]전환: {info.get('transition_criteria', '')}[/dim]")
        else:
            console.print(f"  [dim]  {label}[/dim]")

    console.print(f"\n[dim]Change with: adelie phase set <phase>[/dim]")



def cmd_inform(args: argparse.Namespace) -> None:
    """Generate project status report using Inform AI."""
    _validate_provider()
    import adelie.config as cfg
    from adelie.agents import inform_ai

    system_state = {
        "situation": "normal",
        "goal": args.goal,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }

    report = inform_ai.run(
        system_state=system_state,
        goal=args.goal,
        loop_iteration=0,
    )

    console.print()
    from rich.markdown import Markdown
    console.print(Markdown(report))
    console.print(f"\n[dim]📄 Full report saved to: {cfg.WORKSPACE_PATH / 'exports' / 'status_report.md'}[/dim]")


def cmd_config(args: argparse.Namespace) -> None:
    """View or update configuration."""
    _ensure_adelie_config()
    ws_config = _load_workspace_config()
    changed = False

    if args.provider:
        provider = args.provider.lower()
        if provider not in ("gemini", "ollama"):
            console.print("[red]❌ Provider must be 'gemini' or 'ollama'[/red]")
            sys.exit(1)
        ws_config["provider"] = provider
        console.print(f"[green]✅ provider → {provider}[/green]")
        changed = True

    if args.model:
        provider = ws_config.get("provider", "gemini")
        if provider == "ollama":
            ws_config["ollama_model"] = args.model
            console.print(f"[green]✅ ollama_model → {args.model}[/green]")
        else:
            ws_config["gemini_model"] = args.model
            console.print(f"[green]✅ gemini_model → {args.model}[/green]")
        changed = True

    if args.interval:
        ws_config["loop_interval"] = args.interval
        console.print(f"[green]✅ loop_interval → {args.interval}s[/green]")
        changed = True

    if args.ollama_url:
        ws_config["ollama_base_url"] = args.ollama_url
        console.print(f"[green]✅ ollama_base_url → {args.ollama_url}[/green]")
        changed = True

    if args.api_key:
        ws_config["gemini_api_key"] = args.api_key
        console.print("[green]✅ gemini_api_key updated[/green]")
        changed = True

    if changed:
        _save_workspace_config(ws_config)
    else:
        table = Table(title="⚙️  Adelie Configuration", show_header=True, border_style="blue")
        table.add_column("Setting", style="bold")
        table.add_column("Value")

        provider = ws_config.get("provider", "gemini")
        table.add_row("Provider", provider)
        if provider == "gemini":
            api_key = ws_config.get("gemini_api_key", "")
            table.add_row("Gemini API Key", "***" + api_key[-4:] if api_key else "(not set)")
            table.add_row("Gemini Model", ws_config.get("gemini_model", "gemini-2.0-flash"))
        table.add_row("Ollama URL", ws_config.get("ollama_base_url", "http://localhost:11434"))
        table.add_row("Ollama Model", ws_config.get("ollama_model", "llama3.2"))
        table.add_row("Loop Interval", f"{ws_config.get('loop_interval', 30)}s")
        table.add_row("Workspace", str(_find_workspace_root()))

        console.print(table)
        console.print(f"\n[dim]Config: {_workspace_config_path()}[/dim]")


def cmd_kb(args: argparse.Namespace) -> None:
    """Knowledge Base management."""
    _ensure_adelie_config()
    import adelie.config as cfg
    from adelie.kb import retriever

    retriever.ensure_workspace()

    if args.clear_errors:
        errors_dir = cfg.WORKSPACE_PATH / "errors"
        count = 0
        for f in errors_dir.glob("*.md"):
            f.unlink()
            count += 1
        index = retriever.get_index()
        index = {k: v for k, v in index.items() if not k.startswith("errors/")}
        retriever.INDEX_FILE.write_text(json.dumps(index, indent=2), encoding="utf-8")
        console.print(f"[green]✅ Cleared {count} error file(s)[/green]")

    elif args.reset:
        console.print("[yellow]⚠️  This will delete ALL Knowledge Base files![/yellow]")
        confirm = input("Type 'yes' to confirm: ")
        if confirm.strip().lower() == "yes":
            for cat_dir in cfg.WORKSPACE_PATH.iterdir():
                if cat_dir.is_dir():
                    shutil.rmtree(cat_dir)
                    cat_dir.mkdir()
            retriever.INDEX_FILE.write_text("{}", encoding="utf-8")
            console.print("[green]✅ Workspace reset complete[/green]")
        else:
            console.print("[dim]Cancelled.[/dim]")

    else:
        categories = retriever.list_categories()
        table = Table(title="📚 Knowledge Base", show_header=True, border_style="green")
        table.add_column("Category", style="bold")
        table.add_column("Files", justify="right")

        total = 0
        for cat, count in categories.items():
            table.add_row(cat, str(count))
            total += count
        table.add_row("── Total ──", str(total), style="bold")

        console.print(table)
        console.print(f"\n[dim]Path: {cfg.WORKSPACE_PATH}[/dim]")


def cmd_ollama(args: argparse.Namespace) -> None:
    """Ollama model management."""
    _ensure_adelie_config()
    import adelie.config as cfg

    base_url = cfg.OLLAMA_BASE_URL
    action = args.ollama_action

    if action == "list":
        import requests
        try:
            r = requests.get(f"{base_url}/api/tags", timeout=5)
            r.raise_for_status()
            models = r.json().get("models", [])
            if not models:
                console.print("[yellow]No models installed.[/yellow]")
                console.print("[dim]Pull one with: adelie ollama pull <model>[/dim]")
                return

            table = Table(title="🦙 Ollama Models", show_header=True, border_style="magenta")
            table.add_column("Name", style="bold")
            table.add_column("Size")
            table.add_column("Modified")

            for m in models:
                name = m.get("name", "")
                size_gb = f"{m.get('size', 0) / 1e9:.1f} GB"
                modified = m.get("modified_at", "")[:10]
                marker = " ← active" if cfg.OLLAMA_MODEL in name else ""
                table.add_row(f"{name}{marker}", size_gb, modified)

            console.print(table)
        except Exception as e:
            console.print(f"[red]❌ Cannot connect to Ollama at {base_url}[/red]")
            console.print("[dim]   Start Ollama with: ollama serve[/dim]")

    elif action == "pull":
        if not args.model_name:
            console.print("[red]❌ Specify model: adelie ollama pull <model>[/red]")
            return
        console.print(f"[bold cyan]🦙 Pulling model: {args.model_name}[/bold cyan]")
        try:
            subprocess.run(["ollama", "pull", args.model_name], check=True)
            console.print(f"[green]✅ '{args.model_name}' downloaded[/green]")
            console.print(f"[dim]Set as active: adelie config --model {args.model_name}[/dim]")
        except FileNotFoundError:
            console.print("[red]❌ 'ollama' not found. Install from: https://ollama.com[/red]")
        except subprocess.CalledProcessError as e:
            console.print(f"[red]❌ Failed: {e}[/red]")

    elif action == "remove":
        if not args.model_name:
            console.print("[red]❌ Specify model: adelie ollama remove <model>[/red]")
            return
        try:
            subprocess.run(["ollama", "rm", args.model_name], check=True)
            console.print(f"[green]✅ '{args.model_name}' removed[/green]")
        except FileNotFoundError:
            console.print("[red]❌ 'ollama' not found.[/red]")
        except subprocess.CalledProcessError as e:
            console.print(f"[red]❌ Failed: {e}[/red]")

    elif action == "run":
        model = args.model_name or cfg.OLLAMA_MODEL
        console.print(f"[bold cyan]🦙 Chat with: {model}[/bold cyan]")
        try:
            subprocess.run(["ollama", "run", model])
        except FileNotFoundError:
            console.print("[red]❌ 'ollama' not found.[/red]")

# ═══════════════════════════════════════════════════════════════════════════════
# TELEGRAM
# ═══════════════════════════════════════════════════════════════════════════════


def cmd_telegram(args: argparse.Namespace) -> None:
    """Telegram bot management."""
    action = args.telegram_action

    if action == "setup":
        _ensure_adelie_config()
        ws_config = _load_workspace_config()

        console.print("[bold cyan]🤖 Telegram Bot Setup[/bold cyan]\n")
        console.print("1. Open Telegram and search for [bold]@BotFather[/bold]")
        console.print("2. Send [bold]/newbot[/bold] and follow the instructions")
        console.print("3. Copy the bot token and paste it below\n")

        token = input("Bot Token: ").strip()
        if not token:
            console.print("[red]❌ Token cannot be empty[/red]")
            return

        ws_config["telegram_bot_token"] = token
        _save_workspace_config(ws_config)
        console.print("[green]✅ Telegram bot token saved![/green]")
        console.print("[dim]Start with: adelie telegram start[/dim]")

    elif action == "start":
        from adelie import registry

        # Determine workspace
        if args.ws_num:
            ws = registry.get_by_index(args.ws_num)
            if not ws:
                console.print(f"[red]❌ Workspace #{args.ws_num} not found.[/red]")
                sys.exit(1)
            ws_path = ws["path"]
        else:
            ws_path = str(_find_workspace_root().parent)

        adelie_dir = Path(ws_path) / ".adelie"
        if not adelie_dir.exists():
            console.print(f"[red]❌ .adelie/ not found in {ws_path}[/red]")
            console.print("[dim]Initialize with: adelie init[/dim]")
            sys.exit(1)

        # Load config to get token
        config_path = adelie_dir / "config.json"
        if config_path.exists():
            ws_config = json.loads(config_path.read_text(encoding="utf-8"))
        else:
            ws_config = {}

        token = args.token or ws_config.get("telegram_bot_token", "")
        if not token:
            console.print("[red]❌ No Telegram bot token configured.[/red]")
            console.print("[dim]Run: adelie telegram setup[/dim]")
            sys.exit(1)

        from adelie.integrations.telegram_bot import AdelieTelegramBot
        bot = AdelieTelegramBot(token=token, workspace_path=ws_path)
        bot.start()

    else:
        console.print("[red]❌ Unknown action. Use: setup, start[/red]")


def cmd_spec(args: argparse.Namespace) -> None:
    """Load, list, or remove specification files (MD, PDF, DOCX) from KB."""
    _ensure_adelie_config()
    import adelie.config as cfg
    from adelie.kb import retriever
    retriever.ensure_workspace()

    action = args.spec_action

    if action == "load":
        if not args.file_path:
            console.print("[red]❌ Provide a file: adelie spec load <file>[/red]")
            return

        file_path = Path(args.file_path).resolve()
        if not file_path.exists():
            console.print(f"[red]❌ File not found: {file_path}[/red]")
            return

        from adelie.spec_loader import SUPPORTED_EXTENSIONS, load_spec

        ext = file_path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            console.print(
                f"[red]❌ Unsupported format: '{ext}'[/red]\n"
                f"[dim]Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}[/dim]"
            )
            return

        category = args.category or "logic"
        console.print(f"[bold cyan]📄 Loading spec: {file_path.name}[/bold cyan]")
        console.print(f"   [dim]Format: {ext} → Markdown[/dim]")
        console.print(f"   [dim]Category: {category}[/dim]")

        try:
            saved_path = load_spec(
                file_path=file_path,
                workspace_path=cfg.WORKSPACE_PATH,
                category=category,
            )
            # Show chunk info
            from adelie.spec_loader import list_specs
            specs = list_specs(cfg.WORKSPACE_PATH)
            loaded = next((s for s in specs if s["path"] == f"{category}/{saved_path.name}"), None)
            chunk_info = ""
            if loaded and loaded.get("chunks", 0) > 0:
                chunk_info = f" ({loaded['chunks']} chunks)"
            console.print(f"\n[green]✅ Spec loaded → {saved_path.relative_to(cfg.WORKSPACE_PATH)}{chunk_info}[/green]")
        except ImportError as e:
            console.print(f"[red]❌ Missing dependency: {e}[/red]")
            console.print("[dim]Run: pip install -r requirements.txt[/dim]")
        except Exception as e:
            console.print(f"[red]❌ Failed to load spec: {e}[/red]")

    elif action == "list":
        from adelie.spec_loader import list_specs

        specs = list_specs(cfg.WORKSPACE_PATH)
        if not specs:
            console.print("[dim]No specs loaded yet.[/dim]")
            console.print("[dim]Load one with: adelie spec load <file>[/dim]")
            return

        table = Table(title="📋 Loaded Specifications", show_header=True, border_style="green")
        table.add_column("Name", style="bold")
        table.add_column("Category")
        table.add_column("Size", justify="right")
        table.add_column("Chunks", justify="right")
        table.add_column("Updated")

        for spec in specs:
            size_str = f"{spec['size'] / 1024:.1f} KB" if spec['size'] >= 1024 else f"{spec['size']} B"
            chunks = spec.get('chunks', 0)
            chunk_str = str(chunks) if chunks > 0 else "-"
            table.add_row(
                spec["name"],
                spec["category"],
                size_str,
                chunk_str,
                spec.get("updated", "")[:16],
            )
        console.print(table)

    elif action == "remove":
        spec_name = args.file_path
        if not spec_name:
            console.print("[red]❌ Provide spec name: adelie spec remove <name>[/red]")
            console.print("[dim]Use 'adelie spec list' to see loaded specs.[/dim]")
            return

        from adelie.spec_loader import remove_spec

        if remove_spec(cfg.WORKSPACE_PATH, spec_name):
            console.print(f"[green]✅ Spec '{spec_name}' removed[/green]")
        else:
            console.print(f"[yellow]⚠️  Spec '{spec_name}' not found[/yellow]")
            console.print("[dim]Use 'adelie spec list' to see loaded specs.[/dim]")


def cmd_scan(args: argparse.Namespace) -> None:
    """Scan existing codebase and generate KB documentation + auto-assign coders."""
    _ensure_adelie_config()
    _validate_provider()

    target = Path(args.directory).resolve()

    if not target.is_dir():
        console.print(f"[red]❌ Directory not found: {target}[/red]")
        return

    ws_root = _find_workspace_root()
    if not ws_root.exists():
        console.print("[yellow]⚠️  No .adelie/ workspace found. Run 'adelie init' first.[/yellow]")
        return

    import adelie.config as cfg
    from adelie.agents.scanner_ai import run_scan

    written = run_scan(
        project_root=target,
        workspace_path=cfg.WORKSPACE_PATH,
    )

    if written:
        console.print(f"\n[bold green]✅ Scan complete — {len(written)} KB document(s) generated[/bold green]")
    else:
        console.print("[yellow]No documents generated. Check if the project has source files.[/yellow]")


# ═══════════════════════════════════════════════════════════════════════════════
# FEEDBACK / GOAL / GIT
# ═══════════════════════════════════════════════════════════════════════════════


def cmd_feedback(args: argparse.Namespace) -> None:
    """Submit or list user feedback."""
    _ensure_adelie_config()

    from adelie.feedback_queue import submit_feedback, read_pending

    if args.list_pending:
        pending = read_pending()
        if not pending:
            console.print("[green]✅ No pending feedback[/green]")
            return
        table = Table(title="🗣️ Pending Feedback", show_header=True, border_style="yellow")
        table.add_column("ID", style="bold cyan")
        table.add_column("Priority")
        table.add_column("Message", max_width=50)
        table.add_column("Time")
        for fb in pending:
            prio = fb.get("priority", "normal")
            icon = {"critical": "🔴", "high": "🟠", "normal": "🟢", "low": "⚪"}.get(prio, "🟢")
            table.add_row(
                fb.get("id", "?"),
                f"{icon} {prio}",
                fb.get("message", "")[:50],
                fb.get("timestamp", "")[:16],
            )
        console.print(table)
        return

    if not args.message:
        console.print("[red]❌ Provide a message: adelie feedback \"your message\"[/red]")
        console.print("[dim]Or list pending: adelie feedback --list[/dim]")
        return

    submit_feedback(message=args.message, priority=args.priority)


def cmd_goal(args: argparse.Namespace) -> None:
    """Set or show the project goal."""
    _ensure_adelie_config()
    import adelie.config as cfg
    from adelie.kb import retriever

    retriever.ensure_workspace()
    goal_path = cfg.WORKSPACE_PATH / "logic" / "project_goal.md"

    if args.goal_action == "set":
        if not args.goal_text:
            console.print("[red]❌ Provide goal text: adelie goal set \"your goal\"[/red]")
            return

        goal_path.parent.mkdir(parents=True, exist_ok=True)
        content = (
            f"# 🎯 Project Goal\n\n"
            f"**Set**: {datetime.now().isoformat(timespec='seconds')}\n\n"
            f"## Goal\n{args.goal_text}\n\n"
            f"## Notes\n- This file is automatically referenced by Expert AI and Writer AI.\n"
            f"- Update this goal whenever the project direction changes.\n"
        )
        goal_path.write_text(content, encoding="utf-8")
        retriever.update_index(
            "logic/project_goal.md",
            tags=["goal", "project", "priority"],
            summary=f"Project goal: {args.goal_text[:100]}",
        )
        console.print(f"[green]✅ Project goal saved![/green]")
        console.print(f"[dim]   {args.goal_text[:80]}[/dim]")
        return

    # Show current goal
    if goal_path.exists():
        content = goal_path.read_text(encoding="utf-8")
        from rich.markdown import Markdown
        console.print(Markdown(content))
    else:
        console.print("[yellow]No project goal set yet.[/yellow]")
        console.print("[dim]Set one with: adelie goal set \"your goal description\"[/dim]")


def cmd_git(args: argparse.Namespace) -> None:
    """Show git status and recent commits."""
    _ensure_adelie_config()
    import adelie.config as cfg

    from adelie.git_ops import is_git_repo, get_status, get_log

    root = cfg.PROJECT_ROOT

    if not is_git_repo(root):
        console.print(f"[yellow]⚠️  {root} is not a git repository.[/yellow]")
        return

    # Status
    status = get_status(root)
    if status["ok"]:
        if status["changed_files"] == 0:
            console.print("[green]✅ Working tree clean[/green]")
        else:
            console.print(f"[yellow]📝 {status['changed_files']} changed file(s):[/yellow]")
            for f in status["files"]:
                console.print(f"   [dim]{f}[/dim]")
    else:
        console.print(f"[red]❌ Git error: {status.get('error', '?')}[/red]")

    # Recent log
    log = get_log(n=5, root=root)
    if log:
        console.print("\n[bold]Recent commits:[/bold]")
        for entry in log:
            console.print(f"  [cyan]{entry['hash']}[/cyan] {entry['message']}")


def cmd_research(args: argparse.Namespace) -> None:
    """Perform manual web research or list recent results."""
    _ensure_adelie_config()
    _validate_provider()

    if args.list_results:
        import adelie.config as cfg
        research_dir = cfg.WORKSPACE_PATH.parent / "research"
        if not research_dir.exists():
            console.print("[dim]No research logs yet.[/dim]")
            return
        logs = sorted(research_dir.glob("log_*.json"), reverse=True)[:5]
        if not logs:
            console.print("[dim]No research logs yet.[/dim]")
            return
        for log_file in logs:
            try:
                data = json.loads(log_file.read_text(encoding="utf-8"))
                ts = data.get("timestamp", "?")[:16]
                total = data.get("total_queries", 0)
                grounded = data.get("grounded_count", 0)
                console.print(f"  [cyan]{ts}[/cyan] — {total} quer{'y' if total == 1 else 'ies'} ({grounded} grounded)")
                for r in data.get("results", []):
                    console.print(f"    → {r.get('topic', '?')[:50]} → {r.get('kb_path', '?')}")
            except Exception:
                pass
        return

    if not args.topic:
        console.print("[red]❌ Provide a topic: adelie research \"your topic\"[/red]")
        console.print("[dim]Or list recent: adelie research --list[/dim]")
        return

    from adelie.agents.research_ai import run as run_research
    results = run_research(
        queries=[{
            "topic": args.topic,
            "context": args.context or "",
            "category": args.category or "dependencies",
        }],
        max_queries=1,
    )
    if results:
        console.print(f"\n[green]✅ Research saved to KB:[/green] {results[0].get('kb_path', '?')}")
    else:
        console.print("[yellow]No results found.[/yellow]")


def cmd_metrics(args: argparse.Namespace) -> None:
    """Show cycle metrics, agent usage, and performance trends."""
    _ensure_adelie_config()
    from adelie.metrics import read_cycles, summary_table, agent_summary_table, trend_summary, get_stats_summary

    last_n = args.last or 20

    # Time filter
    since = None
    if args.since:
        from datetime import timedelta
        hours_map = {
            "1h": 1, "6h": 6, "12h": 12, "24h": 24, "48h": 48,
            "1d": 24, "7d": 168,
        }
        hours = hours_map.get(args.since)
        if hours:
            since = datetime.now() - timedelta(hours=hours)
        else:
            try:
                h = int(args.since.rstrip("h"))
                since = datetime.now() - timedelta(hours=h)
            except ValueError:
                console.print(f"[red]❌ Invalid --since value: {args.since}[/red]")
                console.print("[dim]Use: 1h, 6h, 12h, 24h, 48h, 7d[/dim]")
                return

    records = read_cycles(since=since, last_n=last_n)

    if not records:
        console.print("[yellow]No metrics data yet.[/yellow]")
        console.print("[dim]Metrics are recorded automatically when the AI loop runs.[/dim]")
        return

    if args.agents:
        console.print(agent_summary_table(records))
        stats = get_stats_summary(records)
        console.print(f"\n[dim]Based on {stats['total_cycles']} cycles | "
                      f"{stats['first_cycle_ts'][:16]} → {stats['last_cycle_ts'][:16]}[/dim]")
    elif args.trend:
        console.print(trend_summary(records))
        stats = get_stats_summary(records)
        console.print(f"\n[dim]{stats['total_cycles']} cycles | "
                      f"avg {stats['avg_cycle_time']}s | "
                      f"min {stats['min_cycle_time']}s | max {stats['max_cycle_time']}s | "
                      f"total {stats['total_tokens_used']:,} tokens[/dim]")
    else:
        console.print(summary_table(records))
        stats = get_stats_summary(records)
        console.print(f"\n[dim]{stats['total_cycles']} cycles shown | "
                      f"avg {stats['avg_cycle_time']}s/cycle | "
                      f"avg {stats['avg_tokens_per_cycle']:,} tok/cycle[/dim]")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="adelie",
        description="🐧 Adelie — Self-Communicating Autonomous AI Loop",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Run [adelie help] for detailed command reference.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ── help ──────
    p_help = subparsers.add_parser("help", help="Show detailed command reference")
    p_help.set_defaults(func=cmd_help)

    # ── init ──────
    p_init = subparsers.add_parser("init", help="Initialize a new workspace")
    p_init.add_argument("directory", nargs="?", default=".",
                        help="Target directory (default: current)")
    p_init.add_argument("--force", action="store_true",
                        help="Reinitialize existing workspace")
    p_init.set_defaults(func=cmd_init)

    # ── ws ────────
    p_ws = subparsers.add_parser("ws", help="List / manage workspaces")
    p_ws.add_argument("ws_action", nargs="?", default="list",
                      choices=["list", "remove"],
                      help="Action (default: list)")
    p_ws.add_argument("number", nargs="?", type=int, default=None,
                      help="Workspace number (for remove)")
    p_ws.set_defaults(func=cmd_ws)

    # ── scan ──────
    p_scan = subparsers.add_parser("scan", help="Scan existing codebase and generate KB docs")
    p_scan.add_argument("--directory", type=str, default=".",
                        help="Project directory to scan (default: current)")
    p_scan.set_defaults(func=cmd_scan)

    # ── spec ──────
    p_spec = subparsers.add_parser("spec", help="Load spec files (MD, PDF, DOCX) into KB")
    p_spec.add_argument("spec_action", nargs="?", default="list",
                        choices=["load", "list", "remove"],
                        help="load / list (default) / remove")
    p_spec.add_argument("file_path", nargs="?", default=None,
                        help="File path (for load) or spec name (for remove)")
    p_spec.add_argument("--category", type=str, default="logic",
                        choices=["dependencies", "skills", "logic", "errors", "maintenance"],
                        help="KB category (default: logic)")
    # For 'remove' action, spec_name is the file_path positional
    p_spec.set_defaults(func=cmd_spec, spec_name=None)

    # ── run ───────
    p_run = subparsers.add_parser("run", help="Run the AI loop")
    p_run.add_argument("ws_keyword", nargs="?", default=None,
                       help="Use 'ws' followed by a number to resume a workspace")
    p_run.add_argument("workspace_num", nargs="?", type=int, default=None,
                       help="Workspace number (use with 'ws')")
    p_run.add_argument("--goal", type=str,
                       default="Operate and improve the Adelie autonomous AI system",
                       help="High-level goal for the AI agents")
    p_run.add_argument("--once", action="store_true",
                       help="Run exactly one cycle then exit")
    p_run.set_defaults(func=_dispatch_run)

    # ── status ────
    p_status = subparsers.add_parser("status", help="Show system status & health")
    p_status.set_defaults(func=cmd_status)

    # ── inform ────
    p_inform = subparsers.add_parser("inform", help="Generate project status report (Inform AI)")
    p_inform.add_argument("--goal", type=str, default="",
                          help="Project goal context for the report")
    p_inform.set_defaults(func=cmd_inform)

    # ── config ────
    p_config = subparsers.add_parser("config", help="View or update configuration")
    p_config.add_argument("--provider", type=str, help="'gemini' or 'ollama'")
    p_config.add_argument("--model", type=str, help="Model name")
    p_config.add_argument("--interval", type=int, help="Loop interval (seconds)")
    p_config.add_argument("--ollama-url", type=str, help="Ollama server URL")
    p_config.add_argument("--api-key", type=str, help="Gemini API key")
    p_config.set_defaults(func=cmd_config)

    # ── kb ────────
    p_kb = subparsers.add_parser("kb", help="Knowledge Base management")
    p_kb.add_argument("--clear-errors", action="store_true", help="Clear error files")
    p_kb.add_argument("--reset", action="store_true", help="Reset entire KB")
    p_kb.set_defaults(func=cmd_kb)

    # ── ollama ────
    p_ollama = subparsers.add_parser("ollama", help="Ollama model management")
    p_ollama.add_argument("ollama_action", choices=["list", "pull", "remove", "run"],
                          help="list / pull / remove / run")
    p_ollama.add_argument("model_name", nargs="?", default=None,
                          help="Model name")
    p_ollama.set_defaults(func=cmd_ollama)

    # ── telegram ──
    p_tg = subparsers.add_parser("telegram", help="Telegram bot integration")
    p_tg.add_argument("telegram_action", choices=["setup", "start"],
                      help="setup (register token) / start (run bot)")
    p_tg.add_argument("--ws", type=int, dest="ws_num", default=None,
                      help="Workspace number to bind the bot to")
    p_tg.add_argument("--token", type=str, default=None,
                      help="Bot token (overrides saved one)")
    p_tg.set_defaults(func=cmd_telegram)

    # ── phase ────
    p_phase = subparsers.add_parser("phase", help="Project lifecycle phase management")
    p_phase.add_argument("phase_action", nargs="?", default="show",
                         choices=["show", "set"],
                         help="show (default) or set")
    p_phase.add_argument("phase_value", nargs="?", default=None,
                         help="Phase to set: initial, mid, mid_1, mid_2, late, evolve")
    p_phase.set_defaults(func=cmd_phase)

    # ── feedback ────
    p_fb = subparsers.add_parser("feedback", help="Send user feedback to the AI loop")
    p_fb.add_argument("message", nargs="?", default=None,
                      help="Feedback message")
    p_fb.add_argument("--priority", type=str, default="normal",
                      choices=["low", "normal", "high", "critical"],
                      help="Feedback priority (default: normal)")
    p_fb.add_argument("--list", action="store_true", dest="list_pending",
                      help="List pending feedback")
    p_fb.set_defaults(func=cmd_feedback)

    # ── goal ───────
    p_goal = subparsers.add_parser("goal", help="Manage project goal")
    p_goal.add_argument("goal_action", nargs="?", default="show",
                        choices=["show", "set"],
                        help="show (default) or set")
    p_goal.add_argument("goal_text", nargs="?", default=None,
                        help="Goal text (for set)")
    p_goal.set_defaults(func=cmd_goal)

    # ── git ────────
    p_git = subparsers.add_parser("git", help="Git status and recent commits")
    p_git.set_defaults(func=cmd_git)

    # ── research ────
    p_res = subparsers.add_parser("research", help="Web research via Gemini Search")
    p_res.add_argument("topic", nargs="?", default=None,
                       help="Research topic / search query")
    p_res.add_argument("--context", type=str, default=None,
                       help="Why this research is needed")
    p_res.add_argument("--category", type=str, default="dependencies",
                       choices=["dependencies", "skills", "logic", "errors", "maintenance"],
                       help="KB category to store results (default: dependencies)")
    p_res.add_argument("--list", action="store_true", dest="list_results",
                       help="List recent research results")
    p_res.set_defaults(func=cmd_research)

    # ── metrics ────
    p_metrics = subparsers.add_parser("metrics", help="View cycle performance metrics")
    p_metrics.add_argument("--agents", action="store_true",
                           help="Show per-agent token usage")
    p_metrics.add_argument("--trend", action="store_true",
                           help="Show performance trends")
    p_metrics.add_argument("--last", type=int, default=None,
                           help="Number of recent cycles to show (default: 20)")
    p_metrics.add_argument("--since", type=str, default=None,
                           help="Time filter (e.g. 1h, 6h, 24h, 7d)")
    p_metrics.set_defaults(func=cmd_metrics)

    # ── Parse ─────────────────────────────────────────────────────────────
    args = parser.parse_args()

    if not args.command:
        _setup_env_from_workspace()
        try:
            from adelie.llm_client import get_provider_info
            provider_info = get_provider_info()
        except Exception:
            provider_info = "(not configured)"
        console.print(Panel.fit(
            f"[bold cyan]🐧 Adelie[/bold cyan] — Autonomous AI Loop\n"
            f"[dim]LLM: {provider_info}[/dim]",
            border_style="cyan",
        ))
        parser.print_help()
        return

    args.func(args)


def _dispatch_run(args: argparse.Namespace) -> None:
    """Handle 'adelie run ws <N>' argument parsing."""
    # If ws_keyword is 'ws', use workspace_num
    if args.ws_keyword == "ws" and args.workspace_num is not None:
        pass  # workspace_num is already set
    elif args.ws_keyword == "ws" and args.workspace_num is None:
        console.print("[red]❌ Specify workspace number: adelie run ws <N>[/red]")
        console.print("[dim]Use 'adelie ws' to see available workspaces.[/dim]")
        sys.exit(1)
    elif args.ws_keyword == "once":
        args.once = True
        args.workspace_num = None
    elif args.ws_keyword is not None:
        # Try to parse as workspace number directly
        try:
            args.workspace_num = int(args.ws_keyword)
        except ValueError:
            console.print(f"[red]❌ Unknown argument: {args.ws_keyword}[/red]")
            console.print("[dim]Usage: adelie run [ws <N>] [--goal '...'] [--once][/dim]")
            sys.exit(1)
    else:
        args.workspace_num = None

    cmd_run(args)


if __name__ == "__main__":
    main()
