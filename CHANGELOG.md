# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.2.3] - 2026-03-21

### Added
- **State Persistence**: `loop_iteration`, test/review history now saved to `config.json` — Ctrl+C → restart resumes from where you left off
- **Tool Detection for Runner AI**: `shutil.which()` checks which CLI tools are actually installed; Runner AI prompt now includes available/unavailable tools list, preventing commands for missing tools (e.g., Docker)

### Fixed
- **Research AI 401 error**: `web_search.py` now includes `Authorization: Bearer` header for Ollama Cloud API calls


## [0.2.2] - 2026-03-21

### Added
- **AI-Driven Main Goal**: `adelie run` without `--goal` now auto-generates a comprehensive project roadmap from `.adelie/specs/` using LLM
- **Goal System Redesign**: Main Goal (roadmap from specs) + Sub Goal (Expert AI's per-cycle coder_tasks) architecture

### Changed
- `--goal` default removed — no more hardcoded "Operate and improve the Adelie autonomous AI system"
- Workspace resume uses `last_goal` when no `--goal` specified
- Orchestrator accepts `None` goal with graceful fallback

### Fixed
- Ollama Cloud URL in `.env` template corrected to `https://ollama.com`


## [0.2.1] - 2026-03-21

### Added
- **OS Detection**: `adelie init` now auto-detects OS (Windows/macOS/Linux), shell, and architecture
- **OS-specific prompts**: Auto-generates `.adelie/context.md` with English OS-specific command references for all AI agents
  - Windows: PowerShell commands, CRLF handling, Docker Desktop notes
  - macOS: zsh/bash commands, Apple Silicon awareness, Homebrew paths
  - Linux: bash commands, distro detection, native Docker support
- OS info displayed in project file tree header (`project_context.py`)
- New test suite `test_os_detection.py` (14 tests)

### Fixed
- Dashboard `ConnectionAbortedError` on Windows — `handle_error` override on `ThreadingDashboardHTTPServer` silently ignores client-side disconnects instead of printing traceback

## [0.2.0] - 2026-03-18

### Added
- Initial public release on npm (`adelie-ai`)
- Multi-provider LLM support (Gemini, Ollama)
- Knowledge Base system with semantic retrieval
- Expert/Writer/Coder/Reviewer AI agent pipeline
- Project lifecycle phases (initial → mid → late → evolve)
- Real-time web dashboard with SSE
- Spec file auto-sync
- Telegram bot integration
- MCP (Model Context Protocol) support
- Skill registry and A2A communication
