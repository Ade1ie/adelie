"""
adelie/phases.py

Project Lifecycle Phase System.

Defines the 5 macro-phases of an Adelie project and provides
phase-specific behavior directives for Writer AI and Expert AI.
"""

from __future__ import annotations

from enum import Enum


class Phase(str, Enum):
    """Project lifecycle phases — from idea to autonomous evolution."""

    INITIAL   = "initial"      # 초기: 문서화, 정보 수집, 로드맵 설계
    MID       = "mid"          # 중기: 프로덕션 구현, 테스트, 코드 고도화
    MID_1     = "mid_1"        # 중기 1기: 실행, 로드맵 체크, 테스트
    MID_2     = "mid_2"        # 중기 2기: 안정화, 최적화, 배포
    LATE      = "late"         # 후기: 유지보수, 새 기능, 로드맵 확장
    EVOLVE    = "evolve"       # 자율 발전: AI가 스스로 판단하여 발전


# ── Phase metadata ────────────────────────────────────────────────────────────

PHASE_INFO: dict[str, dict] = {
    Phase.INITIAL: {
        "label": "초기 — Planning & Documentation",
        "max_coder_layer": -1,  # No coders in planning phase
        "env_strategies": ["direct"],
        "goal": "프로덕션의 구상과 로드맵 작성. 스스로 생각하는 프로덕션의 비전을 문서화.",
        "writer_directive": """PHASE: INITIAL (초기)
Your focus in this phase:
1. Create comprehensive documentation about the project concept
2. Research and document required technologies, APIs, and dependencies
3. Design the system architecture and write it to skills/
4. Create a detailed ROADMAP file (exports/roadmap.md) with milestones
5. Identify risks and unknowns — document them in logic/
6. DO NOT write implementation code yet — focus on planning and design

Priority files to create:
- skills/project_vision.md — What the product does, target users, key features
- skills/architecture.md — System design, tech stack, component diagram
- dependencies/tech_stack.md — Required libraries, services, APIs
- logic/decision_log.md — Key design decisions and rationale
- exports/roadmap.md — Phased roadmap with milestones and success criteria""",

        "expert_directive": """PHASE: INITIAL (초기)
Your decision criteria in this phase:
- Prioritize DOCUMENTATION and PLANNING over implementation
- Keep requesting NEW_LOGIC until: project vision, architecture, roadmap all exist
- Transition to "normal" once documentation foundation is solid
- Suggest EXPORT when the roadmap is ready for user review
- Do NOT suggest code implementation — that's for the mid phase
- Check if these KB files exist: project_vision, architecture, roadmap
- If any are missing, request them via kb_updates_needed""",

        "transition_criteria": "Transition to MID when: roadmap.md exists, architecture is documented, at least 5 KB files exist, AND at least one coder_task has been issued (even scaffolding).",
    },

    Phase.MID: {
        "label": "중기 — Implementation & Testing",
        "max_coder_layer": 0,  # Layer 0 only: feature coders
        "env_strategies": ["direct"],
        "goal": "프로덕션 완벽 구현. 코드 작성, 테스트, 코드 고도화.",
        "writer_directive": """PHASE: MID (중기)
Your focus in this phase:
1. Break down the roadmap into implementable tasks in logic/
2. Write implementation guides and code patterns in skills/
3. Document test strategies and quality criteria
4. Track implementation progress against the roadmap
5. Update dependencies/ as new libraries/services are integrated
6. Log any issues or blockers in errors/

Priority files to create/update:
- logic/implementation_plan.md — Current sprint tasks broken from roadmap
- skills/coding_standards.md — Code patterns and best practices
- logic/test_strategy.md — What to test and how
- exports/progress_report.md — Implementation progress vs roadmap""",

        "expert_directive": """PHASE: MID (중기)
Your decision criteria in this phase:
- Focus on IMPLEMENTATION progress tracking
- Check implementation_plan.md against roadmap milestones
- Request code quality and testing documentation
- Use EXPORT to generate progress reports
- Transition to normal/continue to keep development moving
- If blocked, log issues and suggest alternatives

CODER TASK RULES FOR MID PHASE:
- ⚠️ ONLY Layer 0 is active. ALL coder_tasks MUST have "layer": 0.
- Do NOT assign layer 1 or layer 2 — they will produce ZERO output.
- ⚠️ FIRST CYCLE SCAFFOLDING: If project entry files (index.html, src/main.tsx,
  vite.config.ts, package.json, tsconfig.json) DON'T EXIST, create a
  "project_scaffolding" coder task as the FIRST task BEFORE any feature coders.
  This coder must generate ALL missing entry/config files. This is MANDATORY.
- Do NOT create feature coders until scaffolding is confirmed.
- Then: individual feature implementations (one per coder task).
- Each task should be self-contained — the coder creates files from scratch.
- Be SPECIFIC: include exact filenames, tech stack, data models in task descriptions.""",

        "transition_criteria": "Transition to MID_1 when: core features are implemented, basic tests pass, implementation_plan tasks are mostly complete.",
    },

    Phase.MID_1: {
        "label": "중기 1기 — Execution & Roadmap Check",
        "max_coder_layer": 1,  # Layer 0 + Layer 1: feature + connector coders
        "env_strategies": ["direct", "resolver"],
        "goal": "프로덕션 실행 및 테스트. 로드맵 진행상황 체크, 중복 방지, 발전 가능성 확보.",
        "writer_directive": """PHASE: MID_1 (중기 1기)
Your focus in this phase:
1. Document test results and integration outcomes
2. UPDATE the roadmap (exports/roadmap.md) — mark completed items, add discoveries
3. Check for DUPLICATE functionality — consolidate if found
4. Identify improvement opportunities and document them
5. Write operational guides in skills/
6. Update progress reports with real execution data

Priority actions:
- exports/roadmap.md — UPDATE with progress checkmarks and new discoveries
- logic/duplicate_check.md — Audit for redundant features/code
- skills/operations_guide.md — How to run and operate the product
- exports/test_results.md — Comprehensive test outcomes""",

        "expert_directive": """PHASE: MID_1 (중기 1기)
Your decision criteria in this phase:
- VERIFY that roadmap items are being completed
- Check for duplicate or redundant knowledge/features
- Request test result documentation
- Focus on operational readiness
- Use EXPORT for test results and roadmap updates
- If roadmap has gaps, request updates via kb_updates_needed""",

        "transition_criteria": "Transition to MID_2 when: tests pass, roadmap is updated, no critical duplicates, operational guide exists.",
    },

    Phase.MID_2: {
        "label": "중기 2기 — Stabilization & Optimization",
        "max_coder_layer": 2,  # All layers: feature + connector + infra
        "env_strategies": ["resolver", "docker"],
        "goal": "프로덕션 안정화, 최적화, 배포 준비, 수익화 전략.",
        "writer_directive": """PHASE: MID_2 (중기 2기)
Your focus in this phase:
1. Document optimization opportunities and apply them
2. Write deployment guides and configuration docs
3. Create monetization/business strategy documentation
4. Performance benchmarks and stability reports
5. Security audit documentation
6. Prepare deployment checklists

Priority files:
- skills/deployment_guide.md — Step-by-step deployment
- logic/optimization_log.md — What was optimized and results
- skills/monetization_strategy.md — Revenue model, pricing
- exports/stability_report.md — Performance and reliability metrics
- maintenance/deploy_checklist.md — Pre-deploy verification list""",

        "expert_directive": """PHASE: MID_2 (중기 2기)
Your decision criteria in this phase:
- Prioritize STABILITY and OPTIMIZATION
- CRITICAL: Check the 'Current Project Reality' section for actual file counts.
  * If source_files = 0: treat this as MID phase — create coder_tasks to build the app.
    EXPORT and PAUSE when no code exists is meaningless.
  * If source_files < 5: prioritize coder_tasks to complete core implementation first.
  * If source_files >= 5 and total_lines > 500: then documentation/deployment exports are appropriate.
- Request deployment documentation only AFTER code exists
- Check that security and performance are addressed in the codebase
- Use EXPORT for deployment-ready artifacts — only when the project actually has code
- Focus on business viability documentation only after implementation is underway
- Suggest PAUSE for careful review before major deployments (not before code exists)""",

        "transition_criteria": "Transition to LATE when: source code exists (>5 files), deployed, stable, monetization strategy documented.",
    },

    Phase.LATE: {
        "label": "후기 — Maintenance & Evolution",
        "max_coder_layer": 2,  # All layers active
        "env_strategies": ["docker", "resolver", "direct"],
        "goal": "프로덕션 유지보수, 새 기능 추가, 로드맵 확장.",
        "writer_directive": """PHASE: LATE (후기)
Your focus in this phase:
1. Document maintenance procedures and runbooks
2. Track and log incidents/issues in errors/
3. Create feature proposals for new capabilities
4. Extend the roadmap with v2/v3 plans
5. Monitor system health and document patterns
6. Keep dependencies/ updated with version changes

Priority files:
- maintenance/runbook.md — Standard operating procedures
- exports/roadmap.md — Extended roadmap with new phases
- logic/feature_proposals.md — Ideas for new features
- maintenance/health_monitor.md — System metrics and alerts
- skills/incident_response.md — How to handle issues""",

        "expert_directive": """PHASE: LATE (후기)
Your decision criteria in this phase:
- Prioritize STABILITY over new features
- Use EXPORT for health reports and extended roadmaps
- Track incidents and ensure recovery documentation
- Suggest new features only after stability is confirmed
- Use MAINTENANCE state for scheduled maintenance windows
- Monitor for deprecation or dependency updates
- When enough new feature proposals accumulate, suggest transitioning to EVOLVE""",

        "transition_criteria": "Transition to EVOLVE when: system is stable, feature proposals exist, and new growth opportunities are identified.",
    },

    Phase.EVOLVE: {
        "label": "자율 발전 — Autonomous Evolution",
        "max_coder_layer": 2,  # All layers active
        "env_strategies": ["docker", "resolver", "direct"],
        "goal": "AI가 스스로 판단하여 프로덕트의 미래를 결정하고 지속적으로 발전시킴.",
        "writer_directive": """PHASE: EVOLVE (자율 발전)
You are now in AUTONOMOUS EVOLUTION mode. You must think independently.

Your focus in this phase:
1. ANALYZE the entire KB — identify gaps, outdated info, missed opportunities
2. Generate INNOVATION reports — what new features/products could emerge?
3. Evaluate market trends and technology shifts relevant to this project
4. Create self-improvement plans for the system itself
5. Write evolution proposals with cost-benefit analysis
6. Update the roadmap as a living document with new visions

Priority files:
- logic/self_assessment.md — Honest evaluation of current state
- logic/innovation_ideas.md — New feature/product ideas with rationale
- exports/evolution_roadmap.md — Next-generation roadmap
- skills/growth_opportunities.md — Areas for expansion
- maintenance/system_health.md — Current health and improvement areas

AUTONOMOUS DECISION MAKING:
- If you identify a high-value opportunity, suggest cycling back to MID phase
- If the system needs optimization, suggest MID_2
- If new features are ready for implementation, suggest MID → MID_1 flow
- You may propose entirely new product lines or pivots
- Document your reasoning thoroughly — you are the strategist now""",

        "expert_directive": """PHASE: EVOLVE (자율 발전)
You are now the AUTONOMOUS STRATEGIST. Think long-term.

Your decision criteria:
- SELF-ASSESS the entire project — what's working, what's not?
- INNOVATE — propose new features, pivots, or expansions
- DECIDE if the project should cycle back to an earlier phase:
  * Back to MID for major new features
  * Back to MID_2 for optimization rounds
  * Stay in EVOLVE for strategic planning
- Use EXPORT to create evolution reports for the user
- Use kb_updates_needed to request innovation documentation
- Consider: market fit, scalability, user needs, technical debt
- Your goal is CONTINUOUS IMPROVEMENT — never settle

Phase cycling:
- Set next_situation to "normal" with action "CONTINUE" for ongoing evolution
- When you have a concrete plan for new development, add to kb_updates_needed
- If a major new initiative is identified, document it and suggest phase transition""",

        "transition_criteria": "EVOLVE can cycle back to MID for new features, or stay in EVOLVE for continuous improvement. This is the self-sustaining phase.",
    },
}



def get_phase_prompt(phase: str, agent: str) -> str:
    """
    Get phase-specific prompt directive for an agent.

    Args:
        phase: Phase string value (e.g., "initial")
        agent: "writer" or "expert"

    Returns:
        Phase-specific instruction string to inject into the agent's prompt.
    """
    info = PHASE_INFO.get(phase, PHASE_INFO[Phase.INITIAL])
    key = f"{agent}_directive"
    goal = info.get("goal", "")
    directive = info.get(key, "")
    transition = info.get("transition_criteria", "")

    return f"""
## Project Phase
{info.get('label', phase)}

## Phase Goal
{goal}

{directive}

## Phase Transition
{transition}
"""


def get_phase_label(phase: str) -> str:
    info = PHASE_INFO.get(phase, {})
    return info.get("label", phase)


def get_all_phases() -> list[tuple[str, str]]:
    """Return list of (phase_value, label) tuples."""
    return [(p.value, PHASE_INFO[p]["label"]) for p in Phase]
