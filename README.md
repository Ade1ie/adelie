<p align="center">
  <img src="docs/adelie_logo.jpeg" alt="Adelie Logo" width="200" />
</p>

<h1 align="center">Adelie</h1>

<p align="center">
  <strong>Self-Communicating Autonomous AI Loop System</strong><br/>
  An AI orchestrator that plans, codes, reviews, tests, deploys, and evolves — autonomously.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue?logo=python" alt="Python 3.10+" />
  <img src="https://img.shields.io/badge/LLM-Gemini%20%7C%20Ollama-orange" alt="LLM Support" />
  <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT License" />
  <img src="https://img.shields.io/badge/tests-374%20passed-brightgreen" alt="Tests" />
</p>

---

## What is Adelie?

Adelie is an **autonomous AI loop system** that orchestrates multiple specialized AI agents to build, maintain, and evolve software projects — with minimal human intervention.

Think of it as an AI team that continuously works on your project:

| Agent | Role |
|-------|------|
| **Expert AI** | Makes strategic decisions, dispatches tasks, manages state |
| **Writer AI** | Creates and maintains the Knowledge Base (documentation) |
| **Coder AI** | Writes actual source code in a layered architecture |
| **Reviewer AI** | Reviews code quality, feeds back to coders |
| **Tester AI** | Runs tests, reports failures back for fixes |
| **Runner AI** | Builds, deploys, and runs the project |
| **Monitor AI** | Checks system health, triggers restarts |
| **Analyst AI** | Provides project-level insights and analysis |
| **Research AI** | Searches the web for external information |
| **Scanner AI** | Scans existing codebases on first run |

All agents communicate through a **file-based Knowledge Base** and are coordinated by the **Orchestrator** — an endless loop with a built-in state machine.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   ORCHESTRATOR                       │
│                                                     │
│   ┌──────────┐    ┌──────────┐    ┌──────────────┐ │
│   │ Writer AI│───>│Expert AI │───>│ Coder Manager│ │
│   └──────────┘    └──────────┘    └──────┬───────┘ │
│        │               │                 │         │
│        v               │          ┌──────┴──────┐  │
│   ┌──────────┐         │          │  Layer 0-2  │  │
│   │Knowledge │         │          │   Coders    │  │
│   │   Base   │<────────┘          └──────┬──────┘  │
│   └──────────┘                           │         │
│                                          v         │
│   ┌──────────┐  ┌──────────┐  ┌──────────────────┐│
│   │ Reviewer │  │ Tester   │  │ Runner / Monitor ││
│   │    AI    │  │    AI    │  │       AI         ││
│   └──────────┘  └──────────┘  └──────────────────┘│
│                                                     │
│   ┌──────────────────────────────────────────────┐ │
│   │  Loop Detector │ Scheduler │ Process Supv.   │ │
│   └──────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

---

## Project Lifecycle (Phases)

Adelie evolves your project through 6 phases:

```
INITIAL ──> MID ──> MID_1 ──> MID_2 ──> LATE ──> EVOLVE
Planning    Coding   Testing   Optimizing  Maintaining  Autonomous
```

| Phase | Focus | Coder Layers |
|-------|-------|-------------|
| Initial | Documentation, architecture, roadmap | None |
| Mid | Implementation, feature coding | Layer 0 (features) |
| Mid-1 | Integration, testing, roadmap check | Layer 0-1 (+ connectors) |
| Mid-2 | Stabilization, optimization, deployment | Layer 0-2 (+ infra) |
| Late | Maintenance, new features | All layers |
| Evolve | Autonomous evolution, self-improvement | All layers |

Phase transitions are **gated** by quality metrics (KB file count, test pass rate, review scores) and confirmed by the Expert AI.

---

## Safety Harnesses

Adelie includes multiple built-in safety mechanisms:

| Harness | Purpose |
|---------|---------|
| **Loop Detector** | Detects 5 types of repetitive patterns with escalating interventions |
| **Phase Gates** | Prevents premature transitions with quality thresholds |
| **Context Budget** | Per-agent token budgets prevent unbounded prompt growth |
| **Process Supervisor** | Timeout enforcement, orphan cleanup, concurrent limits |
| **Reviewer Loop** | Code review → feedback → retry cycle (max 2 retries) |
| **Tester Loop** | Test failure → coder fix → re-test cycle (max 2 retries) |
| **Expert Fallback** | JSON retry + regex extraction + safe fallback decision |

---

## Quick Start

### Prerequisites

- **Python 3.10+**
- **Node.js 16+** (for the CLI wrapper)
- **Gemini API key** or **Ollama** running locally

### Installation

```bash
# Install via npm (recommended)
npm install -g adelie

# Or install from source
git clone https://github.com/kimhyunbin/Adelie.git
cd Adelie
npm install -g .
```

### Setup

```bash
# Initialize a workspace in your project directory
cd /path/to/your/project
adelie init

# Configure LLM provider
adelie config --provider gemini --api-key YOUR_GEMINI_API_KEY

# Or use Ollama (local, free)
adelie config --provider ollama --model gemma3:12b

# Set display language (ko or en)
adelie config --lang en
```

### Run

```bash
# Start the autonomous AI loop
adelie run --goal "Build a REST API for task management"

# Or run a single cycle
adelie run once --goal "Analyze and document the codebase"
```

---

## CLI Reference

