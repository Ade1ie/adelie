# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).
## [0.3.0] - 2026-04-09

**Major Release — AI Harness Architecture**

v0.3.0 transforms Adelie from a static pipeline executor into a self-configuring, policy-enforced, production-aware AI harness. This release consolidates v0.2.16–v0.2.20 into a single major version.

### Added

#### 🔧 Meta Harness — Dynamic Pipeline (from v0.2.16)
- **HarnessManager** (`harness_manager.py`) — Dynamic JSON state machine replaces static 6-phase Enum. Expert AI reconfigures pipeline at runtime via `MODIFY_HARNESS` action.
- **DynamicAgent** (`agents/dynamic_agent.py`) — Runtime-created agents with 3-tier permissions (observer → analyst → operator).
- **Snapshot Rollback** — Every harness modification creates automatic backup; failed changes auto-revert.

#### 🛡️ Policy Engine — Declarative Constraints (from v0.2.17)
- **PolicyEngine** (`policy_engine.py`) — Enforces `.adelie/constraints.yaml` rules. Three types: `pattern` (regex), `ast` (Python AST), `file` (line limits).
- **AST Checker** (`utils/ast_checker.py`) — Detects `eval()`, `exec()`, wildcard imports, missing docstrings.
- **PolicyGate** — Blocks staging promotion on violation; forces Coder retry loop.

#### 🧠 Memory Harness — Selective Forgetting (from v0.2.18)
- **MemoryHarness** (`memory_harness.py`) — Phase-aware KB visibility to prevent context derailment.
- **Phase Scope Filter** — KB files tagged with `phase_scope` only visible during designated phases.
- **Archive Manager** — Resolved errors and completed-phase docs auto-archived. Summary Tree preserves minimal awareness.

#### 📡 Production Bridge — CI/CD Feedback Loop (from v0.2.19)
- **ProductionBridge** (`production_bridge.py`) — Connects to GitHub Actions, Sentry, and custom MCP servers.
- **SignalCollector + HealthVerdict** — Aggregates signals into `healthy`/`degraded`/`critical` verdict.
- **Auto-Rollback** — Critical verdict transitions to `LoopState.ERROR` + KB error log + hotfix generation.

#### ⛔ Human Intercept & Monitoring (from v0.2.20)
- **`/intercept [reason]`** — Immediate mid-cycle stop + ERROR state + KB logging.
- **`/policy`**, **`/health`**, **`/memory`**, **`/harness`** — Dedicated CLI commands for each feature.
- **`/status` enhanced** — Full system status with all feature indicators.
- **Dashboard overhaul** — Intercept button, Production Health panel, Policy Engine panel, Memory Harness panel, Pipeline Visualizer, Feature SSE events.

### Changed
- **Orchestrator** — Integrated all 5 harness components (HarnessManager, PolicyGate, MemoryHarness, ProductionBridge, Intercept).
- **Expert AI** — New `MODIFY_HARNESS` action, production health context injection, harness summary in prompt.
- **Coder/Reviewer AI** — Policy constraint summaries injected into prompts.
- **KB Retriever** — Phase-aware `query()` and `semantic_query()`.
- **Context Engine** — Archive summary injection (5% budget).
- **Cycle Header** — Feature indicators (🛡️ 📡 🧠).
- **Dashboard** — Complete redesign with feature panels, SSE events, intercept API.

---

## [0.2.20] - 2026-04-09

