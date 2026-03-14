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

console = Console()

# ── Prompts ───────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are Expert AI — the decision-maker in an autonomous AI loop system.

You receive:
1. The current system situation and context.
2. Relevant Knowledge Base files selected for THIS specific situation.

Your job:
1. Read the situation and KB files carefully.
2. Make a structured decision on what action to take.
3. Output a single valid JSON object (no markdown fences, no extra text).

Output format:
{
  "action": "<ACTION_TYPE>",
  "reasoning": "Short explanation of why this action was chosen",
  "commands": ["command1", "command2"],
  "kb_updates_needed": [
    {
      "category": "<category>",
      "filename": "<filename.md>",
      "reason": "Why this KB file needs to be created/updated"
    }
  ],
  "next_situation": "<normal|error|export|maintenance|new_logic>",
  "suggested_phase": "<null or: initial|mid|mid_1|mid_2|late|evolve>",
  "coder_tasks": [
    {
      "layer": 0,
      "name": "coder_identifier",
      "task": "What code to write — be specific and detailed",
      "files": ["src/path/to/relevant/file.py"]
    }
  ],
  "research_queries": [
    {
      "topic": "Search query or research question",
      "context": "Why this information is needed",
      "category": "dependencies"
    }
  ],
  "export_data": null
}

ACTION_TYPE options:
  - CONTINUE       : Normal operation, keep looping. Use this when the KB has enough relevant knowledge.
  - RECOVER        : Error recovery — follow the recovery steps from KB errors/
  - EXPORT         : Write output to exports/ and notify
  - PAUSE          : Request maintenance window
  - NEW_LOGIC      : Bootstrap new knowledge. Use ONLY when the KB is truly empty or missing critical information.
  - SHUTDOWN       : Gracefully stop the loop (only if explicitly needed)

CRITICAL STATE TRANSITION RULES:
- If the current situation is "new_logic" AND knowledge files already exist in the KB, you MUST set next_situation to "normal" and action to "CONTINUE".
- Only keep next_situation as "new_logic" if the KB is completely empty (zero files).
- After Writer AI has written files (you can see them in the KB Index), transition to "normal".
- Do NOT stay in "new_logic" for more than 2-3 cycles. Once basic knowledge exists, move to "normal".
- In "normal" state, focus on expanding and refining knowledge, not re-bootstrapping.

Rules:
- Base decisions on the KB files provided — do not invent facts not in the KB.
- Keep "commands" as concrete, actionable steps the Writer AI should focus on next.
- "export_data" should contain the actual data to export if action is EXPORT, else null.

USER FEEDBACK:
- If "user_feedback" is present in the system state, it contains DIRECT HUMAN INSTRUCTIONS.
- User feedback takes ABSOLUTE PRIORITY over autonomous decisions.
- Address all user feedback items in your commands and coder_tasks.
- If user feedback contradicts your analysis, FOLLOW the user feedback.

PHASE TRANSITION:
- The system may include a "phase_recommendation" in the state, suggesting the next phase.
- If you agree the project is ready, set "suggested_phase" to the recommended value.
- If you disagree, set "suggested_phase" to null and explain WHY in your "reasoning".
- You can also proactively suggest a phase transition even without a recommendation.
- Generally suggest FORWARD transitions (initial → mid → mid_1 → mid_2 → late → evolve).
- However, if the project is in the "evolve" phase, you MAY suggest cycling back to "mid" or "mid_2" for new features or optimizations.

CODER TASKS:
- In MID phase and beyond, you can dispatch coder_tasks to generate actual source code.
- Layer 0: Feature coders. Create one coder per feature (e.g., "backend_login", "frontend_dashboard").
  Be SPECIFIC about what code to write — include tech stack, endpoints, data models.
- Layer 1: Connector coders. Create one coder per domain (e.g., "backend", "frontend").
  These integrate Layer 0 features together — routing, shared state, API connections.
- Layer 2: Infrastructure coders. Deployment, CI/CD, Docker, project configuration.
- In INITIAL phase, set coder_tasks to an empty array [].
- Each coder task must have: layer (0/1/2), name (identifier), task (detailed description).
- ⚠️ CRITICAL: Only assign layers up to the ACTIVE MAX LAYER shown in the system state.
  Tasks assigned to higher layers WILL BE SKIPPED and produce ZERO output.
  If max active layer is 0, ALL tasks MUST be layer 0.

CODER DEDUPLICATION RULES:
- ⚠️ CHECK the "EXISTING CODERS" section below before creating ANY coder task.
- If an existing coder already targets the SAME file or implements the SAME feature, 
  REUSE that coder's exact name instead of creating a new one.
- DO NOT create multiple coders for the same hook, component, or module.
- Example: if "chess_logic_hook" exists, do NOT create "implement_useChessGame_hook".
  Instead, reuse the name "chess_logic_hook".

RESEARCH QUERIES:
- When you need external information (latest docs, API references, best practices, library versions), add research_queries.
- Research AI will perform web searches and store results in the KB for the next cycle.
- Each query: topic (what to search), context (why it's needed), category (KB category to store: dependencies/skills/logic).
- If no external info is needed, set research_queries to an empty array [].
- Use sparingly — each query costs an API call. Max 5 per cycle.
"""

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

    # React/Vite project detection
    has_tsx = any(f.suffix in (".tsx", ".jsx") for f in project_root.rglob("*") if f.is_file())
    has_ts = any(f.suffix == ".ts" for f in project_root.rglob("*") if f.is_file())
    has_pkg = "package.json" in existing

    if has_tsx or has_ts or has_pkg:
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
    valid_actions = {"CONTINUE", "RECOVER", "EXPORT", "PAUSE", "NEW_LOGIC", "SHUTDOWN"}
    if decision.get("action") not in valid_actions:
        return False
    valid_situations = {"normal", "error", "export", "maintenance", "new_logic"}
    if decision.get("next_situation") and decision["next_situation"] not in valid_situations:
        return False
    return True


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

## This Cycle — Writer AI Output
{writer_summary}

## Knowledge Base Index (all available files)
{kb_index}

## Relevant KB Files Loaded for This Situation
{kb_content}

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
