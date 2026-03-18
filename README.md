<p align="center">
  <img src="docs/adelie_logo.jpeg" alt="Adelie Logo" width="200" />
</p>

<h1 align="center">Adelie</h1>

<p align="center">
  <strong>Self-Communicating Autonomous AI Loop System</strong><br/>
  An AI orchestrator that plans, codes, reviews, tests, deploys, and evolves — autonomously.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.10+" />
  <img src="https://img.shields.io/badge/LLM-Gemini%20%7C%20Ollama-orange?style=for-the-badge" alt="LLM Support" />
  <img src="https://img.shields.io/badge/license-MIT-green?style=for-the-badge" alt="MIT License" />
  <img src="https://img.shields.io/badge/tests-183%20passed-brightgreen?style=for-the-badge" alt="Tests" />
</p>

<p align="center">
  <a href="#-quick-start">Quick Start</a> ·
  <a href="#-architecture">Architecture</a> ·
  <a href="#-features">Features</a> ·
  <a href="#-cli-reference">CLI</a> ·
  <a href="#-testing">Testing</a> ·
  <a href="#-license">License</a>
</p>

---

## 🤔 What is Adelie?

Adelie is an **autonomous AI loop system** that orchestrates 10 specialized AI agents to build, maintain, and evolve software projects — with minimal human intervention.

Think of it as a full AI development team running 24/7:

```
 🧠 Expert AI    →  Strategic decisions & task dispatch
 ✍️  Writer AI    →  Knowledge Base documentation
 💻 Coder AI     →  Code generation (3-layer architecture)
 🔍 Reviewer AI  →  Code quality review & feedback
 🧪 Tester AI    →  Test execution & failure reporting
 🚀 Runner AI    →  Build & deployment
 📡 Monitor AI   →  System health monitoring
 📊 Analyst AI   →  Project insights & analysis
 🔎 Research AI  →  Web search for external info
 🔬 Scanner AI   →  Codebase scanning on first run
```

All agents communicate through a **file-based Knowledge Base** and are coordinated by the **Orchestrator** — an endless loop with a built-in state machine.

---

## ✨ Features

### 🎯 Core

- **10 Specialized Agents** — Each with a focused role, scheduled independently
- **6-Phase Project Lifecycle** — `INITIAL → MID → MID_1 → MID_2 → LATE → EVOLVE`
- **Layered Code Generation** — Layer 0 (features) → Layer 1 (connectors) → Layer 2 (infra)
- **Knowledge Base** — Tag-based & semantic retrieval across 6 categories
- **Multi-LLM** — Gemini + Ollama with automatic fallback chains

### 🛡️ Safety

- **Loop Detector** — 5 stuck-pattern types with escalating interventions
- **Phase Gates** — Quality-metric thresholds (KB count, test rate, review scores)
- **Context Budget** — Per-agent token limits prevent unbounded growth
- **Process Supervisor** — Timeout enforcement, orphan cleanup, concurrency limits

### 🔌 Extensibility (New in Phase 2-3)

| Feature | Description |
|---------|-------------|
| 💾 **Checkpoint System** | Auto-snapshot before file promotion, instant rollback |
| 🐳 **Docker Sandboxing** | Configurable workspace access, network isolation, security blocklist |
| 🌐 **REST Gateway** | HTTP API: `/api/status`, `/api/tools`, `/api/control` |
| 🧩 **Skill Registry** | Install/update/uninstall skills from Git or local dirs |
| 📡 **Multichannel** | `ChannelProvider` ABC — Discord, Slack, and custom channels |
| 🤝 **A2A Protocol** | Agent-to-Agent HTTP API for external agent integration |
| 🔧 **MCP Support** | Model Context Protocol for external tool ecosystems |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        ORCHESTRATOR                              │
│                                                                  │
│   ┌──────────┐    ┌──────────┐    ┌──────────────┐              │
│   │ Writer AI│───>│Expert AI │───>│ Coder Manager│              │
│   └──────────┘    └──────────┘    └──────┬───────┘              │
│        │               │                 │                       │
│        v               │          ┌──────┴──────┐               │
│   ┌──────────┐         │          │  Layer 0-2  │               │
│   │Knowledge │         │          │   Coders    │               │
│   │   Base   │<────────┘          └──────┬──────┘               │
│   └──────────┘                           │                       │
│                                          v                       │
│   ┌──────────┐  ┌──────────┐  ┌──────────────────┐             │
│   │ Reviewer │  │ Tester   │  │ Runner / Monitor │             │
│   │    AI    │  │    AI    │  │       AI         │             │
│   └──────────┘  └──────────┘  └──────────────────┘             │
│                                                                  │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │ Loop Detector │ Scheduler │ Process Supervisor          │   │
│   ├─────────────────────────────────────────────────────────┤   │
│   │ Checkpoint    │ Sandbox   │ Gateway │ A2A │ Channels    │   │
│   └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🔄 Project Lifecycle

