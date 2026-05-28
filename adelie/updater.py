"""
adelie/updater.py

Update checker for the Adelie CLI.
Checks npm registry for latest version and shows a cute notification.
"""
from __future__ import annotations

import threading


def _fetch_latest_version(timeout: float = 2.5) -> str | None:
    """Fetch latest version from npm registry (non-blocking helper)."""
    try:
        import urllib.request
        import json as _json

        url = "https://registry.npmjs.org/adelie-ai/latest"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = _json.loads(resp.read().decode())
            return data.get("version")
    except Exception:
        return None


def check_for_update(current_version: str, timeout: float = 2.5) -> dict | None:
    """
    Compare current version with latest on npm.
    Returns dict if update available, None if already up-to-date or check failed.
    """
    latest = _fetch_latest_version(timeout=timeout)
    if not latest:
        return None

    try:
        from packaging.version import Version
        is_newer = Version(latest) > Version(current_version)
    except Exception:
        # Fallback: simple string compare
        is_newer = latest != current_version and latest > current_version

    if is_newer:
        return {"current": current_version, "latest": latest}
    return None


def check_for_update_async(current_version: str, callback) -> None:
    """
    Run update check in a background thread.
    Calls callback(result) when done (result is None or dict).
    """
    def _worker():
        result = check_for_update(current_version)
        callback(result)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()


def format_update_notice(current: str, latest: str) -> str:
    """Return a cute, Rich-markup update notification string."""
    return (
        f"\n"
        f"  [bold yellow]Brrr... 🐧 A new version is available![/bold yellow]\n"
        f"  [dim]v{current}[/dim] → [bold cyan]v{latest}[/bold cyan]  "
        f"[dim](A fresh Adelie penguin is waiting for you)[/dim]\n"
        f"\n"
        f"  Run [bold]adelie --update[/bold] to update now ✨\n"
    )


def do_update() -> int:
    """
    Run the update: npm install -g adelie-ai@latest
    Returns exit code.
    """
    import subprocess
    import sys
    from rich.console import Console

    console = Console()
    console.print("\n[bold cyan]🐧 Updating Adelie...[/bold cyan]")
    console.print("[dim]npm install -g adelie-ai@latest[/dim]\n")

    try:
        result = subprocess.run(
            ["npm", "install", "-g", "adelie-ai@latest"],
            check=False,
        )
        if result.returncode == 0:
            console.print("\n[bold green]✅ Update complete! You are now running the cutest version 🐧✨[/bold green]")
            console.print("[dim]Check version: adelie --version[/dim]\n")
        else:
            console.print("\n[bold red]❌ Update failed.[/bold red]")
            console.print("[dim]Try running: npm install -g adelie-ai@latest[/dim]\n")
        return result.returncode
    except FileNotFoundError:
        console.print("[bold red]❌ npm command not found.[/bold red]")
        console.print("[dim]Please install Node.js and try again: https://nodejs.org[/dim]\n")
        return 1
