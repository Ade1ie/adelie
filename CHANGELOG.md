# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.2.6] - 2026-03-22

### Added
- **Project File Snapshot in Expert AI**: `_get_project_file_snapshot()` injects real file system state (source file count, total lines, deployment-readiness) into Expert AI's prompt every cycle. Expert now naturally avoids EXPORT/PAUSE when no source code exists.
- **Writer AI Scope Guidance**: `_get_project_file_snapshot_for_writer()` prevents Writer from writing deployment/security docs when no source code exists yet.

### Fixed
- **MID_2 Phase Directive**: Expert AI now explicitly checks source file count before choosing EXPORT — if source_files=0, treats MID_2 as MID and prioritizes coder_tasks.
- **Phase Transition Criteria**: INITIAL→MID now requires at least one coder_task issued. MID_2→LATE now requires source code to exist (>5 files).


## [0.2.5] - 2026-03-22

### Fixed
- **Dashboard blank/Cycle #0**: Critical bug in `interactive.py` — `_setup_logger()` was called before `_start_dashboard()`, so `ds = self._dashboard_state` captured `None`. All dashboard callbacks (`update_cycle`, `update_metrics`, `update_agent`, `add_log`) were silent no-ops. Fixed by (1) moving `_start_dashboard` before `_setup_logger`, (2) using lazy `self._dashboard_state` references inside each callback.


## [0.2.4] - 2026-03-21

### Fixed
- **Windows `[WinError 87]` in Monitor/Runner AI**: `os.kill(pid, 0)` is not supported on Windows. Replaced with `ctypes.windll.kernel32.OpenProcess` for Windows, `os.kill(pid, 0)` for Linux/macOS. Fixes crash in `monitor_ai.py` and `runner_ai.py`.


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
