"""
adelie/commands/knowledge.py

Commands: adelie kb, adelie feedback, adelie goal, adelie research,
          adelie spec, adelie scan
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table

from adelie.commands._helpers import (
    _find_workspace_root,
    _ensure_adelie_config,
    _validate_provider,
)
from adelie.i18n import t

console = Console()


def cmd_kb(args) -> None:
    """Knowledge Base management."""
    _ensure_adelie_config()
    import shutil
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
        console.print(f"[green]OK: Cleared {count} error file(s)[/green]")

    elif args.reset:
        console.print("[yellow]WARN: This will delete ALL Knowledge Base files![/yellow]")
        confirm = input("Type 'yes' to confirm: ")
        if confirm.strip().lower() == "yes":
            for cat_dir in cfg.WORKSPACE_PATH.iterdir():
                if cat_dir.is_dir():
                    shutil.rmtree(cat_dir)
                    cat_dir.mkdir()
            retriever.INDEX_FILE.write_text("{}", encoding="utf-8")
            console.print("[green]OK: Workspace reset complete[/green]")
        else:
            console.print("[dim]Cancelled.[/dim]")

    else:
        categories = retriever.list_categories()
        table = Table(title="Knowledge Base", show_header=True, border_style="green")
        table.add_column("Category", style="bold")
        table.add_column("Files", justify="right")

        total = 0
        for cat, count in categories.items():
            table.add_row(cat, str(count))
            total += count
        table.add_row("── Total ──", str(total), style="bold")

        console.print(table)
        console.print(f"\n[dim]Path: {cfg.WORKSPACE_PATH}[/dim]")


def cmd_feedback(args) -> None:
    """Submit or list user feedback."""
    _ensure_adelie_config()

    from adelie.feedback_queue import submit_feedback, read_pending

    if args.list_pending:
        pending = read_pending()
        if not pending:
            console.print("[green]OK: No pending feedback[/green]")
            return
        table = Table(title="Pending Feedback", show_header=True, border_style="yellow")
        table.add_column("ID", style="bold cyan")
        table.add_column("Priority")
        table.add_column("Message", max_width=50)
        table.add_column("Time")
        for fb in pending:
            prio = fb.get("priority", "normal")
            icon = {"critical": "[!]", "high": "[*]", "normal": "[+]", "low": "[-]"}.get(prio, "[+]")
            table.add_row(
                fb.get("id", "?"),
                f"{icon} {prio}",
                fb.get("message", "")[:50],
                fb.get("timestamp", "")[:16],
            )
        console.print(table)
        return

    if not args.message:
        console.print("[red]ERROR: Provide a message: adelie feedback \"your message\"[/red]")
        console.print("[dim]Or list pending: adelie feedback --list[/dim]")
        return

    submit_feedback(message=args.message, priority=args.priority)


def cmd_goal(args) -> None:
    """Set or show the project goal."""
    _ensure_adelie_config()
    import adelie.config as cfg
    from adelie.kb import retriever

    retriever.ensure_workspace()
    goal_path = cfg.WORKSPACE_PATH / "logic" / "project_goal.md"

    if args.goal_action == "set":
        if not args.goal_text:
            console.print("[red]ERROR: Provide goal text: adelie goal set \"your goal\"[/red]")
            return

        goal_path.parent.mkdir(parents=True, exist_ok=True)
        content = (
            f"# Project Goal\n\n"
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
        console.print(f"[green]OK: Project goal saved![/green]")
        console.print(f"[dim]   {args.goal_text[:80]}[/dim]")
        return

    if goal_path.exists():
        content = goal_path.read_text(encoding="utf-8")
        from rich.markdown import Markdown
        console.print(Markdown(content))
    else:
        console.print("[yellow]No project goal set yet.[/yellow]")
        console.print("[dim]Set one with: adelie goal set \"your goal description\"[/dim]")


def cmd_research(args) -> None:
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
        console.print("[red]ERROR: Provide a topic: adelie research \"your topic\"[/red]")
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
        console.print(f"\n[green]OK: Research saved to KB:[/green] {results[0].get('kb_path', '?')}")
    else:
        console.print("[yellow]No results found.[/yellow]")


def cmd_spec(args) -> None:
    """Load, list, or remove specification files (MD, PDF, DOCX) from KB."""
    _ensure_adelie_config()
    import adelie.config as cfg
    from adelie.kb import retriever
    retriever.ensure_workspace()

    action = args.spec_action

    if action == "load":
        if not args.file_path:
            console.print("[red]ERROR: Provide a file: adelie spec load <file>[/red]")
            return

        file_path = Path(args.file_path).resolve()
        if not file_path.exists():
            console.print(f"[red]ERROR: File not found: {file_path}[/red]")
            return

        from adelie.spec_loader import SUPPORTED_EXTENSIONS, load_spec

        ext = file_path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            console.print(
                f"[red]ERROR: Unsupported format: '{ext}'[/red]\n"
                f"[dim]Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}[/dim]"
            )
            return

        category = args.category or "logic"
        console.print(f"[bold cyan]Loading spec: {file_path.name}[/bold cyan]")
        console.print(f"   [dim]Format: {ext} → Markdown[/dim]")
        console.print(f"   [dim]Category: {category}[/dim]")

        try:
            saved_path = load_spec(
                file_path=file_path,
                workspace_path=cfg.WORKSPACE_PATH,
                category=category,
            )
            from adelie.spec_loader import list_specs
            specs = list_specs(cfg.WORKSPACE_PATH)
            loaded = next((s for s in specs if s["path"] == f"{category}/{saved_path.name}"), None)
            chunk_info = ""
            if loaded and loaded.get("chunks", 0) > 0:
                chunk_info = f" ({loaded['chunks']} chunks)"
            console.print(f"\n[green]OK: Spec loaded → {saved_path.relative_to(cfg.WORKSPACE_PATH)}{chunk_info}[/green]")
        except ImportError as e:
            console.print(f"[red]ERROR: Missing dependency: {e}[/red]")
            console.print("[dim]Run: pip install -r requirements.txt[/dim]")
        except Exception as e:
            console.print(f"[red]ERROR: Failed to load spec: {e}[/red]")

    elif action == "list":
        from adelie.spec_loader import list_specs

        specs = list_specs(cfg.WORKSPACE_PATH)
        if not specs:
            console.print("[dim]No specs loaded yet.[/dim]")
            console.print("[dim]Load one with: adelie spec load <file>[/dim]")
            return

        table = Table(title="Loaded Specifications", show_header=True, border_style="green")
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
            console.print("[red]ERROR: Provide spec name: adelie spec remove <name>[/red]")
            console.print("[dim]Use 'adelie spec list' to see loaded specs.[/dim]")
            return

        from adelie.spec_loader import remove_spec

        if remove_spec(cfg.WORKSPACE_PATH, spec_name):
            console.print(f"[green]OK: Spec '{spec_name}' removed[/green]")
        else:
            console.print(f"[yellow]WARN: Spec '{spec_name}' not found[/yellow]")
            console.print("[dim]Use 'adelie spec list' to see loaded specs.[/dim]")


def cmd_scan(args) -> None:
    """Scan existing codebase and generate KB documentation."""
    _ensure_adelie_config()
    _validate_provider()

    target = Path(args.directory).resolve()

    if not target.is_dir():
        console.print(f"[red]ERROR: Directory not found: {target}[/red]")
        return

    ws_root = _find_workspace_root()
    if not ws_root.exists():
        console.print("[yellow]WARN: No .adelie/ workspace found. Run 'adelie init' first.[/yellow]")
        return

    import adelie.config as cfg
    from adelie.agents.scanner_ai import run_scan

    written = run_scan(
        project_root=target,
        workspace_path=cfg.WORKSPACE_PATH,
    )

    if written:
        console.print(f"\n[bold green]Scan complete — {len(written)} KB document(s) generated[/bold green]")
    else:
        console.print("[yellow]No documents generated. Check if the project has source files.[/yellow]")
