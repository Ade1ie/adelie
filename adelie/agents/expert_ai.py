"""
adelie/agents/expert_ai.py

Expert AI agent.
Reads the Knowledge Base situationally and produces structured command
logic / decisions as JSON.
"""

from __future__ import annotations

import json

from rich.console import Console

from adelie.kb import retriever
from adelie.llm_client import generate
from adelie.context_compactor import compact_kb_content, DEFAULT_BUDGET
from adelie.phases import get_phase_prompt
from adelie.rules_loader import get_rules_prompt_section, get_context_prompt_section
from adelie.prompt_loader import load_prompt
from adelie.skill_manager import get_skills_prompt_section
from adelie.tool_registry import get_registry as get_tool_registry

console = Console()

# ── Prompts ───────────────────────────────────────────────────────────────────

_FALLBACK_PROMPT = """You are Expert AI — the decision-maker in an autonomous AI loop system.
Output a single valid JSON object with action, reasoning, commands, and next_situation fields."""

SYSTEM_PROMPT = load_prompt("expert", _FALLBACK_PROMPT)

MAX_JSON_RETRIES = 2


def _get_coder_registry_summary() -> str:
    """코더 레지스트리를 요약 텍스트로 반환."""
    from adelie.config import WORKSPACE_PATH

    registry_path = WORKSPACE_PATH.parent / "coder" / "registry.json"
    if not registry_path.exists():
        return "(No coders registered yet.)"

    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except Exception:
        return "(Registry unreadable.)"

    coders = registry.get("coders", [])
    if not coders:
        return "(No coders registered yet.)"

    lines = [f"Total: {len(coders)} coder(s)"]
    for c in coders[-15:]:  # 최근 15개만 (토큰 절약)
        task_short = c.get("last_task", "")[:80]
        lines.append(
            f"  - [L{c.get('layer', '?')}] {c['name']}: {task_short}"
        )

    if len(coders) > 15:
        lines.insert(1, f"  (showing last 15 of {len(coders)})")

    return "\n".join(lines)


def _get_harness_summary() -> str:
    """Get a summary of the current harness configuration for Expert AI context."""
    try:
        from adelie.harness_manager import get_manager
        hm = get_manager()
        phases = hm.get_all_phases()
        dynamic_agents = hm.get_dynamic_agents()

        lines = [
            f"Current pipeline: {len(phases)} phase(s)",
            "Phases: " + " → ".join(f"{pid}" for pid, _ in phases),
        ]

        if dynamic_agents:
            lines.append(f"Dynamic agents: {len(dynamic_agents)}")
            for agent in dynamic_agents:
                perm = agent.get("permissions", {}).get("level", "analyst")
                lines.append(
                    f"  - {agent['name']} [{perm}] active in: {', '.join(agent.get('active_in_phases', []))}"
                )
        else:
            lines.append("Dynamic agents: none")

        lines.append("")
        lines.append(
            "To modify the pipeline, use action: MODIFY_HARNESS with a harness_payload field containing: "
            "new_phases (list of phase dicts with id, label, order, max_coder_layer, goal, "
            "writer_directive, expert_directive, transition_criteria, next_phase), "
            "new_agents (list of agent configs with name, active_in_phases, prompt_template, "
            "schedule, permissions), remove_phases (list of phase IDs), remove_agents (list of names)."
        )

        return "\n".join(lines)
    except Exception:
        return "(Harness info unavailable)"


def _get_recent_build_errors() -> str:
    """최근 빌드 로그에서 실패 정보 추출."""
    from adelie.config import WORKSPACE_PATH

    runner_dir = WORKSPACE_PATH.parent / "runner"
    if not runner_dir.exists():
        return ""

    # 최신 로그 파일 1개만 읽기
    logs = sorted(runner_dir.glob("build_log_*.md"), reverse=True)
    if not logs:
        return ""

    try:
        content = logs[0].read_text(encoding="utf-8")
    except Exception:
        return ""

    # 실패가 있는 경우만 반환
    if "❌" not in content and "Failed" not in content:
        return ""

    return content[:500]  # 토큰 제한


