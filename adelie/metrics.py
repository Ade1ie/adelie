"""
adelie/metrics.py

Persistent metrics recording and analysis for the Adelie orchestrator.
Stores per-cycle metrics as JSON Lines (.jsonl) and provides CLI-friendly
analysis tools for performance trending, agent comparison, and anomaly detection.

Storage format: .adelie/metrics/cycles.jsonl
Each line is a self-contained JSON record for one orchestrator cycle.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.table import Table

console = Console()

# ── Metrics Directory ────────────────────────────────────────────────────────

_metrics_dir: Optional[Path] = None


def _get_metrics_dir() -> Path:
    """Get the metrics directory, creating it if needed."""
    global _metrics_dir
    if _metrics_dir is None:
        from adelie.config import ADELIE_ROOT
        _metrics_dir = ADELIE_ROOT / "metrics"
    _metrics_dir.mkdir(parents=True, exist_ok=True)
    return _metrics_dir


def _get_cycles_file() -> Path:
    return _get_metrics_dir() / "cycles.jsonl"


# ── Recording ────────────────────────────────────────────────────────────────


def record_cycle(
    iteration: int,
    phase: str,
    state: str,
    cycle_time: float,
    agent_metrics: dict[str, dict],
    token_usage: dict,
    loop_metrics: dict,
) -> None:
    """
    Append one cycle's metrics to the JSONL file.

    Args:
        iteration:     Loop iteration number.
        phase:         Current project phase.
        state:         Current loop state.
        cycle_time:    Total cycle duration in seconds.
        agent_metrics: Per-agent stats {name: {time, tokens, calls, ...}}.
        token_usage:   Global token usage from llm_client.get_usage().
        loop_metrics:  Additional loop metrics (files, tests, review scores, etc).
    """
    record = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "cycle": iteration,
        "phase": phase,
        "state": state,
        "cycle_time": round(cycle_time, 2),
        "tokens": {
            "prompt": token_usage.get("prompt_tokens", 0),
            "completion": token_usage.get("completion_tokens", 0),
            "total": token_usage.get("total_tokens", 0),
            "calls": token_usage.get("calls", 0),
        },
        "agents": agent_metrics,
        "files_written": loop_metrics.get("files_written", 0),
        "tests": {
            "passed": loop_metrics.get("tests_passed", 0),
            "total": loop_metrics.get("tests_total", 0),
        },
        "review_scores": loop_metrics.get("review_scores", []),
        "parallel": loop_metrics.get("parallel_phases", []),
    }

    try:
        cycles_file = _get_cycles_file()
        with open(cycles_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        console.print(f"[dim]⚠️ Metrics write error: {e}[/dim]")


# ── Reading ──────────────────────────────────────────────────────────────────


def read_cycles(
    since: Optional[datetime] = None,
    last_n: Optional[int] = None,
) -> list[dict]:
    """
    Read cycle records from the JSONL file.

    Args:
        since:  Only include records after this timestamp.
        last_n: Only include the last N records.

    Returns:
        List of cycle dicts, oldest first.
    """
    cycles_file = _get_cycles_file()
    if not cycles_file.exists():
        return []

    records: list[dict] = []
    try:
        with open(cycles_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    if since:
                        ts = datetime.fromisoformat(record.get("ts", ""))
                        if ts < since:
                            continue
                    records.append(record)
                except (json.JSONDecodeError, ValueError):
                    continue
    except Exception:
        return []

    if last_n is not None:
        records = records[-last_n:]

    return records


# ── Analysis ─────────────────────────────────────────────────────────────────


def summary_table(records: list[dict]) -> Table:
    """Build a Rich Table summarizing cycle metrics."""
    table = Table(
        title="📊 Cycle Metrics",
        show_header=True,
        border_style="cyan",
        show_lines=False,
    )
    table.add_column("#", style="bold cyan", justify="right", width=5)
    table.add_column("Time", justify="right", width=8)
    table.add_column("Phase", width=8)
    table.add_column("Tokens", justify="right", width=8)
    table.add_column("Calls", justify="right", width=5)
    table.add_column("Files", justify="right", width=5)
    table.add_column("Tests", width=7)
    table.add_column("⚡Parallel", width=14)
    table.add_column("Timestamp", style="dim", width=19)

    for r in records:
        cycle = str(r.get("cycle", "?"))
        ctime = f"{r.get('cycle_time', 0):.1f}s"
        phase = r.get("phase", "?")
        tokens = f"{r.get('tokens', {}).get('total', 0):,}"
        calls = str(r.get("tokens", {}).get("calls", 0))
        files = str(r.get("files_written", 0))

        tests = r.get("tests", {})
        t_passed = tests.get("passed", 0)
        t_total = tests.get("total", 0)
        test_str = f"{t_passed}/{t_total}" if t_total > 0 else "—"

        parallel = r.get("parallel", [])
        parallel_str = ", ".join(
            f"P{p['phase']}:{p['time']}s" for p in parallel
        ) if parallel else "—"

        ts = r.get("ts", "")[:19].replace("T", " ")

        table.add_row(cycle, ctime, phase, tokens, calls, files, test_str, parallel_str, ts)

    return table


def agent_summary_table(records: list[dict]) -> Table:
    """Build a Rich Table showing per-agent token usage across all cycles."""
    # Aggregate per agent
    agent_totals: dict[str, dict] = {}

    for r in records:
        agents = r.get("agents", {})
        for name, stats in agents.items():
            if name not in agent_totals:
                agent_totals[name] = {"tokens": 0, "calls": 0, "time": 0.0, "cycles": 0}
            agent_totals[name]["tokens"] += stats.get("tokens", 0)
            agent_totals[name]["calls"] += stats.get("calls", 0)
            agent_totals[name]["time"] += stats.get("time", 0.0)
            agent_totals[name]["cycles"] += 1

    table = Table(
        title="🤖 Agent Token Usage",
        show_header=True,
        border_style="green",
    )
    table.add_column("Agent", style="bold")
    table.add_column("Total Tokens", justify="right")
    table.add_column("Calls", justify="right")
    table.add_column("Avg Time", justify="right")
    table.add_column("Cycles", justify="right")

    # Sort by total tokens descending
    for name, totals in sorted(agent_totals.items(), key=lambda x: x[1]["tokens"], reverse=True):
        avg_time = totals["time"] / max(totals["cycles"], 1)
        table.add_row(
            name,
            f"{totals['tokens']:,}",
            str(totals["calls"]),
            f"{avg_time:.1f}s",
            str(totals["cycles"]),
        )

    return table


def trend_summary(records: list[dict]) -> Table:
    """Build a Rich Table showing performance trends."""
    if not records:
        return Table(title="No data")

    total = len(records)
    half = total // 2
    if half == 0:
        half = 1

    first_half = records[:half]
    second_half = records[half:]

    def avg(lst, key):
        vals = [r.get(key, 0) for r in lst if isinstance(r.get(key, 0), (int, float))]
        return sum(vals) / max(len(vals), 1)

    def avg_nested(lst, key1, key2):
        vals = [r.get(key1, {}).get(key2, 0) for r in lst]
        return sum(vals) / max(len(vals), 1)

    table = Table(
        title="📈 Performance Trend",
        show_header=True,
        border_style="yellow",
    )
    table.add_column("Metric", style="bold")
    table.add_column(f"First {len(first_half)} cycles", justify="right")
    table.add_column(f"Last {len(second_half)} cycles", justify="right")
    table.add_column("Change", justify="right")

    metrics = [
        ("Cycle Time (s)", "cycle_time", None),
        ("Tokens/cycle", "tokens.total", "total"),
        ("LLM Calls/cycle", "tokens.calls", "calls"),
    ]

    for label, key, nested_key in metrics:
        if nested_key:
            v1 = avg_nested(first_half, "tokens", nested_key)
            v2 = avg_nested(second_half, "tokens", nested_key)
        else:
            v1 = avg(first_half, key)
            v2 = avg(second_half, key)

        if v1 > 0:
            pct = ((v2 - v1) / v1) * 100
            change_str = f"{pct:+.1f}%"
            if pct > 10:
                change_str = f"[red]{change_str}[/red]"
            elif pct < -10:
                change_str = f"[green]{change_str}[/green]"
        else:
            change_str = "—"

        table.add_row(label, f"{v1:.1f}", f"{v2:.1f}", change_str)

    return table


def get_stats_summary(records: list[dict]) -> dict:
    """Return a stats dict for programmatic use."""
    if not records:
        return {}

    cycle_times = [r.get("cycle_time", 0) for r in records]
    total_tokens = [r.get("tokens", {}).get("total", 0) for r in records]

    return {
        "total_cycles": len(records),
        "avg_cycle_time": round(sum(cycle_times) / len(cycle_times), 1),
        "min_cycle_time": round(min(cycle_times), 1),
        "max_cycle_time": round(max(cycle_times), 1),
        "total_tokens_used": sum(total_tokens),
        "avg_tokens_per_cycle": round(sum(total_tokens) / len(total_tokens)),
        "first_cycle_ts": records[0].get("ts", ""),
        "last_cycle_ts": records[-1].get("ts", ""),
    }
