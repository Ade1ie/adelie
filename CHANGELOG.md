# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.2.13] - 2026-04-09

### Fixed
- **Python 3.9 compatibility** — Fixed a SyntaxError in `_helpers.py` where a backslash was used inside an f-string expression, which is not supported in Python versions older than 3.12.

## [0.2.12] - 2026-03-29

### Fixed
- **Security: Windows shell injection** — `BLOCKED_CHARS` in `runner_ai.py` and `tester_ai.py` now blocks single `&` and `>` characters. Previously only `&&` was blocked, allowing Windows `cmd.exe` command chaining via `&`.
- **Thread safety: `_usage` dict** — Added `_usage_lock` to `llm_client.py` protecting global token counter from race conditions during parallel agent execution.
- **Reviewer approved logic** — Retry limit no longer force-approves rejected code. Previously, `reviewer_approved = True` was set even when the reviewer rejected the code after `MAX_REVIEW_RETRIES`.
- **Staging race condition** — Added `_staging_lock` to `orchestrator.py` preventing concurrent `_promote_staged_files` / `_cleanup_staging` calls from Tester thread and main thread during Phase 3.
- **Windows path traversal** — `coder_ai.py` now uses `Path.resolve()` to verify output paths stay within staging root. Catches Windows absolute paths (`C:\...`) that bypassed the old `/`-prefix check.
- **Windows `python3` stub** — `_verify_staged_files` now uses `sys.executable` on Windows instead of `shutil.which("python3")`, which resolves to the non-functional Microsoft Store stub (`WindowsApps/python3.EXE`).
- **Windows venv activation** — `env_strategy.py` generates `activate.bat &&` wrapper on Windows instead of `source bin/activate`. Also fixed `_wrap_resolver` to use `cmd /c` on Windows.
- **npm_prefix path separator** — Uses `os.sep` instead of hardcoded `/` for cross-platform compatibility.
- **KB `list_categories` glob** — Changed `glob("*")` to `glob("*.md")` so `index.json` and other non-content files are not counted.
- **Writer AI similarity edge case** — Fixed denominator in content similarity check to use `min(len(a), len(b), 200)` instead of just `len(existing_body[:200])`, preventing false positives when new content is much shorter.

### Changed
- **Cross-platform test suite** — Updated `test_env_strategy.py` fixtures and assertions to work on both Windows (Scripts/) and Unix (bin/). 6 previously-failing Windows tests now pass.

## [0.2.11] - 2026-03-28

### Fixed
- **`cmd_init` path resolution** — `adelie init <dir>` now resolves relative to `ADELIE_CWD` (user's actual working directory) instead of `PKG_ROOT` (npm package location). Fixes `init` creating workspaces inside the npm installation directory.

## [0.2.10] - 2026-03-27

### Added
- **GitHub Pages documentation** — Full command reference site at `https://ade1ie.github.io/adelie/` with dark theme, sidebar navigation, installation guides, and phase timeline visualization.

### Fixed
- **CLI execution** — `bin/adelie.js` now runs `python -m adelie.cli` instead of direct file execution, ensuring `sys.path` is correctly set for module imports.

## [0.2.9] - 2026-03-27

### Fixed
- **Module importability** — Added `PYTHONPATH` to `bin/adelie.js` so the `adelie` package is findable when installed via npm global. Fixes `ModuleNotFoundError` on first run.

## [0.2.8] - 2026-03-26

### Added
- **Auto update checker** — `adelie --update` flag checks npm registry for newer versions and offers to upgrade.
- **CI/CD pipeline** — GitHub Actions workflow for automatic npm publish on merge to main.

### Changed
- **CLI refactor** — Split monolithic `cli.py` into `adelie/commands/` package with separate modules for workspace, run, config, monitoring, knowledge, and integrations.

## [0.2.7] - 2026-03-26

### Added
- **ASCII Penguin splash screen**: Replaced the plain version/LLM info panel with a Braille-art Adelie penguin rendered alongside version info in a neofetch-style layout using Rich `Columns` + `Padding`. Appears when running `adelie` with no arguments.

### Changed
- **`__version__` hardcoded**: `adelie/__init__.py` now sets `__version__ = "0.2.7"` as a static string for reliability; dynamic `_get_version()` from `package.json` is retained but no longer used as default.
- **`docs/adelie.rb` updated**: Homebrew formula URL bumped to `adelie-ai-0.2.7.tgz` and sha256 updated with the value from npm publish.

### Fixed
- **`install.sh` macOS/POSIX compatibility**: Replaced `grep -oP` (Perl-regex, GNU only) with `grep -oE` (POSIX ERE) for Python and Node.js version parsing — fixes installation failures on macOS where BSD grep does not support `-P`.
- **`.gitignore` cleanup**: Corrected test-project ignore patterns (`adelie-test-01/`, `adelie_test/`, `gemini-cli-main/`) that were previously misaligned.

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