def _get_project_file_snapshot() -> str:
    """
    Scan the actual project directory and return a reality summary.
    This gives Expert AI ground-truth about what code actually exists,
    preventing premature EXPORT/PAUSE when no source code is present.
    """
    from adelie.config import PROJECT_ROOT

    if not PROJECT_ROOT.exists():
        return "Project directory not found."

    SOURCE_EXTS = {".ts", ".tsx", ".js", ".jsx", ".py", ".go", ".rs", ".java", ".kt", ".swift", ".vue", ".svelte"}
    CONFIG_EXTS = {".json", ".toml", ".yaml", ".yml", ".env", ".cfg", ".ini"}
    SKIP_DIRS = {"node_modules", "__pycache__", ".git", ".adelie", "dist", "build", ".venv", "venv"}

    source_files: list[str] = []
    config_files: list[str] = []
    total_lines = 0

    for path in PROJECT_ROOT.rglob("*"):
        if path.is_file():
            # Skip hidden/build dirs
            parts = set(path.parts)
            if parts & SKIP_DIRS:
                continue
            rel = str(path.relative_to(PROJECT_ROOT))
            if path.suffix in SOURCE_EXTS:
                source_files.append(rel)
                try:
                    total_lines += len(path.read_text(encoding="utf-8", errors="ignore").splitlines())
                except Exception:
                    pass
            elif path.suffix in CONFIG_EXTS:
                config_files.append(rel)

    src_count = len(source_files)
    cfg_count = len(config_files)

    # Determine deployment readiness contextually
    if src_count == 0:
        readiness = "❌ NO SOURCE CODE — implementation has not started"
        advice = (
            "IMPORTANT CONTEXT: There are no source files in the project yet. "
            "EXPORT or PAUSE at this stage provides zero value to the user. "
            "The highest priority is to create coder_tasks to build the actual application."
        )
    elif src_count < 5:
        readiness = f"⚠️ EARLY STAGE — only {src_count} source file(s), scaffolding phase"
        advice = (
            "The project is in early scaffolding. "
            "Prioritize coder_tasks to build core features before any documentation exports."
        )
    elif total_lines < 200:
        readiness = f"🔶 SKELETON — {src_count} files but only {total_lines} total lines"
        advice = "Source files exist but content is minimal. Focus on implementation over exports."
    else:
        readiness = f"✅ CODE EXISTS — {src_count} source file(s), {total_lines:,} lines"
        advice = "Source code is present. Documentation and exports are appropriate."

    # Show up to 10 source files
    sample = source_files[:10]
    sample_str = "\n  ".join(sample) if sample else "(none)"
    if len(source_files) > 10:
        sample_str += f"\n  ... and {len(source_files) - 10} more"

    return f"""## Current Project Reality (File System Snapshot)
Status: {readiness}
Source files: {src_count}  |  Config files: {cfg_count}  |  Total lines: {total_lines:,}

Source files found:
  {sample_str}

{advice}"""

def _detect_framework(project_root) -> str:
    """
    Detect the JS/TS framework used in the project.
    Returns one of: 'nextjs', 'nuxt', 'remix', 'sveltekit', 'angular', 'vite', 'unknown'.
    """
    # Next.js: next.config.js / next.config.mjs / next.config.ts
    for ext in (".js", ".mjs", ".ts"):
        if (project_root / f"next.config{ext}").exists():
            return "nextjs"

    # Nuxt: nuxt.config.ts / nuxt.config.js
    for ext in (".ts", ".js"):
        if (project_root / f"nuxt.config{ext}").exists():
            return "nuxt"

    # Remix: remix.config.js
    if (project_root / "remix.config.js").exists():
        return "remix"

    # SvelteKit: svelte.config.js
    if (project_root / "svelte.config.js").exists():
        return "sveltekit"

    # Angular: angular.json
    if (project_root / "angular.json").exists():
        return "angular"

    # Check package.json dependencies as fallback
    pkg_path = project_root / "package.json"
    if pkg_path.exists():
        try:
            pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
            all_deps = set(pkg.get("dependencies", {}).keys())
            all_deps |= set(pkg.get("devDependencies", {}).keys())

            if "next" in all_deps:
                return "nextjs"
            if "nuxt" in all_deps:
                return "nuxt"
            if "@remix-run/react" in all_deps:
                return "remix"
            if "@sveltejs/kit" in all_deps:
                return "sveltekit"
            if "@angular/core" in all_deps:
                return "angular"
        except Exception:
            pass

    # Vite: vite.config.ts / vite.config.js
    for ext in (".ts", ".js"):
        if (project_root / f"vite.config{ext}").exists():
            return "vite"

    return "unknown"