```
Workspace
  adelie init [dir]              Initialize workspace (default: current dir)
  adelie ws                      List all workspaces
  adelie ws remove <N>           Remove workspace #N

Run
  adelie run --goal "..."        Start AI loop
  adelie run ws <N>              Resume loop in workspace #N
  adelie run once --goal "..."   Run exactly one cycle

Configuration
  adelie config                  Show current config
  adelie config --provider ...   Switch LLM provider (gemini/ollama)
  adelie config --model ...      Set model name
  adelie config --interval N     Set loop interval (seconds)
  adelie config --api-key KEY    Set Gemini API key
  adelie config --lang ko|en     Set display language

Monitoring
  adelie status                  System health & provider status
  adelie inform                  Generate project status report
  adelie phase                   Show current project phase
  adelie phase set <phase>       Set phase manually

Knowledge Base
  adelie kb                      Show KB file counts per category
  adelie kb --clear-errors       Clear error files
  adelie kb --reset              Reset entire KB (destructive)

Project Management
  adelie goal                    Show current project goal
  adelie goal set "..."          Set project goal
  adelie feedback "message"      Send feedback to the AI loop
  adelie research "topic"        Search the web and save to KB
  adelie git                     Show git status & recent commits
  adelie metrics                 Show recent cycle metrics

Ollama
  adelie ollama list             List installed models
  adelie ollama pull <model>     Download a model
  adelie ollama run [model]      Interactive chat

Telegram
  adelie telegram setup          Setup bot token
  adelie telegram start          Start Telegram bot
```

---

## Environment Variables

All settings are stored in `.adelie/.env` (created by `adelie init`):

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `gemini` | `gemini` or `ollama` |
| `GEMINI_API_KEY` | — | Required for Gemini provider |
| `GEMINI_MODEL` | `gemini-2.0-flash` | Gemini model name |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `llama3.2` | Ollama model name |
| `FALLBACK_MODELS` | — | Comma-separated fallback chain (e.g. `gemini:gemini-2.5-flash,ollama:llama3.2`) |
| `LOOP_INTERVAL_SECONDS` | `30` | Seconds between loop cycles |
| `ADELIE_LANGUAGE` | `ko` | Display language (`ko` or `en`) |

---

## Knowledge Base Structure

The KB uses 6 categories:

```
.adelie/workspace/
├── skills/          # How-to guides, procedures, capabilities
├── dependencies/    # External APIs, libraries, services
├── errors/          # Known errors, root causes, recovery
├── logic/           # Decision patterns, planning docs
├── exports/         # Reports, roadmaps, outputs
└── maintenance/     # System health, status updates
```

All KB files are Markdown with tag-based and semantic (embedding) retrieval.

---

## Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_orchestrator.py -v
```

Currently **374 tests** covering all agents, context engine, loop detection, scheduling, and more.

---

## Project Structure

```
Adelie/
├── adelie/                  # Core package
│   ├── orchestrator.py      # Main loop controller (state machine)
│   ├── cli.py               # CLI commands
│   ├── config.py            # Configuration & env loading
│   ├── i18n.py              # Internationalization (ko/en)
│   ├── llm_client.py        # LLM abstraction (Gemini + Ollama)
│   ├── scheduler.py         # Per-agent scheduling
│   ├── phases.py            # Project lifecycle phases
│   ├── hooks.py             # Event-driven plugin system
│   ├── loop_detector.py     # Stuck-loop detection
│   ├── context_engine.py    # Per-agent context assembly
│   ├── context_compactor.py # Token budget enforcement
│   ├── process_supervisor.py# Subprocess management
│   ├── feedback_queue.py    # User feedback injection
│   ├── git_ops.py           # Git auto-commit
│   ├── web_search.py        # Web search for Research AI
│   ├── kb/                  # Knowledge Base
│   │   ├── retriever.py     # Tag + semantic KB retrieval
│   │   └── embedding_store.py
│   ├── agents/              # AI agents
│   │   ├── writer_ai.py     # KB file generation
│   │   ├── expert_ai.py     # Decision-making
│   │   ├── coder_ai.py      # Code generation
│   │   ├── coder_manager.py # Multi-layer coder orchestration
│   │   ├── reviewer_ai.py   # Code review
│   │   ├── tester_ai.py     # Test execution
│   │   ├── runner_ai.py     # Build & deploy
│   │   ├── monitor_ai.py    # Health checks
│   │   ├── analyst_ai.py    # Project analysis
│   │   ├── research_ai.py   # Web research
│   │   ├── scanner_ai.py    # Codebase scanning
│   │   └── inform_ai.py     # Status reports
│   └── integrations/
│       └── telegram_bot.py  # Telegram integration
├── tests/                   # 374 tests
├── bin/                     # Node.js CLI wrapper
├── scripts/                 # Install scripts
├── requirements.txt         # Python dependencies
└── package.json             # npm package config
```

---

## How It Works

Each orchestrator cycle runs these steps:

1. **Writer AI** creates/updates Knowledge Base files
2. **Expert AI** reads the KB and makes a structured decision (JSON)
3. **Research AI** searches the web if the Expert requested external info
4. **Coder Manager** dispatches code generation tasks by layer
5. **Reviewer AI** reviews the generated code; retries on failure
6. **Staging → Project** promotes approved code to the project
7. **Tester AI** runs tests; retries on failure
8. **Runner AI** builds and deploys
9. **Monitor AI** checks health; restarts if needed
10. **Phase Gates** check if the project is ready for the next phase

The loop runs continuously until shutdown, with the **Scheduler** controlling how often each agent runs and the **Loop Detector** intervening when the system gets stuck.

---

## License

MIT — see [LICENSE](./LICENSE) for details.

---

<p align="center">
  Made with Adelie
</p>
