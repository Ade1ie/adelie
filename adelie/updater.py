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
        f"  [bold yellow]꼬르르... 🐧 새 버전이 나왔어요![/bold yellow]\n"
        f"  [dim]v{current}[/dim] → [bold cyan]v{latest}[/bold cyan]  "
        f"[dim](최신 Adelie 펭귄이 기다리고 있어요)[/dim]\n"
        f"\n"
        f"  [bold]adelie --update[/bold]  [dim]로 업데이트할 수 있어요 ✨[/dim]\n"
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
    console.print("\n[bold cyan]🐧 Adelie 업데이트 중...[/bold cyan]")
    console.print("[dim]npm install -g adelie-ai@latest[/dim]\n")

    try:
        result = subprocess.run(
            ["npm", "install", "-g", "adelie-ai@latest"],
            check=False,
        )
        if result.returncode == 0:
            console.print("\n[bold green]✅ 업데이트 완료! 가장 귀여운 버전이 됐어요 🐧✨[/bold green]")
            console.print("[dim]다시 실행: adelie --version[/dim]\n")
        else:
            console.print("\n[bold red]❌ 업데이트 실패했어요.[/bold red]")
            console.print("[dim]직접 실행해보세요: npm install -g adelie-ai@latest[/dim]\n")
        return result.returncode
    except FileNotFoundError:
        console.print("[bold red]❌ npm을 찾을 수 없어요.[/bold red]")
        console.print("[dim]Node.js를 설치한 뒤 다시 시도해주세요: https://nodejs.org[/dim]\n")
        return 1