def _get_scaffolding_need() -> str:
    """
    프로젝트 진입 파일 존재 여부 검사.
    없으면 스캐폴딩 안내 반환, 전부 존재하면 빈 문자열.
    """
    from adelie.config import PROJECT_ROOT, WORKSPACE_PATH

    # Detect project type from KB or existing files
    project_root = PROJECT_ROOT
    if not project_root.exists():
        return ""

    # Gather existing files for detection
    existing = set()
    for f in project_root.iterdir():
        if f.is_file():
            existing.add(f.name.lower())
    src_dir = project_root / "src"
    if src_dir.exists():
        for f in src_dir.iterdir():
            if f.is_file():
                existing.add(f"src/{f.name}".lower())

    # Define scaffolding checks per project type
    checks: list[dict] = []

    has_tsx = any(f.suffix in (".tsx", ".jsx") for f in project_root.rglob("*") if f.is_file())
    has_ts = any(f.suffix == ".ts" for f in project_root.rglob("*") if f.is_file())
    has_pkg = "package.json" in existing

    # ── Framework-aware scaffolding checks ────────────────────────────
    framework = _detect_framework(project_root)

    if framework == "nextjs":
        # Next.js needs: package.json, next.config.*, src/app/layout.tsx or pages/
        entry_files = {
            "package.json": "Node.js dependencies and scripts (npm run dev, npm run build)",
        }
        # Check for app router or pages router
        has_app_router = (
            (src_dir / "app" / "layout.tsx").exists()
            or (src_dir / "app" / "layout.ts").exists()
            or (src_dir / "app" / "layout.jsx").exists()
            or (project_root / "app" / "layout.tsx").exists()
        )
        has_pages_router = (
            (src_dir / "pages").exists()
            or (project_root / "pages").exists()
        )
        if not has_app_router and not has_pages_router:
            entry_files["src/app/layout.tsx"] = "Next.js App Router root layout"
            entry_files["src/app/page.tsx"] = "Next.js App Router home page"

        for fname, desc in entry_files.items():
            path = project_root / fname
            if not path.exists():
                checks.append({"file": fname, "desc": desc})

    elif framework == "nuxt":
        entry_files = {
            "package.json": "Node.js dependencies and scripts",
        }
        has_app_vue = (project_root / "app.vue").exists()
        has_pages = (project_root / "pages").exists()
        if not has_app_vue and not has_pages:
            entry_files["app.vue"] = "Nuxt root App component"

        for fname, desc in entry_files.items():
            path = project_root / fname
            if not path.exists():
                checks.append({"file": fname, "desc": desc})

    elif framework == "sveltekit":
        entry_files = {
            "package.json": "Node.js dependencies and scripts",
        }
        has_routes = (src_dir / "routes").exists()
        if not has_routes:
            entry_files["src/routes/+page.svelte"] = "SvelteKit root page"

        for fname, desc in entry_files.items():
            path = project_root / fname
            if not path.exists():
                checks.append({"file": fname, "desc": desc})

    elif framework in ("remix", "angular"):
        # Minimal checks — just package.json
        if not (project_root / "package.json").exists():
            checks.append({"file": "package.json", "desc": "Node.js dependencies and scripts"})

    elif has_tsx or has_ts or has_pkg:
        # Default: Vite / vanilla React project (original behavior)
        entry_files = {
            "index.html": "Vite entry point — must reference src/main.tsx",
            "package.json": "Node.js dependencies and scripts (npm run build, npm run dev)",
            "tsconfig.json": "TypeScript compiler configuration",
        }
        # Check src/main.tsx or src/main.ts
        has_main = (
            (src_dir / "main.tsx").exists()
            or (src_dir / "main.ts").exists()
            or (src_dir / "main.jsx").exists()
            or (src_dir / "main.js").exists()
            or (src_dir / "index.tsx").exists()
            or (src_dir / "index.ts").exists()
        )
        if not has_main:
            entry_files["src/main.tsx"] = "React root render — ReactDOM.createRoot + App import"

        has_vite_cfg = (
            (project_root / "vite.config.ts").exists()
            or (project_root / "vite.config.js").exists()
        )
        if not has_vite_cfg:
            entry_files["vite.config.ts"] = "Vite build configuration with React plugin"

        for fname, desc in entry_files.items():
            path = project_root / fname
            if not path.exists():
                checks.append({"file": fname, "desc": desc})

    # Python project detection
    has_py = any(f.suffix == ".py" for f in project_root.rglob("*") if f.is_file())
    if has_py and not (has_tsx or has_ts or has_pkg):
        py_entries = {
            "requirements.txt": "Python dependencies",
        }
        for fname, desc in py_entries.items():
            if not (project_root / fname).exists():
                checks.append({"file": fname, "desc": desc})

    # ── tsconfig.json deep validation ─────────────────────────────────
    tsconfig_path = project_root / "tsconfig.json"
    if tsconfig_path.exists():
        try:
            # Strip comments (tsconfig allows // comments)
            raw = tsconfig_path.read_text(encoding="utf-8")
            # Remove single-line comments
            import re as _re
            cleaned = _re.sub(r'//.*$', '', raw, flags=_re.MULTILINE)
            tsconfig = json.loads(cleaned)

            # Check "references" — e.g. [{"path": "./tsconfig.node.json"}]
            for ref in tsconfig.get("references", []):
                ref_path = ref.get("path", "")
                if ref_path:
                    ref_file = project_root / ref_path
                    # If path is a directory, tsconfig.json is implied
                    if not ref_file.exists() and not ref_file.with_suffix(".json").exists():
                        checks.append({
                            "file": ref_path,
                            "desc": f"Referenced by tsconfig.json — must exist or build fails (TS6053)",
                        })

            # Check "extends" — e.g. "./tsconfig.node.json"
            extends = tsconfig.get("extends", "")
            if extends and not extends.startswith("@"):
                ext_file = project_root / extends
                if not ext_file.exists():
                    checks.append({
                        "file": extends,
                        "desc": f"Extended by tsconfig.json — must exist or build fails",
                    })

            # Check "compilerOptions.types" → need @types/* in package.json
            types_list = tsconfig.get("compilerOptions", {}).get("types", [])
            if types_list and has_pkg:
                try:
                    pkg = json.loads((project_root / "package.json").read_text(encoding="utf-8"))
                    all_deps = set(pkg.get("dependencies", {}).keys())
                    all_deps |= set(pkg.get("devDependencies", {}).keys())

                    for type_name in types_list:
                        types_pkg = f"@types/{type_name}"
                        if types_pkg not in all_deps:
                            checks.append({
                                "file": f"package.json (add {types_pkg})",
                                "desc": f"tsconfig requires types '{type_name}' but {types_pkg} not in dependencies (TS2688)",
                            })
                except Exception:
                    pass

        except Exception:
            pass  # tsconfig parse error — skip validation

    if not checks:
        return ""

    lines = [
        "⚠️ CRITICAL: The following entry files are MISSING. Without them, the build WILL FAIL.",
        "Create a 'project_scaffolding' coder task (layer 0) to generate these BEFORE any feature tasks:",
    ]
    for c in checks:
        lines.append(f"  - {c['file']}: {c['desc']}")

    return "\n".join(lines)


