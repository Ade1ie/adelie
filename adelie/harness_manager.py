"""
adelie/harness_manager.py

Dynamic Harness Management — replaces the static Phase Enum system.

The HarnessManager loads the project's pipeline configuration from
`workspace/.adelie/harness.json`, providing:
  - Dynamic phase definitions (phases, goals, directives, transition criteria)
  - Dynamic agent slot registration
  - Harness modification + validation + rollback
  - Backward-compatible API surface for existing code

If no harness.json exists, the default 6-phase pipeline is used as a template.
"""

from __future__ import annotations

import json
import shutil
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from rich.console import Console

console = Console()


# ── Permission Model ─────────────────────────────────────────────────────────

class AgentPermission(str, Enum):
    """Three-tier permission model for dynamic agents."""
    OBSERVER = "observer"    # KB read only
    ANALYST  = "analyst"     # KB read + write + export
    OPERATOR = "operator"    # Above + coder task creation


# ── Harness Schema Defaults ──────────────────────────────────────────────────

DEFAULT_HARNESS: dict = {
    "$schema": "harness/v1",
    "version": "1.0",
    "phases": [
        {
            "id": "initial",
            "label": "초기 — Planning & Documentation",
            "order": 0,
            "max_coder_layer": -1,
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
            "transition_criteria": {
                "description": "Transition to MID when: roadmap.md exists, architecture is documented, at least 5 KB files exist, AND at least one coder_task has been issued (even scaffolding).",
                "conditions": {
                    "min_loops": 8,
                    "min_kb_files": 5,
                    "required_files": ["roadmap", "architecture"],
                    "min_test_pass_rate": 0.0,
                    "min_review_score": 0,
                },
            },
            "next_phase": "mid",
        },
        {
            "id": "mid",
            "label": "중기 — Implementation & Testing",
            "order": 1,
            "max_coder_layer": 0,
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
            "transition_criteria": {
                "description": "Transition to MID_1 when: core features are implemented, basic tests pass, implementation_plan tasks are mostly complete.",
                "conditions": {
                    "min_loops": 15,
                    "min_kb_files": 8,
                    "required_files": ["implementation", "test"],
                    "min_test_pass_rate": 0.0,
                    "min_review_score": 4,
                },
            },
            "next_phase": "mid_1",
        },
        {
            "id": "mid_1",
            "label": "중기 1기 — Execution & Roadmap Check",
            "order": 2,
            "max_coder_layer": 1,
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
            "transition_criteria": {
                "description": "Transition to MID_2 when: tests pass, roadmap is updated, no critical duplicates, operational guide exists.",
                "conditions": {
                    "min_loops": 20,
                    "min_kb_files": 10,
                    "required_files": ["operations", "test_result"],
                    "min_test_pass_rate": 0.3,
                    "min_review_score": 5,
                },
            },
            "next_phase": "mid_2",
        },
        {
            "id": "mid_2",
            "label": "중기 2기 — Stabilization & Optimization",
            "order": 3,
            "max_coder_layer": 2,
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
            "transition_criteria": {
                "description": "Transition to LATE when: source code exists (>5 files), deployed, stable, monetization strategy documented.",
                "conditions": {
                    "min_loops": 25,
                    "min_kb_files": 12,
                    "required_files": ["deploy", "stability"],
                    "min_test_pass_rate": 0.5,
                    "min_review_score": 6,
                },
            },
            "next_phase": "late",
        },
        {
            "id": "late",
            "label": "후기 — Maintenance & Evolution",
            "order": 4,
            "max_coder_layer": 2,
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
            "transition_criteria": {
                "description": "Transition to EVOLVE when: system is stable, feature proposals exist, and new growth opportunities are identified.",
                "conditions": {
                    "min_loops": 30,
                    "min_kb_files": 15,
                    "required_files": ["feature_proposal", "innovation"],
                    "min_test_pass_rate": 0.7,
                    "min_review_score": 7,
                },
            },
            "next_phase": "evolve",
        },
        {
            "id": "evolve",
            "label": "자율 발전 — Autonomous Evolution",
            "order": 5,
            "max_coder_layer": 2,
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
            "transition_criteria": {
                "description": "EVOLVE can cycle back to MID for new features, or stay in EVOLVE for continuous improvement. This is the self-sustaining phase.",
                "conditions": {
                    "min_loops": 0,
                    "min_kb_files": 0,
                    "required_files": [],
                    "min_test_pass_rate": 0.0,
                    "min_review_score": 0,
                },
            },
            "next_phase": None,
        },
    ],
    "dynamic_agents": [],
    "transitions": {
        "initial": {"next": "mid", "allow_skip": False},
        "mid": {"next": "mid_1", "allow_skip": False},
        "mid_1": {"next": "mid_2", "allow_skip": False},
        "mid_2": {"next": "late", "allow_skip": False},
        "late": {"next": "evolve", "allow_skip": False},
    },
    "metadata": {
        "created_by": "default",
        "modified_by": None,
        "last_modified": None,
    },
}


