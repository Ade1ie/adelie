# 🐧 Adelie — Complete Command Reference

> Comprehensive documentation for all Adelie CLI commands and options.
>
> 🇰🇷 [한국어 버전 →](./COMMANDS.md)

---

## Table of Contents

1. [Installation & Update](#1-installation--update)
2. [Workspace Management](#2-workspace-management)
3. [AI Loop Execution](#3-ai-loop-execution)
4. [Configuration](#4-configuration)
5. [Runtime Settings](#5-runtime-settings)
6. [Monitoring & Status](#6-monitoring--status)
7. [Knowledge Base (KB)](#7-knowledge-base-kb)
8. [Project Management](#8-project-management)
9. [Performance Metrics](#9-performance-metrics)
10. [Ollama Model Management](#10-ollama-model-management)
11. [Telegram Bot](#11-telegram-bot)
12. [Prompt Management](#12-prompt-management)
13. [Tool Registry](#13-tool-registry)
14. [Custom Commands](#14-custom-commands)
15. [Project Phases (Lifecycle)](#15-project-phases-lifecycle)
16. [Environment Variables](#16-environment-variables)
17. [Usage Scenarios](#17-usage-scenarios)

---

## 1. Installation & Update

### Prerequisites

| Requirement | Minimum Version |
|-------------|-----------------|
| Python | 3.10+ |
| Node.js | 16+ |
| LLM Provider | Gemini API Key **or** Ollama |

### Install

```bash
# npm (recommended)
npm install -g adelie-ai

# curl (macOS / Linux)
curl -fsSL https://raw.githubusercontent.com/Ade1ie/adelie/main/install.sh | bash

# PowerShell (Windows)
irm https://raw.githubusercontent.com/Ade1ie/adelie/main/install.ps1 | iex

# Homebrew (macOS / Linux)
brew tap Ade1ie/tap
brew install adelie

# From source
git clone https://github.com/Ade1ie/adelie.git
cd adelie && pip install -r requirements.txt
```

### Update

```bash
# npm
npm install -g adelie-ai@latest

# Homebrew
brew upgrade adelie

# Check version
adelie --version
```

---

## 2. Workspace Management

### `adelie init` — Initialize Workspace

Creates the `.adelie/` directory with Knowledge Base structure.

```bash
adelie init                  # Current directory
adelie init /path/to/project # Specific directory
adelie init --force          # Force reinitialize
```

| Option | Description |
|--------|-------------|
| `[directory]` | Target directory (default: `.`) |
| `--force` | Reinitialize existing `.adelie/` |

**Auto-detected project types:** JavaScript (Node.js, React, Vue, Next.js, etc.), Python, Rust, Go, Java (Maven/Gradle), Ruby (Rails), PHP (Laravel).

### `adelie ws` — List / Manage Workspaces

```bash
adelie ws               # List all registered workspaces
adelie ws remove <N>     # Remove workspace #N
```

---

## 3. AI Loop Execution

### `adelie run` — Start AI Loop

```bash
adelie run --goal "Build a REST API"       # Continuous loop
adelie run once --goal "Analyze codebase"  # Single cycle
adelie run ws 1                            # Resume workspace #1
```

| Option | Description |
|--------|-------------|
| `--goal "text"` | High-level goal for AI agents |
| `--once` | Run exactly one cycle then exit |
| `ws <N>` | Resume from workspace #N |

**Cycle order:** Writer → Expert → Research → Coder Manager → Reviewer → Staging → Tester → Runner → Monitor → Phase Gates

---

## 4. Configuration

### `adelie config` — LLM Configuration

Manages LLM provider, model, API keys, and core settings.

```bash
adelie config                              # Show current config
adelie config --provider gemini            # Switch to Gemini
adelie config --provider ollama            # Switch to Ollama
adelie config --model gemini-2.5-flash     # Set model
adelie config --api-key YOUR_KEY           # Set Gemini API key
adelie config --ollama-url URL             # Set Ollama server URL
adelie config --lang en                    # Set language
adelie config --sandbox docker             # Set sandbox mode
adelie config --plan-mode true             # Enable Plan Mode
```

| Option | Description |
|--------|-------------|
| `--provider` | `gemini` or `ollama` |
| `--model` | Model name |
| `--api-key` | Gemini API key |
| `--ollama-url` | Ollama server URL |
| `--lang` | Language (`ko`, `en`) |
| `--sandbox` | `none`, `seatbelt`, `docker` |
| `--plan-mode` | `true` or `false` |

---

## 5. Runtime Settings

### `adelie settings` — Two-tier Settings Management

Settings are split into **Global** (`~/.adelie/settings.json`) and **Workspace** (`.adelie/.env` + `config.json`).

```
 Priority: Workspace > Global > Default
```

```bash
adelie settings                              # Show all settings
adelie settings --global                     # Show global settings only
adelie settings set dashboard false          # Disable dashboard (workspace)
adelie settings set --global language en     # Set global language
adelie settings reset dashboard.port         # Reset to default
```

| Subcommand | Description |
|------------|-------------|
| `show` (default) | Display all settings with source (workspace/global/default) |
| `set <key> <value>` | Change a setting value |
| `reset <key>` | Reset to default value |

| Option | Description |
|--------|-------------|
| `--global` | Target global settings instead of workspace |

### Available Settings

| Key | Default | Description |
|-----|---------|-------------|
| `dashboard` | `true` | Dashboard on/off |
| `dashboard.port` | `5042` | Dashboard port |
| `loop.interval` | `30` | Loop interval (seconds) |
| `plan.mode` | `false` | Plan Mode (approval before execution) |
| `sandbox` | `none` | Sandbox mode (none/seatbelt/docker) |
| `mcp` | `true` | MCP protocol on/off |
| `browser.search` | `true` | Browser search on/off |
| `browser.max_pages` | `3` | Max search pages |
| `fallback.models` | — | Fallback model chain |
| `fallback.cooldown` | `60` | Fallback cooldown (seconds) |
| `language` | `ko` | Language (ko/en) |

---

## 6. Monitoring & Status

### `adelie status` — System Status

```bash
adelie status
```

Shows LLM connection status, loop interval, workspace path, and KB file counts.

### `adelie inform` — AI Status Report

```bash
adelie inform
adelie inform --goal "Microservice migration"
```

Generates project status report via Inform AI. Saved to `workspace/exports/status_report.md`.

### `adelie phase` — Project Phase

```bash
adelie phase                  # Show current phase
adelie phase set mid_1        # Change phase manually
```

Valid values: `initial`, `mid`, `mid_1`, `mid_2`, `late`, `evolve`

---

## 7. Knowledge Base (KB)

### `adelie kb` — KB Management

```bash
adelie kb                    # File counts by category
adelie kb --clear-errors     # Clear error files only
adelie kb --reset            # Reset entire KB (confirmation required)
```

### `adelie scan` — Codebase Scanner

```bash
adelie scan                          # Scan current directory
adelie scan --directory /path/to/src # Scan specific directory
```

### `adelie spec` — Specification Files

```bash
adelie spec load spec.md                       # Load Markdown
adelie spec load architecture.pdf              # PDF auto-convert
adelie spec load requirements.docx             # DOCX auto-convert
adelie spec load api.pdf --category dependencies
adelie spec list                               # List loaded specs
adelie spec remove spec_my_spec                # Remove spec
```

Supported formats: `.md`, `.pdf`, `.docx`

---

## 8. Project Management

### `adelie goal` — Goal Management

```bash
adelie goal                          # Show current goal
adelie goal set "Build a chat app"   # Set goal
```

### `adelie feedback` — Send Feedback

```bash
adelie feedback "Implement auth first"                    # Normal
adelie feedback "Stop production deploy" --priority critical  # Urgent
adelie feedback --list                                     # List pending
```

### `adelie research` — Web Research

```bash
adelie research "FastAPI WebSocket implementation"
adelie research "Redis caching" --context "high-perf API" --category skills
adelie research --list
```

### `adelie git` — Git Status

```bash
adelie git              # Git status + last 5 commits
```

---

## 9. Performance Metrics

### `adelie metrics` — Cycle Metrics

```bash
adelie metrics                   # Recent cycle metrics
adelie metrics --agents          # Per-agent token usage
adelie metrics --trend           # Performance trends
adelie metrics --last 50         # Last 50 cycles
adelie metrics --since 24h       # Last 24 hours
```

| Option | Description |
|--------|-------------|
| `--agents` | Per-agent token usage breakdown |
| `--trend` | Performance trends (time, tokens, scores) |
| `--last N` | Show last N cycles (default: 20) |
| `--since` | Time filter (`1h`, `6h`, `24h`, `48h`, `7d`) |

---

## 10. Ollama Model Management

```bash
adelie ollama list               # List installed models
adelie ollama pull gemma3:12b    # Download model
adelie ollama remove gemma3:12b  # Remove model
adelie ollama run                # Interactive chat (current model)
adelie ollama run gemma3:12b     # Chat with specific model
```

---

## 11. Telegram Bot

```bash
adelie telegram setup            # Set up bot token (interactive)
adelie telegram start            # Start bot
adelie telegram start --ws 1     # Bind to workspace #1
adelie telegram start --token T  # Override token
```

---

## 12. Prompt Management

### `adelie prompts` — Agent System Prompts

```bash
adelie prompts                   # List available prompts
adelie prompts export            # Export defaults to .adelie/prompts/
adelie prompts reset             # Remove custom prompts (restore defaults)
```

Edit exported prompt files to customize agent behavior.

---

## 13. Tool Registry

### `adelie tools` — Manage Active Tools

```bash
adelie tools                     # List available tools
adelie tools enable <tool>       # Enable a tool
adelie tools disable <tool>      # Disable a tool
```

---

## 14. Custom Commands

### `adelie commands` — User-defined Commands

Place custom scripts in `.adelie/commands/` for auto-detection.

```bash
adelie commands                  # List custom commands
```

---

## 15. Project Phases (Lifecycle)

```
🌱 INITIAL ──▶ 🔨 MID ──▶ 🚀 MID_1 ──▶ ⚡ MID_2 ──▶ 🛡️ LATE ──▶ 🧬 EVOLVE
 Planning      Building    Running      Optimizing    Maintenance   Evolution
```

| Phase | Value | Coder Layers | Goal |
|-------|-------|-------------|------|
| 🌱 Initial | `initial` | — | Vision docs, architecture design |
| 🔨 Mid | `mid` | L0 | Implementation, testing |
| 🚀 Mid 1 | `mid_1` | L0-1 | Execution, roadmap checks |
| ⚡ Mid 2 | `mid_2` | L0-2 | Stabilization, optimization, deploy |
| 🛡️ Late | `late` | L0-2 | Maintenance, new features |
| 🧬 Evolve | `evolve` | L0-2 | Autonomous evolution |

---

## 16. Environment Variables

Configured in `.adelie/.env`.

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `gemini` | `gemini` or `ollama` |
| `GEMINI_API_KEY` | — | Gemini API key |
| `GEMINI_MODEL` | `gemini-2.0-flash` | Gemini model name |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama URL |
| `OLLAMA_MODEL` | `llama3.2` | Ollama model name |
| `FALLBACK_MODELS` | — | Fallback chain (`gemini:flash,ollama:llama3.2`) |
| `FALLBACK_COOLDOWN_SECONDS` | `60` | Cooldown (seconds) |
| `DASHBOARD_ENABLED` | `true` | Dashboard on/off |
| `DASHBOARD_PORT` | `5042` | Dashboard port |
| `PLAN_MODE` | `false` | Plan Mode |
| `SANDBOX_MODE` | `none` | Sandbox mode |
| `MCP_ENABLED` | `true` | MCP protocol |
| `BROWSER_SEARCH_ENABLED` | `true` | Browser search |

---

## 17. Usage Scenarios

### New Project (Gemini)

```bash
mkdir my-app && cd my-app
adelie init
adelie config --provider gemini --api-key YOUR_KEY
adelie goal set "Build a SaaS project management app"
adelie run --goal "Build a SaaS project management app"
```

### Existing Project (Ollama)

```bash
cd /path/to/project
adelie init
adelie config --provider ollama --model gemma3:12b
adelie scan
adelie run once --goal "Analyze codebase and identify improvements"
```

### Settings Management

```bash
# Disable dashboard for this project only
adelie settings set dashboard false

# Set default language for all projects
adelie settings set --global language en

# Review
adelie settings
```

### Multiple Workspaces

```bash
cd ~/projects/frontend && adelie init
cd ~/projects/backend && adelie init
adelie ws
adelie run ws 1
```

---

## Quick Reference

```
┌──────────────────────────────────────────────────────────────┐
│                   🐧 Adelie Quick Reference                  │
├──────────────────────────────────────────────────────────────┤
│  Start      adelie init / config / run --goal "..."          │
│  Settings   adelie settings [set/reset] [--global]           │
│  Status     adelie status / phase / kb / git / metrics       │
│  Project    adelie goal set / feedback / research / scan     │
│  Models     adelie ollama list / pull / run                  │
│  Workspace  adelie ws / run ws <N>                           │
│  Tools      adelie tools / prompts / commands                │
│  Help       adelie help / --version                          │
└──────────────────────────────────────────────────────────────┘
```

---

<p align="center">
  Made with 🐧 by Adelie
</p>
