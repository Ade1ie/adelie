"""
adelie/commands/run.py

Commands: adelie run
Helpers: _sync_specs, _dispatch_run
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console

from adelie.commands._helpers import (
    _find_workspace_root,
    _load_workspace_config,
    _validate_provider,
    _auto_generate_goal,
)
from adelie.i18n import t

console = Console()


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

    manifest_path = specs_dir / ".manifest.json"
    manifest: dict = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            manifest = {}

    new_count = 0
    updated_count = 0

    for file_path in sorted(specs_dir.iterdir()):
        if file_path.is_dir() or file_path.name.startswith("."):
            continue

        ext = file_path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            continue

        file_key = file_path.name
        file_mtime = file_path.stat().st_mtime
        prev_mtime = manifest.get(file_key, {}).get("mtime", 0)

        if file_mtime <= prev_mtime:
            continue

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
            console.print(f"[yellow]WARN: Failed to sync {file_path.name}: {e}[/yellow]")

    if new_count > 0 or updated_count > 0:
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        parts = []
        if new_count:
            parts.append(f"{new_count} new")
        if updated_count:
            parts.append(f"{updated_count} updated")
        console.print(f"[green]  > Auto-synced specs: {', '.join(parts)}[/green]")


def cmd_run(args) -> None:
    """Run the AI loop — either in current workspace or by workspace number."""
    from adelie import registry

    if args.workspace_num is not None:
        ws = registry.get_by_index(args.workspace_num)
        if not ws:
            console.print(f"[red]ERROR: {t('run.ws_not_found', n=args.workspace_num)}[/red]")
            sys.exit(1)

        ws_path = ws["path"]
        adelie_dir = Path(ws_path) / ".adelie"
        if not adelie_dir.exists():
            console.print(f"[red]ERROR: .adelie/ not found in {ws_path}[/red]")
            sys.exit(1)

        import os
        os.environ["ADELIE_CWD"] = ws_path
        os.environ["WORKSPACE_PATH"] = str(adelie_dir / "workspace")

        ws_env_file = adelie_dir / ".env"
        if ws_env_file.exists():
            load_dotenv(ws_env_file, override=True)

        config_path = adelie_dir / "config.json"
        if config_path.exists():
            ws_config = json.loads(config_path.read_text(encoding="utf-8"))
            env_map = {"loop_interval": "LOOP_INTERVAL_SECONDS"}
            for key, env_key in env_map.items():
                if key in ws_config:
                    os.environ[env_key] = str(ws_config[key])

        goal = args.goal
        if not goal and ws.get("last_goal"):
            goal = ws["last_goal"]

        console.print(f"[bold cyan]{t('run.resuming', n=args.workspace_num)}[/bold cyan]")
        console.print(f"   [dim]{ws_path}[/dim]")

        registry.update_last_used(ws_path, goal or "")
    else:
        goal = args.goal
        ws_root = _find_workspace_root()
        if ws_root.exists():
            registry.update_last_used(str(ws_root.parent), goal or "")

    _validate_provider()
    _sync_specs()

    if not goal:
        goal_summary = _auto_generate_goal()
        if goal_summary:
            goal = goal_summary
        else:
            goal = "Autonomously develop and improve the project based on available context"

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


def _dispatch_run(args) -> None:
    """Handle 'adelie run ws <N>' argument parsing."""
    if args.ws_keyword == "ws" and args.workspace_num is not None:
        pass
    elif args.ws_keyword == "ws" and args.workspace_num is None:
        console.print("[red]ERROR: Specify workspace number: adelie run ws <N>[/red]")
        console.print("[dim]Use 'adelie ws' to see available workspaces.[/dim]")
        sys.exit(1)
    elif args.ws_keyword == "once":
        args.once = True
        args.workspace_num = None
    elif args.ws_keyword is not None:
        try:
            args.workspace_num = int(args.ws_keyword)
        except ValueError:
            console.print(f"[red]ERROR: Unknown argument: {args.ws_keyword}[/red]")
            console.print("[dim]Usage: adelie run [ws <N>] [--goal '...'] [--once][/dim]")
            sys.exit(1)
    else:
        args.workspace_num = None

    cmd_run(args)
