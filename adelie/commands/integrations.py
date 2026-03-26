"""
adelie/commands/integrations.py

Commands: adelie ollama, adelie telegram, adelie tools,
          adelie prompts, adelie commands, adelie git, adelie help
"""

from __future__ import annotations

import subprocess
import sys

from rich.console import Console
from rich.table import Table

from adelie.commands._helpers import (
    _find_workspace_root,
    _ensure_adelie_config,
)
from adelie.i18n import t

console = Console()


def cmd_help(args) -> None:
    """Show detailed command reference."""
    help_text = """
[bold cyan]Adelie — Command Reference[/bold cyan]

[bold]Workspace[/bold]
  adelie init [dir]                Initialize workspace in directory (default: .)
  adelie ws                        List registered workspaces
  adelie ws remove <N>             Remove workspace N from registry

[bold]Running[/bold]
  adelie run                       Start AI loop (auto-generates goal from specs)
  adelie run --goal "..."          Start with explicit goal
  adelie run ws <N>                Resume workspace N
  adelie run once                  Run a single cycle then exit

[bold]Configuration[/bold]
  adelie config                    Show current configuration
  adelie config --provider <p>     Set LLM provider (gemini/ollama)
  adelie config --model <m>        Set model name
  adelie config --api-key <key>    Set Gemini API key
  adelie config --lang ko|en       Set display language
  adelie settings                  Show all runtime settings
  adelie settings set <key> <val>  Update a setting
  adelie settings set --global ... Update global setting

[bold]Status & Monitoring[/bold]
  adelie status                    Show LLM + KB health
  adelie phase                     Show current lifecycle phase
  adelie phase set <phase>         Change phase manually
  adelie inform                    Generate AI status report
  adelie metrics                   Show cycle performance data
  adelie metrics --agents          Per-agent token breakdown
  adelie metrics --trend           Performance trends

[bold]Knowledge Base[/bold]
  adelie kb                        Show KB file counts
  adelie kb --clear-errors         Delete error files
  adelie kb --reset                Wipe entire KB
  adelie goal                      Show current project goal
  adelie goal set "..."            Set project goal
  adelie feedback "msg"            Send feedback to running loop
  adelie research "topic"          Web research → KB
  adelie spec load <file>          Load spec (MD/PDF/DOCX) → KB
  adelie spec list                 List loaded specs
  adelie scan [--directory .]      Scan codebase → KB docs

[bold]Integrations[/bold]
  adelie ollama list               List installed Ollama models
  adelie ollama pull <model>       Download model
  adelie telegram setup            Configure Telegram bot
  adelie telegram start            Start Telegram bot
  adelie git                       Show git status + log

[bold]Tools & Prompts[/bold]
  adelie tools                     List tool registry
  adelie tools enable <name>       Enable a tool
  adelie tools disable <name>      Disable a tool
  adelie prompts                   List agent prompts
  adelie prompts export            Export default prompts for editing
  adelie prompts reset             Reset custom prompts
  adelie commands                  List custom commands

[dim]Detailed help: adelie <command> --help[/dim]
"""
    console.print(help_text)


def cmd_ollama(args) -> None:
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

            table = Table(title="Ollama Models", show_header=True, border_style="magenta")
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
        except Exception:
            console.print(f"[red]ERROR: Cannot connect to Ollama at {base_url}[/red]")
            console.print("[dim]   Start Ollama with: ollama serve[/dim]")

    elif action == "pull":
        if not args.model_name:
            console.print("[red]ERROR: Specify model: adelie ollama pull <model>[/red]")
            return
        console.print(f"[bold cyan]Pulling model: {args.model_name}[/bold cyan]")
        try:
            subprocess.run(["ollama", "pull", args.model_name], check=True)
            console.print(f"[green]OK: '{args.model_name}' downloaded[/green]")
            console.print(f"[dim]Set as active: adelie config --model {args.model_name}[/dim]")
        except FileNotFoundError:
            console.print("[red]ERROR: 'ollama' not found. Install from: https://ollama.com[/red]")
        except subprocess.CalledProcessError as e:
            console.print(f"[red]ERROR: Failed: {e}[/red]")

    elif action == "remove":
        if not args.model_name:
            console.print("[red]ERROR: Specify model: adelie ollama remove <model>[/red]")
            return
        try:
            subprocess.run(["ollama", "rm", args.model_name], check=True)
            console.print(f"[green]OK: '{args.model_name}' removed[/green]")
        except FileNotFoundError:
            console.print("[red]ERROR: 'ollama' not found.[/red]")
        except subprocess.CalledProcessError as e:
            console.print(f"[red]ERROR: Failed: {e}[/red]")

    elif action == "run":
        model = args.model_name or cfg.OLLAMA_MODEL
        console.print(f"[bold cyan]Chat with: {model}[/bold cyan]")
        try:
            subprocess.run(["ollama", "run", model])
        except FileNotFoundError:
            console.print("[red]ERROR: 'ollama' not found.[/red]")


