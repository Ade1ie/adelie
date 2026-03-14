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

RESEARCH QUERIES:
- When you need external information (latest docs, API references, best practices, library versions), add research_queries.
- Research AI will perform web searches and store results in the KB for the next cycle.
- Each query: topic (what to search), context (why it's needed), category (KB category to store: dependencies/skills/logic).
- If no external info is needed, set research_queries to an empty array [].
- Use sparingly — each query costs an API call. Max 5 per cycle.
"""

MAX_JSON_RETRIES = 2


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

## Coder Layer Constraints
{layer_constraint}

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
