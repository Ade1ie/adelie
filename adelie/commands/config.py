"""
adelie/commands/config.py

Commands: adelie config, adelie settings
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

from adelie.commands._helpers import (
    _find_workspace_root,
    _load_workspace_config,
    _save_workspace_config,
    _update_env_file,
    _ensure_adelie_config,
)
from adelie.i18n import t

console = Console()

# ── Settings definitions ──────────────────────────────────────────────────────
# key -> (env_var, config_json_key, default, type, description)
_SETTINGS_DEFS: dict[str, dict] = {
    "dashboard":          {"env": "DASHBOARD_ENABLED",       "cfg": None,           "default": "true",  "type": "bool", "desc": "대시보드 on/off",              "group": "🌐 Dashboard"},
    "dashboard.port":     {"env": "DASHBOARD_PORT",          "cfg": None,           "default": "5042",  "type": "int",  "desc": "대시보드 포트",                "group": "🌐 Dashboard"},
    "loop.interval":      {"env": None,                      "cfg": "loop_interval","default": "30",    "type": "int",  "desc": "루프 간격 (초)",               "group": "⚡ Runtime"},
    "plan.mode":          {"env": "PLAN_MODE",               "cfg": None,           "default": "false", "type": "bool", "desc": "Plan Mode (승인 후 실행)",     "group": "⚡ Runtime"},
    "sandbox":            {"env": "SANDBOX_MODE",            "cfg": None,           "default": "none",  "type": "str",  "desc": "샌드박스 (none/seatbelt/docker)", "group": "⚡ Runtime"},
    "mcp":                {"env": "MCP_ENABLED",             "cfg": None,           "default": "true",  "type": "bool", "desc": "MCP 프로토콜 on/off",          "group": "⚡ Runtime"},
    "browser.search":     {"env": "BROWSER_SEARCH_ENABLED",  "cfg": None,           "default": "true",  "type": "bool", "desc": "브라우저 검색 on/off",         "group": "🔍 Search"},
    "browser.max_pages":  {"env": "BROWSER_SEARCH_MAX_PAGES","cfg": None,           "default": "3",     "type": "int",  "desc": "검색 최대 페이지",             "group": "🔍 Search"},
    "fallback.models":    {"env": "FALLBACK_MODELS",         "cfg": None,           "default": "",      "type": "str",  "desc": "폴백 모델 체인",               "group": "🔄 Fallback"},
    "fallback.cooldown":  {"env": "FALLBACK_COOLDOWN_SECONDS","cfg": None,          "default": "60",    "type": "int",  "desc": "폴백 쿨다운 (초)",             "group": "🔄 Fallback"},
    "language":           {"env": "ADELIE_LANGUAGE",         "cfg": None,           "default": "ko",    "type": "str",  "desc": "언어 (ko/en)",                 "group": "🎨 Display"},
}

_GLOBAL_SETTINGS_FILE = Path.home() / ".adelie" / "settings.json"


def _load_global_settings() -> dict:
    if _GLOBAL_SETTINGS_FILE.exists():
        try:
            return json.loads(_GLOBAL_SETTINGS_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def _save_global_settings(settings: dict) -> None:
    _GLOBAL_SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _GLOBAL_SETTINGS_FILE.write_text(
        json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _read_ws_env_value(env_key: str) -> str | None:
    ws_root = _find_workspace_root()
    env_path = ws_root / ".env"
    if not env_path.exists():
        return None
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith(f"{env_key}="):
            return stripped.split("=", 1)[1].strip()
    return None


def _resolve_setting(key: str, is_global: bool = False) -> tuple[str, str]:
    defn = _SETTINGS_DEFS.get(key)
    if not defn:
        return ("", "unknown")

    if is_global:
        gs = _load_global_settings()
        if key in gs:
            return (str(gs[key]), "global")
        return (defn["default"], "default")

    ws_value = None
    if defn["env"]:
        ws_value = _read_ws_env_value(defn["env"])
    elif defn["cfg"]:
        ws_config = _load_workspace_config()
        if defn["cfg"] in ws_config:
            ws_value = str(ws_config[defn["cfg"]])

    if ws_value is not None:
        return (ws_value, "workspace")

    gs = _load_global_settings()
    if key in gs:
        return (str(gs[key]), "global")

    return (defn["default"], "default")


def cmd_config(args) -> None:
    """View or update configuration."""
    _ensure_adelie_config()
    import adelie.config as cfg
    ws_config = _load_workspace_config()
    env_updates = {}
    config_changed = False

    if args.provider:
        provider = args.provider.lower()
        if provider not in ("gemini", "ollama"):
            console.print("[red]ERROR: Provider must be 'gemini' or 'ollama'[/red]")
            sys.exit(1)
        env_updates["LLM_PROVIDER"] = provider
        console.print(f"[green]OK: provider → {provider}[/green]")

    if args.model:
        provider = env_updates.get("LLM_PROVIDER", cfg.LLM_PROVIDER)
        if provider == "ollama":
            env_updates["OLLAMA_MODEL"] = args.model
            console.print(f"[green]OK: ollama_model → {args.model}[/green]")
        else:
            env_updates["GEMINI_MODEL"] = args.model
            console.print(f"[green]OK: gemini_model → {args.model}[/green]")

    if args.interval:
        ws_config["loop_interval"] = args.interval
        console.print(f"[green]OK: loop_interval → {args.interval}s[/green]")
        config_changed = True

    if args.ollama_url:
        env_updates["OLLAMA_BASE_URL"] = args.ollama_url
        console.print(f"[green]OK: ollama_base_url → {args.ollama_url}[/green]")

    if args.api_key:
        env_updates["GEMINI_API_KEY"] = args.api_key
        console.print("[green]OK: gemini_api_key updated[/green]")

    if args.lang:
        import os
        lang = args.lang.lower()
        if lang not in ("ko", "en"):
            console.print(f"[red]ERROR: {t('config.lang_invalid')}[/red]")
            sys.exit(1)
        env_updates["ADELIE_LANGUAGE"] = lang
        os.environ["ADELIE_LANGUAGE"] = lang
        console.print(f"[green]OK: language → {lang}[/green]")

    if getattr(args, "sandbox", None):
        sbx = args.sandbox.lower()
        if sbx not in ("none", "seatbelt", "docker"):
            console.print("[red]ERROR: Sandbox must be 'none', 'seatbelt', or 'docker'[/red]")
            sys.exit(1)
        env_updates["SANDBOX_MODE"] = sbx
        console.print(f"[green]OK: sandbox_mode → {sbx}[/green]")

    if getattr(args, "plan_mode", None):
        pm = args.plan_mode.lower()
        if pm not in ("true", "false"):
            console.print("[red]ERROR: Plan mode must be 'true' or 'false'[/red]")
            sys.exit(1)
        env_updates["PLAN_MODE"] = pm
        console.print(f"[green]OK: plan_mode → {pm}[/green]")

    if env_updates:
        _update_env_file(env_updates)
    if config_changed:
        _save_workspace_config(ws_config)

    if not env_updates and not config_changed:
        table = Table(title="Adelie Configuration", show_header=True, border_style="blue")
        table.add_column("Setting", style="bold")
        table.add_column("Value")
        table.add_column("Source", style="dim")

        table.add_row("Provider", cfg.LLM_PROVIDER, ".env")
        if cfg.LLM_PROVIDER == "gemini":
            api_key = cfg.GEMINI_API_KEY
            table.add_row("Gemini API Key", "***" + api_key[-4:] if api_key else "(not set)", ".env")
            table.add_row("Gemini Model", cfg.GEMINI_MODEL, ".env")
        table.add_row("Ollama URL", cfg.OLLAMA_BASE_URL, ".env")
        table.add_row("Ollama Model", cfg.OLLAMA_MODEL, ".env")
        table.add_row("Loop Interval", f"{ws_config.get('loop_interval', 30)}s", "config.json")
        table.add_row("Workspace", str(_find_workspace_root()), "")
        table.add_row("Language", cfg.LANGUAGE, ".env")
        table.add_row("Sandbox Mode", cfg.SANDBOX_MODE, ".env")
        table.add_row("Plan Mode", str(cfg.PLAN_MODE_ENABLED), ".env")

        console.print(table)
        ws_root = _find_workspace_root()
        console.print(f"\n[dim]LLM: {ws_root / '.env'}[/dim]")
        from adelie.commands._helpers import _workspace_config_path
        console.print(f"[dim]Config: {_workspace_config_path()}[/dim]")


def cmd_settings(args) -> None:
    """View, update, or reset settings (global or workspace-level)."""
    _ensure_adelie_config()

    action = getattr(args, "settings_action", "show") or "show"
    is_global = getattr(args, "use_global", False)

    if action == "set":
        key = getattr(args, "settings_key", None)
        value = getattr(args, "settings_value", None)
        if not key or value is None:
            console.print("[red]Usage: adelie settings set <key> <value>[/red]")
            return

        if key not in _SETTINGS_DEFS:
            console.print(f"[red]ERROR: Unknown setting: {key}[/red]")
            console.print(f"[dim]Available: {', '.join(sorted(_SETTINGS_DEFS.keys()))}[/dim]")
            return

        defn = _SETTINGS_DEFS[key]

        if defn["type"] == "bool" and value.lower() not in ("true", "false"):
            console.print(f"[red]ERROR: '{key}' must be 'true' or 'false'[/red]")
            return
        if defn["type"] == "int":
            try:
                int(value)
            except ValueError:
                console.print(f"[red]ERROR: '{key}' must be a number[/red]")
                return

        if is_global:
            gs = _load_global_settings()
            gs[key] = value
            _save_global_settings(gs)
            console.print(f"[green]✅ [global] {key} → {value}[/green]")
        else:
            if defn["env"]:
                _update_env_file({defn["env"]: value})
            elif defn["cfg"]:
                ws_config = _load_workspace_config()
                ws_config[defn["cfg"]] = int(value) if defn["type"] == "int" else value
                _save_workspace_config(ws_config)
            console.print(f"[green]✅ [workspace] {key} → {value}[/green]")

    elif action == "reset":
        key = getattr(args, "settings_key", None)
        if not key:
            console.print("[red]Usage: adelie settings reset <key>[/red]")
            return

        if key not in _SETTINGS_DEFS:
            console.print(f"[red]ERROR: Unknown setting: {key}[/red]")
            return

        defn = _SETTINGS_DEFS[key]
        default_val = defn["default"]

        if is_global:
            gs = _load_global_settings()
            gs.pop(key, None)
            _save_global_settings(gs)
            console.print(f"[green]✅ [global] {key} reset (removed)[/green]")
        else:
            if defn["env"]:
                _update_env_file({defn["env"]: default_val})
            elif defn["cfg"]:
                ws_config = _load_workspace_config()
                if defn["type"] == "int":
                    ws_config[defn["cfg"]] = int(default_val)
                else:
                    ws_config[defn["cfg"]] = default_val
                _save_workspace_config(ws_config)
            console.print(f"[green]✅ [workspace] {key} → {default_val} (default)[/green]")

    else:
        scope_label = "Global Settings" if is_global else "Settings (workspace + global)"
        table = Table(
            title=f"Adelie {scope_label}",
            show_header=True,
            border_style="cyan",
        )
        table.add_column("Setting", style="bold")
        table.add_column("Value")
        table.add_column("Source", style="dim")
        table.add_column("Description", style="dim")

        current_group = ""
        for key in _SETTINGS_DEFS:
            defn = _SETTINGS_DEFS[key]
            group = defn["group"]

            if group != current_group:
                if current_group:
                    table.add_row("", "", "", "", style="dim")
                current_group = group
                table.add_row(f"[bold cyan]{group}[/bold cyan]", "", "", "")

            value, source = _resolve_setting(key, is_global)

            if source == "workspace":
                source_styled = "[green]workspace[/green]"
            elif source == "global":
                source_styled = "[yellow]global[/yellow]"
            else:
                source_styled = "[dim]default[/dim]"

            if defn["type"] == "bool":
                value_styled = "[green]true[/green]" if value.lower() == "true" else "[dim]false[/dim]"
            elif not value:
                value_styled = "[dim](not set)[/dim]"
            else:
                value_styled = value

            table.add_row(f"  {key}", value_styled, source_styled, defn["desc"])

        console.print(table)

        if is_global:
            console.print(f"\n[dim]Global: {_GLOBAL_SETTINGS_FILE}[/dim]")
        else:
            ws_root = _find_workspace_root()
            from adelie.commands._helpers import _workspace_config_path
            console.print(f"\n[dim]Workspace: {ws_root / '.env'} + {_workspace_config_path()}[/dim]")
            console.print(f"[dim]Global:    {_GLOBAL_SETTINGS_FILE}[/dim]")

        console.print(f"\n[dim]Change: adelie settings set <key> <value>[/dim]")
        console.print(f"[dim]Global: adelie settings set --global <key> <value>[/dim]")