Adelie evolves your project through **6 phases**, each gated by quality metrics:

```
INITIAL ──> MID ──> MID_1 ──> MID_2 ──> LATE ──> EVOLVE
Planning    Code    Test      Optimize  Maintain  Autonomous
```

| Phase | Focus | Coder Layers |
|-------|-------|-------------|
| Initial | Documentation, architecture, roadmap | — |
| Mid | Implementation, feature coding | Layer 0 |
| Mid-1 | Integration, testing | Layer 0-1 |
| Mid-2 | Stabilization, optimization | Layer 0-2 |
| Late | Maintenance, new features | All |
| Evolve | Self-improvement | All |

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.10+**
- **Node.js 16+** (for CLI wrapper)
- **Gemini API key** or **Ollama** running locally

### Installation

```bash
# Install via npm (recommended)
npm install -g adelie-ai

# Or install from source
git clone https://github.com/kimhyunbin/Adelie.git
cd Adelie
pip install -r requirements.txt
npm install -g .
```

### Setup

```bash
# Initialize workspace
cd /path/to/your/project
adelie init

# Configure LLM provider
adelie config --provider gemini --api-key YOUR_GEMINI_API_KEY

# Or use Ollama (local, free)
adelie config --provider ollama --model gemma3:12b
```

### Run

```bash
# Start the autonomous AI loop
adelie run --goal "Build a REST API for task management"

# Single cycle
adelie run once --goal "Analyze and document the codebase"
```

---

## 💻 CLI Reference

```
Workspace
  adelie init [dir]              Initialize workspace
  adelie ws                      List all workspaces
  adelie ws remove <N>           Remove workspace #N

Run
  adelie run --goal "..."        Start AI loop
  adelie run ws <N>              Resume loop in workspace #N
  adelie run once --goal "..."   Run one cycle

Configuration
  adelie config                  Show current config
  adelie config --provider ...   Switch LLM (gemini/ollama)
  adelie config --model ...      Set model name
  adelie config --interval N     Loop interval (seconds)
  adelie config --api-key KEY    Set Gemini API key
  adelie config --lang ko|en     Display language

Monitoring
  adelie status                  System health
  adelie inform                  Project status report
  adelie phase                   Show phase
  adelie phase set <phase>       Set phase manually
  adelie metrics                 Cycle metrics

Knowledge Base
  adelie kb                      KB file counts
  adelie kb --clear-errors       Clear error files
  adelie kb --reset              Reset KB (destructive)

Project
  adelie goal                    Show project goal
  adelie goal set "..."          Set project goal
  adelie feedback "message"      Send feedback to AI loop
  adelie research "topic"        Web search → KB
  adelie git                     Git status & recent commits

Ollama
  adelie ollama list             List models
  adelie ollama pull <model>     Download model
  adelie ollama run [model]      Interactive chat

Telegram
  adelie telegram setup          Setup bot token
  adelie telegram start          Start Telegram bot
```

---

## 🔧 Configuration

### Environment Variables

All settings stored in `.adelie/.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `gemini` | `gemini` or `ollama` |
| `GEMINI_API_KEY` | — | Required for Gemini |
| `GEMINI_MODEL` | `gemini-2.0-flash` | Gemini model |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama URL |
| `OLLAMA_MODEL` | `llama3.2` | Ollama model |
| `FALLBACK_MODELS` | — | Fallback chain (e.g. `gemini:flash,ollama:llama3.2`) |
| `LOOP_INTERVAL_SECONDS` | `30` | Loop interval |
| `ADELIE_LANGUAGE` | `ko` | Display language |

### Docker Sandbox Config

Optional `.adelie/sandbox.json`:

```json
{
  "docker": {
    "image": "adelie-sandbox:latest",
    "workspaceAccess": "rw",
    "network": "none",
    "memoryLimit": "512m",
    "cpuLimit": 1.0,
    "readOnlyRoot": false
  }
}
```

### Skills

Place skills in `.adelie/skills/<name>/SKILL.md`:

```yaml
---
name: react-specialist
description: React/TypeScript best practices
agents: [coder, reviewer]
trigger: auto
---
# Instructions
Use functional components...
```

---

## 🧪 Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Specific modules
python -m pytest tests/test_checkpoint.py -v
python -m pytest tests/test_gateway.py -v
python -m pytest tests/test_a2a.py -v
```

