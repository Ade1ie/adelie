"""
adelie/agents/monitor_ai.py

Monitor AI — watches running services and checks health.

Capabilities:
  - HTTP health checks on configured endpoints
  - Process liveness checks (PID-based)
  - Log file analysis for errors/warnings
  - Generates alerts when issues are detected

Reports saved to .adelie/monitor/
Alerts saved to .adelie/monitor/alerts/
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import requests
from rich.console import Console

from adelie.config import WORKSPACE_PATH, PROJECT_ROOT

console = Console()

MONITOR_ROOT = WORKSPACE_PATH.parent / "monitor"
ALERTS_DIR = MONITOR_ROOT / "alerts"
RUNNER_ROOT = WORKSPACE_PATH.parent / "runner"


def _check_http(url: str, timeout: int = 5) -> dict:
    """Perform an HTTP health check."""
    result = {
        "url": url,
        "status": "unknown",
        "status_code": None,
        "response_ms": None,
    }
    try:
        resp = requests.get(url, timeout=timeout)
        result["status_code"] = resp.status_code
        result["response_ms"] = int(resp.elapsed.total_seconds() * 1000)
        result["status"] = "healthy" if resp.status_code < 400 else "unhealthy"
    except requests.ConnectionError:
        result["status"] = "down"
    except requests.Timeout:
        result["status"] = "timeout"
    except Exception as e:
        result["status"] = f"error: {str(e)[:100]}"

    return result


def _check_process(pid: int) -> bool:
    """Check if a process is still running (cross-platform)."""
    import os
    import sys
    try:
        if sys.platform == "win32":
            import ctypes
            SYNCHRONIZE = 0x00100000
            handle = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, 0, pid)
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            return False
        else:
            os.kill(pid, 0)
            return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


def _load_tracked_processes() -> list[dict]:
    """Load processes tracked by Runner AI."""
    process_file = RUNNER_ROOT / "processes.json"
    if process_file.exists():
        try:
            return json.loads(process_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _scan_log_errors(workspace_root: Path) -> list[str]:
    """Scan recent log files for errors."""
    errors = []
    log_patterns = ["*.log", "*.err"]
    search_dirs = [
        workspace_root,
        workspace_root / "logs",
        RUNNER_ROOT,
    ]

    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        for pattern in log_patterns:
            for log_file in search_dir.glob(pattern):
                try:
                    content = log_file.read_text(encoding="utf-8")
                    lines = content.splitlines()[-50:]  # Last 50 lines
                    for line in lines:
                        lower = line.lower()
                        if any(kw in lower for kw in ["error", "fatal", "critical", "exception", "traceback"]):
                            errors.append(f"{log_file.name}: {line.strip()[:150]}")
                except Exception:
                    pass

    return errors[:20]  # Cap at 20


def run_health_check(
    endpoints: list[str] | None = None,
    workspace_root: Path | None = None,
) -> dict:
    """
    Run comprehensive health checks.

    Args:
        endpoints: HTTP URLs to check. Auto-detects common ports if None.
        workspace_root: project root

    Returns:
        Health check summary.
    """
    if workspace_root is None:
        workspace_root = PROJECT_ROOT

    console.print(f"[bold green]📡 Monitor AI[/bold green] — running health checks")

    MONITOR_ROOT.mkdir(parents=True, exist_ok=True)
    ALERTS_DIR.mkdir(parents=True, exist_ok=True)

    alerts = []
    report_parts = []

    # 1. HTTP Health Checks — discover ports from Runner's tracked processes
    if endpoints is None:
        tracked = _load_tracked_processes()
        # Extract ports from tracked background processes
        discovered_ports = set()
        for proc in tracked:
            port = proc.get("port")
            if port:
                discovered_ports.add(port)
        if discovered_ports:
            endpoints = [f"http://localhost:{p}" for p in sorted(discovered_ports)]
        else:
            # Fallback: check common ports when no processes are tracked
            endpoints = [
                "http://localhost:3000",
                "http://localhost:8000",
            ]

    http_results = []
    for url in endpoints:
        result = _check_http(url)
        http_results.append(result)

        if result["status"] == "healthy":
            console.print(f"  [green]✅ {url}[/green] — {result['response_ms']}ms")
        elif result["status"] == "down":
            console.print(f"  [dim]⬜ {url} — not running[/dim]")
        else:
            console.print(f"  [red]❌ {url} — {result['status']}[/red]")
            if result["status"] not in ("down",):
                alerts.append(f"HTTP {result['status']}: {url}")

    active_services = [r for r in http_results if r["status"] == "healthy"]
    report_parts.append(
        f"### HTTP Endpoints\n"
        f"- Active: {len(active_services)}/{len(http_results)}\n"
    )

    # 2. Process Checks — clean up dead processes
    processes = _load_tracked_processes()
    alive = 0
    dead = 0
    alive_procs = []
    for proc in processes:
        pid = proc.get("pid")
        if pid and _check_process(pid):
            alive += 1
            alive_procs.append(proc)
            console.print(f"  [green]✅ PID {pid}[/green] — {proc.get('description', '?')}")
        else:
            dead += 1

    # Remove dead processes from tracking file
    if dead > 0:
        console.print(f"  [dim]🗑️  Cleaned {dead} dead process(es)[/dim]")
        process_file = RUNNER_ROOT / "processes.json"
        process_file.write_text(json.dumps(alive_procs, indent=2), encoding="utf-8")

    report_parts.append(
        f"### Processes\n"
        f"- Alive: {alive} | Cleaned: {dead}\n"
    )

    # 3. Log Error Scan
    log_errors = _scan_log_errors(workspace_root)
    if log_errors:
        console.print(f"  [yellow]⚠️  Found {len(log_errors)} error(s) in logs[/yellow]")
        alerts.extend(log_errors[:5])
        report_parts.append(
            f"### Log Errors\n"
            + "\n".join(f"- {e}" for e in log_errors[:10])
            + "\n"
        )

    # Determine overall health
    overall = "healthy"
    if alerts:
        overall = "degraded" if len(alerts) <= 3 else "critical"

    health_icon = {"healthy": "🟢", "degraded": "🟡", "critical": "🔴"}.get(overall, "⚪")
    console.print(f"  {health_icon} Overall: {overall}")

    # Save report
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = (
        f"# Health Check — {datetime.now().isoformat(timespec='seconds')}\n"
        f"**Overall**: {health_icon} {overall}\n\n"
        + "\n".join(report_parts)
    )

    if alerts:
        report += "\n### Alerts\n" + "\n".join(f"- ⚠️ {a}" for a in alerts) + "\n"

    (MONITOR_ROOT / f"health_{ts}.md").write_text(report, encoding="utf-8")

    # Save alerts separately if critical
    if overall == "critical":
        alert_report = (
            f"# 🔴 CRITICAL ALERT — {datetime.now().isoformat(timespec='seconds')}\n\n"
            + "\n".join(f"- {a}" for a in alerts)
        )
        (ALERTS_DIR / f"alert_{ts}.md").write_text(alert_report, encoding="utf-8")

    return {
        "overall": overall,
        "active_services": len(active_services),
        "processes_alive": alive,
        "processes_dead": dead,
        "log_errors": len(log_errors),
        "alerts": alerts,
    }