# ── HarnessManager ───────────────────────────────────────────────────────────


class HarnessManager:
    """
    Manages the dynamic harness configuration for a project.

    Loads harness.json from the workspace, falls back to the default
    6-phase pipeline, and provides backward-compatible APIs that
    the existing codebase (phases.py, orchestrator.py, etc.) relies on.
    """

    MAX_HISTORY = 20  # Max number of harness snapshots to keep

    def __init__(self, workspace_path: Path | None = None):
        if workspace_path is None:
            try:
                from adelie.config import WORKSPACE_PATH
                workspace_path = WORKSPACE_PATH
            except Exception:
                workspace_path = Path.cwd() / ".adelie" / "workspace"
        self._workspace_path = workspace_path
        self._adelie_root = workspace_path.parent
        self._harness_path = self._adelie_root / "harness.json"
        self._history_dir = self._adelie_root / "harness_history"
        self._harness: dict = {}
        self._phase_map: dict[str, dict] = {}  # id → phase config
        self._phase_enum: type | None = None
        self._load()

    # ── Loading / Saving ─────────────────────────────────────────────────

    def _load(self) -> None:
        """Load harness from file, or use default."""
        if self._harness_path.exists():
            try:
                data = json.loads(self._harness_path.read_text(encoding="utf-8"))
                if self._validate_harness(data):
                    self._harness = data
                else:
                    console.print(
                        "[yellow]⚠️  harness.json validation failed — using default[/yellow]"
                    )
                    self._harness = deepcopy(DEFAULT_HARNESS)
            except (json.JSONDecodeError, Exception) as e:
                console.print(f"[yellow]⚠️  harness.json load error: {e} — using default[/yellow]")
                self._harness = deepcopy(DEFAULT_HARNESS)
        else:
            self._harness = deepcopy(DEFAULT_HARNESS)

        self._rebuild_phase_map()

    def _rebuild_phase_map(self) -> None:
        """Build internal phase lookup from loaded harness."""
        self._phase_map = {}
        for phase in self._harness.get("phases", []):
            self._phase_map[phase["id"]] = phase
        self._phase_enum = None  # Invalidate cached enum

    def save(self) -> None:
        """Persist current harness to disk."""
        self._harness["metadata"]["last_modified"] = datetime.now().isoformat(
            timespec="seconds"
        )
        self._harness_path.parent.mkdir(parents=True, exist_ok=True)
        self._harness_path.write_text(
            json.dumps(self._harness, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _snapshot(self) -> None:
        """Save a snapshot of the current harness before modification."""
        self._history_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot_path = self._history_dir / f"harness_{ts}.json"
        snapshot_path.write_text(
            json.dumps(self._harness, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        # Keep only the last MAX_HISTORY snapshots
        snapshots = sorted(self._history_dir.glob("harness_*.json"))
        while len(snapshots) > self.MAX_HISTORY:
            snapshots[0].unlink()
            snapshots.pop(0)

    def rollback(self) -> bool:
        """
        Rollback to the most recent harness snapshot.
        Returns True if rollback succeeded, False if no snapshots available.
        """
        if not self._history_dir.exists():
            return False
        snapshots = sorted(self._history_dir.glob("harness_*.json"))
        if not snapshots:
            return False
        latest = snapshots[-1]
        try:
            data = json.loads(latest.read_text(encoding="utf-8"))
            if self._validate_harness(data):
                self._harness = data
                self._rebuild_phase_map()
                self.save()
                latest.unlink()
                console.print(
                    f"[green]✅ Rolled back to harness snapshot: {latest.name}[/green]"
                )
                return True
        except Exception as e:
            console.print(f"[red]❌ Rollback failed: {e}[/red]")
        return False

    # ── Validation ───────────────────────────────────────────────────────

    def _validate_harness(self, data: dict) -> bool:
        """Validate harness structure."""
        if not isinstance(data, dict):
            return False
        if "$schema" not in data or data["$schema"] != "harness/v1":
            return False
        phases = data.get("phases")
        if not isinstance(phases, list) or len(phases) == 0:
            return False
        # Validate each phase has required fields
        required_fields = {"id", "label", "order", "max_coder_layer", "goal"}
        phase_ids = set()
        for phase in phases:
            if not isinstance(phase, dict):
                return False
            if not required_fields.issubset(phase.keys()):
                return False
            if phase["id"] in phase_ids:
                return False  # Duplicate phase ID
            phase_ids.add(phase["id"])
        # Validate dynamic_agents if present
        for agent in data.get("dynamic_agents", []):
            if not isinstance(agent, dict):
                return False
            if "name" not in agent or "active_in_phases" not in agent:
                return False
        return True

    # ── Backward-Compatible API (used by phases.py shim) ─────────────────

    def get_phase_info(self) -> dict:
        """
        Return a dict compatible with the old PHASE_INFO structure.
        Keys are phase id strings, values are dicts with label, max_coder_layer,
        env_strategies, goal, writer_directive, expert_directive, transition_criteria.
        """
        result = {}
        for pid, phase in self._phase_map.items():
            tc = phase.get("transition_criteria", {})
            result[pid] = {
                "label": phase.get("label", pid),
                "max_coder_layer": phase.get("max_coder_layer", -1),
                "env_strategies": phase.get("env_strategies", ["direct"]),
                "goal": phase.get("goal", ""),
                "writer_directive": phase.get("writer_directive", ""),
                "expert_directive": phase.get("expert_directive", ""),
                "transition_criteria": tc.get("description", "")
                    if isinstance(tc, dict) else str(tc),
            }
        return result

    def get_phase_enum(self) -> type:
        """
        Dynamically create a Phase Enum from the current harness phases.
        Compatible with the old Phase(str, Enum) class.
        """
        if self._phase_enum is not None:
            return self._phase_enum
        members = {}
        for phase in self._harness.get("phases", []):
            pid = phase["id"]
            members[pid.upper()] = pid
        self._phase_enum = Enum("Phase", members, type=str)
        return self._phase_enum

    def get_phase_prompt(self, phase: str, agent: str) -> str:
        """Get phase-specific prompt directive for an agent."""
        info = self._phase_map.get(phase)
        if info is None:
            # Fallback to first phase
            first = self._harness.get("phases", [{}])[0]
            info = first

        key = f"{agent}_directive"
        goal = info.get("goal", "")
        directive = info.get(key, "")
        tc = info.get("transition_criteria", {})
        transition = tc.get("description", "") if isinstance(tc, dict) else str(tc)

        return f"""
## Project Phase
{info.get('label', phase)}

## Phase Goal
{goal}

{directive}

## Phase Transition
{transition}
"""

    def get_phase_label(self, phase: str) -> str:
        """Get human-readable label for a phase."""
        info = self._phase_map.get(phase, {})
        return info.get("label", phase)

    def get_all_phases(self) -> list[tuple[str, str]]:
        """Return list of (phase_id, label) tuples, ordered."""
        phases = sorted(
            self._harness.get("phases", []),
            key=lambda p: p.get("order", 0),
        )
        return [(p["id"], p.get("label", p["id"])) for p in phases]

    # ── Phase Transition Logic ───────────────────────────────────────────

    def check_transition(
        self,
        current_phase: str,
        loop_iteration: int,
        total_kb_files: int,
        kb_file_stems: set[str],
        test_pass_rate: float = 0.0,
        avg_review_score: float = 0.0,
        loop_multiplier: float = 1.0,
    ) -> str | None:
        """
        Check if conditions for the next phase are met.
        Returns the next phase id if ready, None otherwise.
        """
        phase = self._phase_map.get(current_phase)
        if phase is None:
            return None

        tc = phase.get("transition_criteria", {})
        if not isinstance(tc, dict):
            return None

        conditions = tc.get("conditions", {})
        if not conditions:
            return None

        next_phase = phase.get("next_phase")
        if next_phase is None:
            return None

        # Check min_loops
        min_loops = int(conditions.get("min_loops", 0) * loop_multiplier)
        if loop_iteration < min_loops:
            return None

        # Check min_kb_files
        if total_kb_files < conditions.get("min_kb_files", 0):
            return None

        # Check required_files (substring match against KB file stems)
        for required in conditions.get("required_files", []):
            if not any(required in stem for stem in kb_file_stems):
                return None

        # Check min_test_pass_rate
        if test_pass_rate < conditions.get("min_test_pass_rate", 0.0):
            return None

        # Check min_review_score
        if avg_review_score < conditions.get("min_review_score", 0):
            return None

        return next_phase

    def get_phase_order(self) -> list[str]:
        """Return ordered list of phase IDs."""
        phases = sorted(
            self._harness.get("phases", []),
            key=lambda p: p.get("order", 0),
        )
        return [p["id"] for p in phases]

    def is_forward_transition(self, from_phase: str, to_phase: str) -> bool:
        """Check if a transition is forward (higher order) in the pipeline."""
        order = self.get_phase_order()
        try:
            return order.index(to_phase) > order.index(from_phase)
        except ValueError:
            return False

    # ── Dynamic Agent Management ─────────────────────────────────────────

    def get_dynamic_agents(self) -> list[dict]:
        """Return list of dynamic agent configurations."""
        return self._harness.get("dynamic_agents", [])

    def get_agents_for_phase(self, phase_id: str) -> list[dict]:
        """Return dynamic agents that are active in a given phase."""
        return [
            agent for agent in self.get_dynamic_agents()
            if phase_id in agent.get("active_in_phases", [])
        ]

    def add_dynamic_agent(self, agent_config: dict) -> bool:
        """
        Add a dynamic agent to the harness.
        Validates and saves. Returns True on success.
        """
        if not isinstance(agent_config, dict):
            return False
        if "name" not in agent_config or "active_in_phases" not in agent_config:
            return False

        # Check for duplicate name
        existing_names = {a["name"] for a in self.get_dynamic_agents()}
        if agent_config["name"] in existing_names:
            # Update existing
            agents = self._harness.get("dynamic_agents", [])
            for i, a in enumerate(agents):
                if a["name"] == agent_config["name"]:
                    agents[i] = agent_config
                    break
        else:
            # Default permissions
            if "permissions" not in agent_config:
                agent_config["permissions"] = {
                    "level": AgentPermission.ANALYST.value,
                    "coder_layer_access": False,
                    "kb_write": True,
                    "export": True,
                }
            self._harness.setdefault("dynamic_agents", []).append(agent_config)

        self._rebuild_phase_map()
        return True

    def remove_dynamic_agent(self, name: str) -> bool:
        """Remove a dynamic agent by name. Returns True if found and removed."""
        agents = self._harness.get("dynamic_agents", [])
        original_len = len(agents)
        self._harness["dynamic_agents"] = [a for a in agents if a["name"] != name]
        return len(self._harness["dynamic_agents"]) < original_len

    # ── Harness Modification ─────────────────────────────────────────────

    def modify_harness(self, payload: dict) -> tuple[bool, str]:
        """
        Apply a modification payload from Expert AI's MODIFY_HARNESS action.

        Payload can include:
        - new_phases: list of phase dicts to add/replace
        - remove_phases: list of phase IDs to remove
        - new_agents: list of dynamic agent configs to add
        - remove_agents: list of agent names to remove
        - transitions: dict of transition overrides

        Returns (success: bool, message: str).
        """
        # Snapshot before modification
        self._snapshot()

        try:
            # Add/replace phases
            for new_phase in payload.get("new_phases", []):
                if not isinstance(new_phase, dict) or "id" not in new_phase:
                    continue
                # Ensure required fields
                new_phase.setdefault("label", new_phase["id"])
                new_phase.setdefault("order", len(self._harness["phases"]))
                new_phase.setdefault("max_coder_layer", 0)
                new_phase.setdefault("goal", "")
                # Check if replacing existing
                replaced = False
                for i, existing in enumerate(self._harness["phases"]):
                    if existing["id"] == new_phase["id"]:
                        self._harness["phases"][i] = new_phase
                        replaced = True
                        break
                if not replaced:
                    self._harness["phases"].append(new_phase)

            # Remove phases (never remove all — at least one must remain)
            remove_ids = set(payload.get("remove_phases", []))
            if remove_ids:
                remaining = [
                    p for p in self._harness["phases"]
                    if p["id"] not in remove_ids
                ]
                if len(remaining) < 1:
                    return False, "Cannot remove all phases — at least one must remain."
                self._harness["phases"] = remaining

            # Re-order phases based on their "order" field
            self._harness["phases"].sort(key=lambda p: p.get("order", 0))

            # Add/update dynamic agents
            for agent_config in payload.get("new_agents", []):
                self.add_dynamic_agent(agent_config)

            # Remove dynamic agents
            for agent_name in payload.get("remove_agents", []):
                self.remove_dynamic_agent(agent_name)

            # Update transitions
            if "transitions" in payload:
                self._harness.setdefault("transitions", {}).update(
                    payload["transitions"]
                )

            # Update metadata
            self._harness["metadata"]["modified_by"] = "expert_ai"

            # Validate the result
            if not self._validate_harness(self._harness):
                self.rollback()
                return False, "Modified harness failed validation — rolled back."

            self._rebuild_phase_map()
            self.save()
            return True, f"Harness modified successfully ({len(self._harness['phases'])} phases, {len(self.get_dynamic_agents())} dynamic agents)."

        except Exception as e:
            self.rollback()
            return False, f"Harness modification failed: {e} — rolled back."

    # ── Phase Config Access ──────────────────────────────────────────────

    def get_phase_config(self, phase_id: str) -> dict | None:
        """Get the full config dict for a phase."""
        return self._phase_map.get(phase_id)

    def get_max_coder_layer(self, phase_id: str) -> int:
        """Get the max coder layer for a phase. Returns -1 if unknown."""
        config = self._phase_map.get(phase_id, {})
        return config.get("max_coder_layer", -1)

    @property
    def phase_ids(self) -> list[str]:
        """List of all phase IDs in order."""
        return self.get_phase_order()

    @property
    def harness_data(self) -> dict:
        """Raw harness dict (read-only copy)."""
        return deepcopy(self._harness)


# ── Module-Level Singleton ───────────────────────────────────────────────────
# Lazy singleton — created on first access.

_manager: HarnessManager | None = None


def get_manager(workspace_path: Path | None = None) -> HarnessManager:
    """Get or create the singleton HarnessManager."""
    global _manager
    if _manager is None:
        _manager = HarnessManager(workspace_path=workspace_path)
    return _manager


def reset_manager() -> None:
    """Reset the singleton (for testing)."""
    global _manager
    _manager = None