### Added
- **`/intercept [reason]`** CLI command — Immediately stops the AI mid-cycle, transitions to `ERROR` state, records reason in KB, and pauses. Unlike `/pause`, takes effect between agents rather than at cycle boundary.
- **`/policy`** CLI command — Shows Policy Engine status and all loaded constraint rules.
- **`/health`** CLI command — Shows Production Bridge verdict, active adapters, and recent signals.
- **`/memory`** CLI command — Shows Memory Harness statistics (active/archived/scoped files).
- **`/harness`** CLI command — Shows pipeline structure, phase flow, and dynamic agents.
- **`orchestrator.intercept()`** — Programmatic intercept method for external control.
- **`orchestrator.get_feature_status()`** — Unified status API for all v0.2.16-0.2.19 features.
- **Dashboard: Intercept Button** — Emergency ⛔ button in header with confirmation modal, calls `POST /api/intercept`.
- **Dashboard: Production Health Panel** — Real-time verdict badge (HEALTHY/DEGRADED/CRITICAL) with adapter list.
- **Dashboard: Policy Engine Panel** — Active rule count and type breakdown.
- **Dashboard: Memory Harness Panel** — Active/archived/scoped file counters.
- **Dashboard: Pipeline Visualizer** — Horizontal phase flow with active/completed highlighting.
- **Dashboard: `features` SSE event** — Pushes feature status on every cycle start.
- **Dashboard: `/api/features` endpoint** — REST API for feature status.
- **Dashboard: `POST /api/intercept` endpoint** — REST API for remote intercept.

### Changed
- **`/status`** — Now shows full system status including Policy Engine, Memory Harness, Production Bridge, and Pipeline info.
- **Cycle Header** — Enhanced with feature indicators (🛡️ rules, 📡 health, 🧠 memory stats).
- **Help Text** — Updated with all new commands.

## [0.2.19] - 2026-04-09

### Added
- **Production Bridge** (`production_bridge.py`) — Connects the AI harness loop to external CI/CD and monitoring services. Collects signals, determines `HealthVerdict` (healthy/degraded/critical), and triggers automatic ERROR rollback + hotfix generation.
- **GitHub Actions Adapter** — Polls workflow run statuses via REST API or MCP server. Detects CI failures and feeds them back as critical signals.
- **Sentry Adapter** — Polls error issues via REST API or MCP server. Detects error spikes above configurable threshold.
- **Custom MCP Adapter** — Discovers MCP tools matching production patterns (monitor, health, status, alert) and polls them automatically.
- **`PRODUCTION_ALERT` HookEvent** — New hook for external service alerts, enabling custom plugin responses.
- **40 new tests** (`test_production_bridge.py`) — Data models, all 3 adapters (mocked API), SignalCollector, verdict engine, hook integration.

### Changed
- **Orchestrator** — Polls Production Bridge at cycle start. Critical verdict → `LoopState.ERROR` + KB error log + hook emission + critical acknowledgment.
- **Expert AI** — Production health context summary injected into prompt when bridge is active.
- **Config** — `PRODUCTION_BRIDGE_ENABLED` (default: false), `PRODUCTION_POLL_INTERVAL` (default: 60s).

## [0.2.18] - 2026-04-09

### Added
- **Memory Harness — Selective Forgetting** (`memory_harness.py`) — Controls KB visibility per phase to prevent context derailment. Three mechanisms: Phase Scope Filter, Archive Manager, and Summary Tree.
- **Phase Scope Filter** — KB files tagged with `phase_scope` in index.json are only visible during their designated phases. Files without scope remain globally visible (backward compatible).
- **Archive Manager** — Resolved errors (stale for 3+ cycles) and completed-phase documents are automatically moved to `archive/` directory, removing them from active queries.
- **Summary Tree** — Archived files get a 1-2 line summary preserved in `archive/summaries.md`, giving agents minimal awareness of past context without loading full documents.
- **26 new tests** (`test_memory_harness.py`) — Phase groups, scope filtering, auto-tagging, staleness detection, archiving, summary tree, retriever integration.

### Changed
- **KB Retriever** — `query()` and `semantic_query()` now accept `current_phase` parameter for phase-aware filtering. Backward compatible: omitting the parameter returns all files.
- **Context Engine** — `assemble_context()` now injects archived knowledge summaries (5% budget) so agents retain minimal historical awareness.
- **Orchestrator** — Phase transitions trigger automatic KB archiving via Memory Harness hooks. Cycle-end maintenance archives stale error files.

## [0.2.17] - 2026-04-09

