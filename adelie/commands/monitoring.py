"""
adelie/commands/monitoring.py

Commands: adelie status, adelie phase, adelie inform, adelie metrics
"""

from __future__ import annotations

from datetime import datetime

from rich.console import Console
from rich.table import Table

from adelie.commands._helpers import (
    _find_workspace_root,
    _load_workspace_config,
    _save_workspace_config,
    _ensure_adelie_config,
    _validate_provider,
)
from adelie.i18n import t

console = Console()


def cmd_status(args) -> None:
    """Show current system status."""
    _ensure_adelie_config()
    from adelie.llm_client import get_provider_info
    from adelie.kb import retriever
    import adelie.config as cfg

    retriever.ensure_workspace()

    table = Table(title=t('status.title'), show_header=False, border_style="cyan")
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
            console.print(f"[green]OK: {t('status.gemini_ok')}[/green]")
        else:
            console.print(f"[red]ERROR: {t('status.gemini_missing')}[/red]")
    elif cfg.LLM_PROVIDER == "ollama":
        import requests
        try:
            r = requests.get(f"{cfg.OLLAMA_BASE_URL}/api/tags", timeout=3)
            r.raise_for_status()
            models = [m["name"] for m in r.json().get("models", [])]
            console.print(f"[green]OK: {t('status.ollama_ok', n=len(models))}[/green]")
            for m in models:
                marker = "  →" if cfg.OLLAMA_MODEL in m else "   "
                console.print(f"[dim]{marker} {m}[/dim]")
        except Exception:
            console.print(f"[red]ERROR: {t('status.ollama_fail', url=cfg.OLLAMA_BASE_URL)}[/red]")


def cmd_phase(args) -> None:
    """Show or set the current project lifecycle phase."""
    _ensure_adelie_config()
    ws_config = _load_workspace_config()
    from adelie.phases import Phase, get_all_phases, get_phase_label, PHASE_INFO

    if args.phase_action == "set":
        valid = [p.value for p in Phase]
        if args.phase_value not in valid:
            console.print(f"[red]ERROR: Invalid phase. Choose from: {', '.join(valid)}[/red]")
            return
        ws_config["phase"] = args.phase_value
        _save_workspace_config(ws_config)
        label = get_phase_label(args.phase_value)
        console.print(f"[green]OK: Phase set → {label}[/green]")
        return

    current = ws_config.get("phase", "initial")
    phases = get_all_phases()

    console.print(f"\n[bold cyan]Adelie — Project Phase[/bold cyan]\n")

    for value, label in phases:
        if value == current:
            console.print(f"  [bold green]▶ {label}[/bold green]  ← [bold]현재[/bold]")
            info = PHASE_INFO.get(value, {})
            console.print(f"    [dim]목표: {info.get('goal', '')}[/dim]")
            console.print(f"    [dim]전환: {info.get('transition_criteria', '')}[/dim]")
        else:
            console.print(f"  [dim]  {label}[/dim]")

    console.print(f"\n[dim]Change with: adelie phase set <phase>[/dim]")


def cmd_inform(args) -> None:
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
    console.print(f"\n[dim]Full report saved to: {cfg.WORKSPACE_PATH / 'exports' / 'status_report.md'}[/dim]")


def cmd_metrics(args) -> None:
    """Show cycle metrics, agent usage, and performance trends."""
    _ensure_adelie_config()
    from adelie.metrics import read_cycles, summary_table, agent_summary_table, trend_summary, get_stats_summary

    last_n = args.last or 20

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
                console.print(f"[red]ERROR: Invalid --since value: {args.since}[/red]")
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