def cmd_telegram(args) -> None:
    """Telegram bot management."""
    from pathlib import Path
    import json

    action = args.telegram_action

    if action == "setup":
        _ensure_adelie_config()
        from adelie.commands._helpers import _load_workspace_config, _save_workspace_config
        ws_config = _load_workspace_config()

        console.print("[bold cyan]Telegram Bot Setup[/bold cyan]\n")
        console.print("1. Open Telegram and search for [bold]@BotFather[/bold]")
        console.print("2. Send [bold]/newbot[/bold] and follow the instructions")
        console.print("3. Copy the bot token and paste it below\n")

        token = input("Bot Token: ").strip()
        if not token:
            console.print("[red]ERROR: Token cannot be empty[/red]")
            return

        ws_config["telegram_bot_token"] = token
        _save_workspace_config(ws_config)
        console.print("[green]OK: Telegram bot token saved![/green]")
        console.print("[dim]Start with: adelie telegram start[/dim]")

    elif action == "start":
        from adelie import registry

        if args.ws_num:
            ws = registry.get_by_index(args.ws_num)
            if not ws:
                console.print(f"[red]ERROR: Workspace #{args.ws_num} not found.[/red]")
                sys.exit(1)
            ws_path = ws["path"]
        else:
            ws_path = str(_find_workspace_root().parent)

        adelie_dir = Path(ws_path) / ".adelie"
        if not adelie_dir.exists():
            console.print(f"[red]ERROR: .adelie/ not found in {ws_path}[/red]")
            console.print("[dim]Initialize with: adelie init[/dim]")
            sys.exit(1)

        config_path = adelie_dir / "config.json"
        ws_config = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}

        token = args.token or ws_config.get("telegram_bot_token", "")
        if not token:
            console.print("[red]ERROR: No Telegram bot token configured.[/red]")
            console.print("[dim]Run: adelie telegram setup[/dim]")
            sys.exit(1)

        try:
            from adelie.integrations.telegram_bot import AdelieTelegramBot
        except ImportError:
            console.print("[yellow]python-telegram-bot not found — installing…[/yellow]")
            import subprocess as _sp
            _sp.check_call(
                [sys.executable, "-m", "pip", "install", "python-telegram-bot>=20.0"],
                stdout=_sp.DEVNULL,
                stderr=_sp.DEVNULL,
            )
            try:
                from adelie.integrations.telegram_bot import AdelieTelegramBot
            except ImportError:
                console.print(
                    "[bold red]ERROR: python-telegram-bot 설치 실패.[/bold red]\n"
                    "수동 설치: [bold]pip install python-telegram-bot[/bold]"
                )
                sys.exit(1)
            console.print("[green]✅ python-telegram-bot installed.[/green]")

        bot = AdelieTelegramBot(token=token, workspace_path=ws_path)
        bot.start()

    else:
        console.print("[red]ERROR: Unknown action. Use: setup, start[/red]")


def cmd_git(args) -> None:
    """Show git status and recent commits."""
    _ensure_adelie_config()
    import adelie.config as cfg

    from adelie.git_ops import is_git_repo, get_status, get_log

    root = cfg.PROJECT_ROOT

    if not is_git_repo(root):
        console.print(f"[yellow]WARN: {root} is not a git repository.[/yellow]")
        return

    status = get_status(root)
    if status["ok"]:
        if status["changed_files"] == 0:
            console.print("[green]OK: Working tree clean[/green]")
        else:
            console.print(f"[yellow]{status['changed_files']} changed file(s):[/yellow]")
            for f in status["files"]:
                console.print(f"   [dim]{f}[/dim]")
    else:
        console.print(f"[red]ERROR: Git error: {status.get('error', '?')}[/red]")

    log = get_log(n=5, root=root)
    if log:
        console.print("\n[bold]Recent commits:[/bold]")
        for entry in log:
            console.print(f"  [cyan]{entry['hash']}[/cyan] {entry['message']}")