**183 tests** across 8 test suites:

| Suite | Tests | Coverage |
|-------|-------|----------|
| MCP Client | 35 | MCP server connection, tool discovery |
| Tool Registry | 20 | Tool registration, categories, user tools |
| Checkpoint | 16 | Create, restore, prune, metadata |
| Docker Sandbox | 26 | Config, bind safety, Docker wrapping |
| Gateway API | 18 | REST endpoints, auth, CORS |
| Skill Registry | 19 | Install, uninstall, manifest, helpers |
| Multichannel | 24 | Providers, router, broadcast, events |
| A2A Protocol | 25 | Task lifecycle, persistence, HTTP API |

---

## 📁 Project Structure

```
Adelie/
├── adelie/                     # Core package
│   ├── orchestrator.py         # Main loop controller (state machine)
│   ├── cli.py                  # CLI commands
│   ├── config.py               # Configuration & env loading
│   ├── llm_client.py           # LLM abstraction (Gemini + Ollama)
│   ├── checkpoint.py           # 💾 Checkpoint system
│   ├── sandbox.py              # 🐳 Docker/Seatbelt sandboxing
│   ├── gateway.py              # 🌐 REST API gateway
│   ├── skill_manager.py        # 🧩 Skill loading & registry
│   ├── scheduler.py            # Per-agent scheduling
│   ├── phases.py               # Project lifecycle phases
│   ├── hooks.py                # Event-driven plugin system
│   ├── loop_detector.py        # Stuck-loop detection
│   ├── context_engine.py       # Per-agent context assembly
│   ├── process_supervisor.py   # Subprocess management
│   ├── feedback_queue.py       # User feedback injection
│   ├── channels/               # 📡 Multichannel abstraction
│   │   ├── base.py             #   ChannelProvider ABC
│   │   ├── discord.py          #   Discord integration
│   │   ├── slack.py            #   Slack integration
│   │   └── router.py           #   Multi-channel routing
│   ├── a2a/                    # 🤝 Agent-to-Agent protocol
│   │   ├── types.py            #   Task/Event types
│   │   ├── server.py           #   A2A HTTP server
│   │   └── persistence.py      #   Task persistence
│   ├── agents/                 # AI agents (10 specialized)
│   │   ├── expert_ai.py
│   │   ├── writer_ai.py
│   │   ├── coder_ai.py
│   │   ├── reviewer_ai.py
│   │   ├── tester_ai.py
│   │   ├── runner_ai.py
│   │   ├── monitor_ai.py
│   │   ├── analyst_ai.py
│   │   ├── research_ai.py
│   │   └── scanner_ai.py
│   └── kb/                     # Knowledge Base
│       ├── retriever.py
│       └── embedding_store.py
├── tests/                      # 183 tests
├── bin/                        # Node.js CLI wrapper
├── requirements.txt            # Python dependencies
└── package.json                # npm config
```

---

## ⚙️ How It Works

Each orchestrator cycle runs these steps:

1. **Writer AI** creates/updates Knowledge Base files
2. **Expert AI** reads KB and makes structured decisions (JSON)
3. **Research AI** searches the web if requested
4. **Coder Manager** dispatches code generation by layer
5. **Reviewer AI** reviews code; retries on failure
6. **💾 Checkpoint** snapshots current files before promotion
7. **Staging → Project** promotes approved code
8. **Tester AI** runs tests; retries on failure
9. **Runner AI** builds and deploys
10. **Monitor AI** checks health; restarts if needed
11. **Phase Gates** evaluate readiness for next phase

The loop runs continuously with the **Scheduler** controlling agent frequency and the **Loop Detector** intervening when the system gets stuck.

---

## 🗺️ Roadmap

- [x] **Phase 1** — MCP Server Integration
- [x] **Phase 2** — Checkpoint System, Docker Sandboxing, REST Gateway
- [x] **Phase 3** — Skill Registry, Multichannel, A2A Protocol
- [ ] **Phase 4** — VS Code Extension, Web Dashboard, Plugin Marketplace

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit Pull Requests.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Run tests (`python -m pytest tests/ -v`)
4. Commit your changes (`git commit -m 'Add amazing feature'`)
5. Push to the branch (`git push origin feature/amazing-feature`)
6. Open a Pull Request

---

## 📄 License

MIT — see [LICENSE](./LICENSE) for details.

---

<p align="center">
  <sub>Built with 🐧 Adelie — the penguin that codes</sub>
</p>