### Added
- **Declarative Policy Engine** (`policy_engine.py`) — Enforces project-specific constraints from `.adelie/constraints.yaml`. Supports three rule types: `pattern` (regex), `ast` (Python AST analysis), and `file` (line count limits). Violations with severity `block` prevent code promotion.
- **PolicyGate** — New deterministic checkpoint in the orchestrator pipeline between Reviewer AI and staging promotion. Blocks code that violates declared constraints, with automatic Coder retry loop on violation.
- **AST Checker** (`utils/ast_checker.py`) — Python AST-based static analysis: detects forbidden calls (`eval`, `exec`, `compile`), wildcard imports (`from X import *`), and missing docstrings on public functions/classes.
- **Negative Pattern Support** — Rules can define `negative_pattern` to suppress false positives (e.g., `requests.get()` with `timeout=` parameter passes).
- **Policy Prompt Injection** — Active constraints from `constraints.yaml` are injected into both Coder AI and Reviewer AI prompts for violation prevention at generation time.
- **39 new tests** (`test_policy_engine.py`) — Pattern matching, AST checks, file rules, PolicyReport, YAML parser, language detection.

### Changed
- **Orchestrator promotion gate** — Now requires `reviewer_approved AND policy_passed` before promoting staged files. PolicyGate failure triggers Coder feedback retry.
- **Coder AI** — Receives active policy constraint summary in its prompt context.
- **Reviewer AI** — Receives active policy constraint summary alongside its normal review context.

## [0.2.16] - 2026-04-09

### Added
- **Meta Harness Architecture** — Transitioned from a static 6-phase Enum pipeline to a dynamic JSON-based state machine (`harness.json`). Expert AI can now autonomously reconfigure the project pipeline at runtime via the `MODIFY_HARNESS` action.
- **HarnessManager** (`harness_manager.py`) — Core manager that loads/saves/validates harness configurations, supports snapshot-based rollback, and provides declarative JSON transition criteria evaluation.
- **DynamicAgent** (`agents/dynamic_agent.py`) — Runtime-configurable agent class. Roles, prompts, and constraints are defined in `harness.json` and instantiated on-the-fly during pipeline execution.
- **3-Tier Permission Model** — Dynamic agents follow `observer` → `analyst` → `operator` permission escalation. Default is `analyst` (KB read/write + export); `operator` (coder task creation) requires explicit grant.
- **Harness Rollback** — Every harness modification creates an automatic snapshot in `harness_history/`. Failed modifications auto-rollback; CLI can manually rollback via stored snapshots.
- **Dynamic Phase Transitions** — Phase transition logic moved from hardcoded lambda functions to declarative JSON conditions (`min_loops`, `min_kb_files`, `required_files`, `min_test_pass_rate`, `min_review_score`).
- **Orchestrator Phase 5** — New execution phase for dynamic agents that are active in the current pipeline phase, with full scheduler integration.

### Changed
- **`phases.py` → Compatibility Shim** — `Phase` Enum and `PHASE_INFO` dict are now proxied through `HarnessManager`. All 17+ existing import points continue to work unchanged.
- **`_check_phase_readiness()`** — Refactored from hardcoded transition map to `HarnessManager.check_transition()` with JSON-based declarative conditions.
- **Expert AI Output Schema** — Added `MODIFY_HARNESS` action type and `harness_payload` field to the expert decision format.
- **Phase Transition Logic** — `orchestrator.py` now supports dynamically added phases (not just the base 6) for `suggested_phase` transitions.

## [0.2.15] - 2026-04-09

### Fixed
- **Testing & Sandbox Paths** — Added proper shell-quoting around interpolated directory paths to prevent testing and sandbox environment failures when the project directory contains spaces. 
- **Configuration Reloading Bug** — Transitioned `WORKSPACE_PATH` and `PROJECT_ROOT` direct module imports to dynamic property lookups in `tester_ai.py`, `runner_ai.py`, and `sandbox.py` to correctly reflect CLI context updates.
- **Version Integrity** — Synchronized `pyproject.toml` and `docs/index.html` to reflect the current deployment version alongside global builds.

## [0.2.14] - 2026-04-09

### Fixed
- **Testing suite stability** — Fixed test failures caused by `ModuleNotFoundError` for Playwright on environments where it's not installed, and handling for `TimeoutError` in Python 3.9 during parallel execution tests.

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