def cmd_commands(args) -> None:
    """List available custom commands."""
    from adelie.command_loader import load_commands

    cmds = load_commands()
    if not cmds:
        console.print("[dim]No custom commands found.[/dim]")
        console.print("[dim]Create .adelie/commands/<name>.md to add custom commands.[/dim]")
        return

    table = Table(title="Custom Commands", show_header=True, border_style="cyan")
    table.add_column("Command", style="bold cyan")
    table.add_column("Description")
    table.add_column("File", style="dim")
    for cmd in cmds:
        table.add_row(f"/{cmd.name}", cmd.description, cmd.path)
    console.print(table)
    console.print("\n[dim]Use /<command-name> [args] in the interactive REPL.[/dim]")


def cmd_tools(args) -> None:
    """Manage tool registry."""
    from adelie.tool_registry import get_registry

    registry = get_registry()
    action = getattr(args, "tools_action", "list")

    if action == "list":
        tools = registry.get_all()
        if not tools:
            console.print("[dim]No tools registered.[/dim]")
            return

        table = Table(title="Tool Registry", show_header=True, border_style="green")
        table.add_column("Name", style="bold")
        table.add_column("Category")
        table.add_column("Description")
        table.add_column("Status")
        table.add_column("Agents", style="dim")

        for tool in tools:
            status = "[green]enabled[/green]" if tool.enabled else "[dim]disabled[/dim]"
            agents = ", ".join(tool.agents) if tool.agents else "all"
            source = "" if tool.builtin else " [cyan](custom)[/cyan]"
            table.add_row(
                f"{tool.name}{source}",
                tool.category.value,
                tool.description[:50],
                status,
                agents,
            )
        console.print(table)

    elif action == "enable":
        name = getattr(args, "tool_name", None)
        if not name:
            console.print("[red]ERROR: Specify tool name: adelie tools enable <name>[/red]")
            return
        if registry.enable(name):
            registry.save_state()
            console.print(f"[green]OK: Tool '{name}' enabled[/green]")
        else:
            console.print(f"[red]ERROR: Tool '{name}' not found[/red]")

    elif action == "disable":
        name = getattr(args, "tool_name", None)
        if not name:
            console.print("[red]ERROR: Specify tool name: adelie tools disable <name>[/red]")
            return
        if registry.disable(name):
            registry.save_state()
            console.print(f"[green]OK: Tool '{name}' disabled[/green]")
        else:
            console.print(f"[red]ERROR: Tool '{name}' not found[/red]")


def cmd_prompts(args) -> None:
    """Manage agent system prompts."""
    from adelie.prompt_loader import list_prompts, export_prompts, reset_prompts

    action = getattr(args, "action", "list")

    if action == "list":
        prompts = list_prompts()
        if not prompts:
            console.print("[dim]No prompt files found.[/dim]")
            return
        table = Table(title="Agent Prompts", show_header=True, border_style="cyan")
        table.add_column("Agent", style="bold")
        table.add_column("Source")
        table.add_column("Path", style="dim")
        for p in prompts:
            source_style = "[green]user[/green]" if p["source"] == "user" else "[dim]package[/dim]"
            table.add_row(p["agent"], source_style, p["path"])
        console.print(table)
        console.print("\n[dim]To customize: adelie prompts export, then edit .adelie/prompts/<agent>.md[/dim]")

    elif action == "export":
        exported = export_prompts()
        if exported:
            console.print(f"[green]Exported {len(exported)} prompt(s):[/green]")
            for p in exported:
                console.print(f"  {p}")
            console.print("\n[dim]Edit them in .adelie/prompts/ to customize.[/dim]")
        else:
            console.print("[yellow]No new prompts to export (already exist or no .adelie dir).[/yellow]")

    elif action == "reset":
        removed = reset_prompts()
        if removed:
            console.print(f"[green]Reset {len(removed)} custom prompt(s) to defaults.[/green]")
        else:
            console.print("[dim]No custom prompts to reset.[/dim]")
