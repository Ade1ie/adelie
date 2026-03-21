# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

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