def _validate_decision(decision: dict) -> bool:
    """Validate that a decision has required fields with valid values."""
    if not isinstance(decision, dict):
        return False
    if "action" not in decision:
        return False
    valid_actions = {"CONTINUE", "RECOVER", "EXPORT", "PAUSE", "NEW_LOGIC", "SHUTDOWN", "MODIFY_HARNESS"}
    if decision.get("action") not in valid_actions:
        return False
    valid_situations = {"normal", "error", "export", "maintenance", "new_logic"}
    if decision.get("next_situation") and decision["next_situation"] not in valid_situations:
        return False
    return True


def _get_production_health_section() -> str:
    """Get production health context for the Expert AI prompt."""
    try:
        from adelie.config import PRODUCTION_BRIDGE_ENABLED
        if not PRODUCTION_BRIDGE_ENABLED:
            return ""
        from adelie.production_bridge import get_production_bridge
        bridge = get_production_bridge()
        summary = bridge.get_context_summary()
        return summary if summary else ""
    except Exception:
        return ""


def run(
    system_state: dict,
    loop_iteration: int = 0,
    intervention_prompt: str = "",
    writer_output: list[dict] | None = None,
) -> dict:
    """
    Run the Expert AI agent for one cycle.

    Args:
        system_state:   Current orchestrator state dict.
                        Must include 'situation' key.
        loop_iteration: Current loop iteration count.

    Returns:
        Structured decision dict from Expert AI.
    """
    retriever.ensure_workspace()

    situation = system_state.get("situation", "normal")
    console.print(f"[magenta]🧠 Expert AI[/magenta] situation=[bold]{situation}[/bold] — querying KB…")

    # ── Hybrid KB retrieval (tags + semantic embedding) ───────────────────────
    extra_tags = system_state.get("tags", [])
    # Build a semantic query from the current situation context
    goal = system_state.get("goal", "")
    error_msg = system_state.get("error_message", "") or ""
    semantic_text = f"{goal}. Current situation: {situation}. {error_msg}".strip()
    relevant_paths = retriever.semantic_query(
        situation=situation,
        query_text=semantic_text,
        extra_tags=extra_tags or None,
    )

    # Always include project goal file if it exists
    from adelie.config import WORKSPACE_PATH
    goal_path = WORKSPACE_PATH / "logic" / "project_goal.md"
    if goal_path.exists() and goal_path not in relevant_paths:
        relevant_paths.insert(0, goal_path)

    kb_content = retriever.read_files(relevant_paths)
    kb_index = retriever.get_index_summary()

    # Also count all KB files to detect bootstrapped state
    all_categories = retriever.list_categories()
    total_kb_files = sum(all_categories.values())

    console.print(
        f"[magenta]🧠 Expert AI[/magenta] loaded [bold]{len(relevant_paths)}[/bold] KB file(s): "
        + ", ".join(p.relative_to(retriever.WORKSPACE_PATH).as_posix() for p in relevant_paths)
        if relevant_paths else "[magenta]🧠 Expert AI[/magenta] KB is empty — will request bootstrapping."
    )

    # ── Build prompt ──────────────────────────────────────────────────────────
    phase = system_state.get("phase", "initial")
    phase_directive = get_phase_prompt(phase, "expert")
    state_str = json.dumps(system_state, indent=2, ensure_ascii=False)

    # Get active coder layer constraints from phase
    from adelie.phases import PHASE_INFO
    phase_info = PHASE_INFO.get(phase, {})
    max_coder_layer = phase_info.get("max_coder_layer", -1)

    # Build layer constraint message
    if max_coder_layer < 0:
        layer_constraint = "🚫 CODER TASKS ARE DISABLED in this phase. Set coder_tasks to []."
    else:
        active_layers = ", ".join(str(i) for i in range(max_coder_layer + 1))
        layer_constraint = (
            f"✅ ACTIVE CODER LAYERS: [{active_layers}] (max_layer={max_coder_layer})\n"
            f"⚠️ DO NOT assign any coder task with layer > {max_coder_layer} — it WILL BE SKIPPED."
        )

    # Compact KB content to fit token budget
    kb_budget = int(DEFAULT_BUDGET.max_prompt_tokens * DEFAULT_BUDGET.kb_content_share)
    kb_content = compact_kb_content(kb_content, kb_budget)

    # Build writer output summary for this cycle
    writer_summary = ""
    if writer_output:
        writer_lines = [f"Writer AI wrote {len(writer_output)} file(s) this cycle:"]
        for wo in writer_output:
            writer_lines.append(f"  - {wo.get('path', '?')} [{', '.join(wo.get('tags', []))}]: {wo.get('summary', '')}")
        writer_summary = "\n".join(writer_lines)
    else:
        writer_summary = "Writer AI wrote 0 files this cycle."

    user_prompt = f"""{phase_directive}

## Current System State (loop #{loop_iteration})
Situation: {situation}
Total KB files across all categories: {total_kb_files}
{state_str}

## Existing Coders (DO NOT duplicate these)
{_get_coder_registry_summary()}

## Recent Build/Test Errors (fix these in coder_tasks)
{_get_recent_build_errors()}

## Coder Layer Constraints
{layer_constraint}

## ⚠️ Missing Project Entry Files (CREATE THESE FIRST)
{_get_scaffolding_need()}

{_get_project_file_snapshot()}


## This Cycle — Writer AI Output
{writer_summary}
{get_context_prompt_section()}{get_rules_prompt_section()}{get_skills_prompt_section("expert")}{get_tool_registry().get_tools_prompt("expert")}
## Knowledge Base Index (all available files)
{kb_index}

## Relevant KB Files Loaded for This Situation
{kb_content}

## Harness Configuration
{_get_harness_summary()}

{_get_production_health_section()}
Based on the above and the current PROJECT PHASE, what is your decision?
{"IMPORTANT: KB has " + str(total_kb_files) + " files — bootstrapping is done. Set next_situation to 'normal' and action to 'CONTINUE'." if total_kb_files > 0 and situation == "new_logic" else ""}
{intervention_prompt}

{system_state.get('user_feedback_prompt', '')}

Remember: output ONLY a valid JSON object.
"""

    console.print(f"[magenta]🧠 Expert AI[/magenta] generating decision…")

    # Retry loop for JSON parsing failures
    decision = None
    retry_prompt = user_prompt
    for attempt in range(MAX_JSON_RETRIES + 1):
        try:
            raw = generate(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=retry_prompt,
                temperature=0.3,
            )
            decision = json.loads(raw)
            if _validate_decision(decision):
                break
            else:
                console.print(f"[yellow]⚠️  Expert AI response missing required fields (attempt {attempt + 1})[/yellow]")
                if attempt < MAX_JSON_RETRIES:
                    retry_prompt = (
                        user_prompt
                        + "\n\n⚠️ PREVIOUS RESPONSE HAD INVALID STRUCTURE. "
                        "You MUST include 'action' (CONTINUE/RECOVER/EXPORT/PAUSE/NEW_LOGIC/SHUTDOWN) "
                        "and 'next_situation' (normal/error/export/maintenance/new_logic). "
                        "Output ONLY a valid JSON object."
                    )
                    decision = None
                    continue
                return _fallback_decision("Invalid decision structure after retries")
        except json.JSONDecodeError as e:
            console.print(f"[yellow]⚠️  Expert AI returned invalid JSON (attempt {attempt + 1}): {e}[/yellow]")
            if attempt < MAX_JSON_RETRIES:
                # Try extracting JSON from response
                import re
                match = re.search(r'\{.*\}', raw, re.DOTALL)
                if match:
                    try:
                        decision = json.loads(match.group())
                        if _validate_decision(decision):
                            break
                    except json.JSONDecodeError:
                        pass
                retry_prompt = (
                    user_prompt
                    + "\n\n⚠️ PREVIOUS RESPONSE WAS NOT VALID JSON. "
                    "Output ONLY a raw JSON object — no markdown fences, no extra text."
                )
                continue
            return _fallback_decision("JSON parse error from Expert AI model after retries")
        except Exception as e:
            console.print(f"[red]❌ Expert AI error: {e}[/red]")
            raise

    if decision is None:
        return _fallback_decision("Failed to get valid decision after retries")

    # Force transition out of new_logic if KB has content
    if situation == "new_logic" and total_kb_files > 0:
        if decision.get("next_situation") == "new_logic":
            decision["next_situation"] = "normal"
            decision["reasoning"] += " (auto-transitioned to normal: KB has content)"

    # ── Post-process coder tasks: force layer compliance ─────────────────
    coder_tasks = decision.get("coder_tasks", [])
    if coder_tasks and max_coder_layer >= 0:
        fixed = 0
        for task in coder_tasks:
            task_layer = task.get("layer", 0)
            if task_layer > max_coder_layer:
                task["layer"] = max_coder_layer
                fixed += 1
        if fixed:
            console.print(
                f"[yellow]⚠️  Fixed {fixed} coder task(s): "
                f"forced layer ≤ {max_coder_layer} for current phase[/yellow]"
            )
    elif coder_tasks and max_coder_layer < 0:
        # INITIAL phase — remove all coder tasks
        decision["coder_tasks"] = []
        console.print("[dim]⏭  Removed coder tasks — coders disabled in INITIAL phase[/dim]")

    action = decision.get("action", "CONTINUE")
    reasoning = decision.get("reasoning", "")
    console.print(
        f"[magenta]🧠 Expert AI[/magenta] → action=[bold green]{action}[/bold green]  reasoning: {reasoning}"
    )
    return decision


def _fallback_decision(reason: str, last_good: dict | None = None) -> dict:
    """Return a safe fallback decision when Expert AI fails to produce valid output."""
    console.print(f"[yellow]⚠️  Using fallback decision: {reason}[/yellow]")
    next_sit = "normal"
    if last_good:
        # Preserve the last successful decision's state transition
        next_sit = last_good.get("next_situation", "normal")
    return {
        "action": "CONTINUE",
        "reasoning": f"Fallback due to transient error: {reason}. Maintaining last known state.",
        "commands": ["retry_next_cycle"],
        "kb_updates_needed": [],
        "next_situation": next_sit,
        "export_data": None,
    }
