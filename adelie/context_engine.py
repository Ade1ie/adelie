"""
adelie/context_engine.py

Per-agent context assembly engine.
Each AI agent has different context needs — the context engine
provides tailored, budget-aware context for each agent type.

Inspired by openclaw's context engine lifecycle (bootstrap, ingest, assemble, compact),
simplified for Adelie's architecture.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from rich.console import Console

from adelie.context_compactor import (
    compact_expert_output,
    compact_kb_content,
    compact_system_state,
    estimate_tokens,
    truncate_to_budget,
)

console = Console()


# ── Agent Types ──────────────────────────────────────────────────────────────


class AgentType(str, Enum):
    WRITER = "writer"
    EXPERT = "expert"
    CODER = "coder"
    REVIEWER = "reviewer"
    TESTER = "tester"
    RUNNER = "runner"
    SCANNER = "scanner"
    ANALYST = "analyst"
    MONITOR = "monitor"
    INFORM = "inform"


# ── Context Profile ─────────────────────────────────────────────────────────


@dataclass
class ContextProfile:
    """
    Defines what context an agent needs and its token budget allocation.
    Fields set to True are included in the assembled context.
    """

    # What to include
    needs_system_state: bool = True
    needs_project_tree: bool = False
    needs_source_stats: bool = False
    needs_kb_content: bool = False
    needs_kb_index: bool = False
    needs_expert_output: bool = False
    needs_cycle_history: bool = False
    needs_key_configs: bool = False

    # Token budget (total for this agent's context)
    max_tokens: int = 12000

    # Budget allocation shares (must sum to ~1.0 for used components)
    state_share: float = 0.15
    kb_share: float = 0.40
    history_share: float = 0.10
    expert_share: float = 0.15
    tree_share: float = 0.10
    configs_share: float = 0.10


# ── Pre-defined Profiles ────────────────────────────────────────────────────

AGENT_PROFILES: dict[AgentType, ContextProfile] = {
    AgentType.EXPERT: ContextProfile(
        needs_system_state=True,
        needs_project_tree=True,
        needs_source_stats=True,
        needs_kb_content=True,
        needs_kb_index=True,
        needs_cycle_history=True,
        max_tokens=14000,
        state_share=0.10,
        kb_share=0.45,
        history_share=0.15,
        tree_share=0.15,
        expert_share=0.0,
    ),
    AgentType.WRITER: ContextProfile(
        needs_system_state=True,
        needs_kb_index=True,
        needs_expert_output=True,
        needs_cycle_history=True,
        max_tokens=10000,
        state_share=0.20,
        kb_share=0.0,
        history_share=0.10,
        expert_share=0.30,
        tree_share=0.0,
    ),
    AgentType.CODER: ContextProfile(
        needs_system_state=False,
        needs_project_tree=True,
        needs_key_configs=True,
        max_tokens=10000,
        tree_share=0.40,
        configs_share=0.40,
    ),
    AgentType.REVIEWER: ContextProfile(
        needs_system_state=False,
        needs_project_tree=True,
        max_tokens=8000,
        tree_share=0.30,
    ),
    AgentType.TESTER: ContextProfile(
        needs_system_state=False,
        needs_project_tree=True,
        needs_key_configs=True,
        max_tokens=8000,
        tree_share=0.30,
        configs_share=0.30,
    ),
    AgentType.RUNNER: ContextProfile(
        needs_system_state=False,
        needs_project_tree=True,
        needs_key_configs=True,
        max_tokens=8000,
        tree_share=0.30,
        configs_share=0.30,
    ),
    AgentType.SCANNER: ContextProfile(
        needs_system_state=False,
        needs_project_tree=True,
        needs_source_stats=True,
        max_tokens=8000,
        tree_share=0.50,
    ),
    AgentType.ANALYST: ContextProfile(
        needs_system_state=True,
        needs_kb_content=True,
        needs_kb_index=True,
        needs_cycle_history=True,
        max_tokens=12000,
        state_share=0.15,
        kb_share=0.40,
        history_share=0.20,
    ),
    AgentType.MONITOR: ContextProfile(
        needs_system_state=True,
        max_tokens=4000,
        state_share=0.50,
    ),
    AgentType.INFORM: ContextProfile(
        needs_system_state=True,
        needs_kb_index=True,
        max_tokens=6000,
        state_share=0.30,
    ),
}


# ── Context Assembly ─────────────────────────────────────────────────────────


@dataclass
class AssembledContext:
    """Result of context assembly for an agent."""

    agent_type: AgentType
    sections: dict[str, str] = field(default_factory=dict)
    total_tokens: int = 0
    budget: int = 0
    truncated_sections: list[str] = field(default_factory=list)

    def render(self) -> str:
        """Render all sections into a single context string."""
        parts = []
        for label, content in self.sections.items():
            if content:
                parts.append(f"## {label}\n{content}")
        return "\n\n".join(parts)

    @property
    def within_budget(self) -> bool:
        return self.total_tokens <= self.budget


def assemble_context(
    agent_type: AgentType | str,
    system_state: dict | None = None,
    kb_content: str = "",
    kb_index: str = "",
    expert_output: dict | None = None,
    cycle_history: str = "",
    project_tree: str = "",
    source_stats: dict | None = None,
    key_configs: str = "",
) -> AssembledContext:
    """
    Assemble tailored context for a specific agent type.

    Uses the agent's profile to determine which components to include,
    and applies token budgets to each component.

    Args:
        agent_type:    Which agent this context is for
        system_state:  Current orchestrator state dict
        kb_content:    KB file contents (for Expert/Analyst)
        kb_index:      KB index summary string
        expert_output: Last Expert AI decision dict
        cycle_history: Cycle history context string
        project_tree:  Project file tree string
        source_stats:  Source code statistics dict
        key_configs:   Key config file contents

    Returns:
        AssembledContext with budget-enforced sections.
    """
    if isinstance(agent_type, str):
        try:
            agent_type = AgentType(agent_type)
        except ValueError:
            agent_type = AgentType.EXPERT  # default fallback

    profile = AGENT_PROFILES.get(agent_type, AGENT_PROFILES[AgentType.EXPERT])
    result = AssembledContext(
        agent_type=agent_type,
        budget=profile.max_tokens,
    )

    # ── Assemble each section with its budget ────────────────────────────
    if profile.needs_system_state and system_state:
        budget = int(profile.max_tokens * profile.state_share)
        # Strip fields the agent doesn't need
        filtered_state = _filter_state(system_state, profile)
        content = compact_system_state(filtered_state, budget)
        tokens = estimate_tokens(content)
        result.sections["Current System State"] = content
        result.total_tokens += tokens
        if tokens >= budget:
            result.truncated_sections.append("system_state")

    if profile.needs_kb_content and kb_content:
        budget = int(profile.max_tokens * profile.kb_share)
        content = compact_kb_content(kb_content, budget)
        tokens = estimate_tokens(content)
        result.sections["Knowledge Base Content"] = content
        result.total_tokens += tokens
        if tokens >= budget:
            result.truncated_sections.append("kb_content")

    if profile.needs_kb_index and kb_index:
        # KB index is usually small, give it a slice of kb_share or state_share
        budget = int(profile.max_tokens * 0.10)
        content = truncate_to_budget(kb_index, budget, "KB index")
        result.sections["Knowledge Base Index"] = content
        result.total_tokens += estimate_tokens(content)

    if profile.needs_expert_output and expert_output is not None:
        budget = int(profile.max_tokens * profile.expert_share)
        content = compact_expert_output(expert_output, budget)
        result.sections["Expert AI Last Output"] = content
        result.total_tokens += estimate_tokens(content)

    if profile.needs_cycle_history and cycle_history:
        budget = int(profile.max_tokens * profile.history_share)
        content = truncate_to_budget(cycle_history, budget, "cycle history")
        result.sections["Cycle History"] = content
        result.total_tokens += estimate_tokens(content)

    if profile.needs_project_tree and project_tree:
        budget = int(profile.max_tokens * profile.tree_share)
        content = truncate_to_budget(project_tree, budget, "project tree")
        result.sections["Project Structure"] = content
        result.total_tokens += estimate_tokens(content)

    if profile.needs_source_stats and source_stats:
        content = json.dumps(source_stats, indent=2)
        result.sections["Source Statistics"] = content
        result.total_tokens += estimate_tokens(content)

    if profile.needs_key_configs and key_configs:
        budget = int(profile.max_tokens * profile.configs_share)
        content = truncate_to_budget(key_configs, budget, "config files")
        result.sections["Key Configuration Files"] = content
        result.total_tokens += estimate_tokens(content)

    return result


def _filter_state(state: dict, profile: ContextProfile) -> dict:
    """Remove fields from system_state that the agent doesn't need."""
    filtered = dict(state)

    if not profile.needs_project_tree:
        filtered.pop("project_tree", None)
    if not profile.needs_source_stats:
        filtered.pop("source_stats", None)
    if not profile.needs_cycle_history:
        filtered.pop("cycle_history", None)

    return filtered


# ── Convenience Functions ────────────────────────────────────────────────────


def get_profile(agent_type: AgentType | str) -> ContextProfile:
    """Get the context profile for an agent type."""
    if isinstance(agent_type, str):
        try:
            agent_type = AgentType(agent_type)
        except ValueError:
            return AGENT_PROFILES[AgentType.EXPERT]
    return AGENT_PROFILES.get(agent_type, AGENT_PROFILES[AgentType.EXPERT])


def get_budget(agent_type: AgentType | str) -> int:
    """Get the total token budget for an agent type."""
    return get_profile(agent_type).max_tokens


def list_profiles() -> dict[str, dict]:
    """List all agent profiles with their configurations (for debugging)."""
    result = {}
    for agent_type, profile in AGENT_PROFILES.items():
        needs = []
        if profile.needs_system_state:
            needs.append("state")
        if profile.needs_project_tree:
            needs.append("tree")
        if profile.needs_kb_content:
            needs.append("kb")
        if profile.needs_kb_index:
            needs.append("index")
        if profile.needs_expert_output:
            needs.append("expert")
        if profile.needs_cycle_history:
            needs.append("history")
        if profile.needs_key_configs:
            needs.append("configs")

        result[agent_type.value] = {
            "max_tokens": profile.max_tokens,
            "needs": needs,
        }
    return result


# ── After-Cycle Hook ─────────────────────────────────────────────────────────
# Inspired by openclaw's context-engine afterTurn() lifecycle hook.

# Module-level token tracking for after_cycle decisions
_cycle_token_log: list[dict[str, int]] = []
_MAX_TOKEN_LOG_SIZE = 20


def after_cycle(
    assembled_contexts: list[AssembledContext] | None = None,
    cycle_history: Any = None,
) -> dict:
    """
    Post-cycle lifecycle hook, called after each orchestrator cycle completes.
    Inspired by openclaw's ContextEngine.afterTurn().

    Responsibilities:
    - Track per-cycle token usage for trending
    - Detect when context consistently exceeds budget
    - Signal when compaction or summarization should occur

    Args:
        assembled_contexts: All contexts assembled during this cycle.
        cycle_history:      CycleHistory instance (for triggering summary if needed).

    Returns:
        Dict with recommendations:
            needs_compaction: bool — True if contexts exceeded budget
            over_budget_agents: list[str] — Agent types over budget
            avg_utilization: float — Average budget utilization (0.0-1.0+)
    """
    over_budget_agents: list[str] = []
    total_utilization = 0.0
    agent_count = 0

    if assembled_contexts:
        for ctx in assembled_contexts:
            if ctx.budget > 0:
                utilization = ctx.total_tokens / ctx.budget
                total_utilization += utilization
                agent_count += 1
                if not ctx.within_budget:
                    over_budget_agents.append(ctx.agent_type.value)

    avg_utilization = (total_utilization / agent_count) if agent_count > 0 else 0.0

    # Record for trending
    _cycle_token_log.append({
        "over_budget_count": len(over_budget_agents),
        "avg_utilization_pct": int(avg_utilization * 100),
    })
    while len(_cycle_token_log) > _MAX_TOKEN_LOG_SIZE:
        _cycle_token_log.pop(0)

    # Recommend compaction if recent cycles are consistently over budget
    needs_compaction = False
    if len(_cycle_token_log) >= 3:
        recent = _cycle_token_log[-3:]
        if all(entry["over_budget_count"] > 0 for entry in recent):
            needs_compaction = True
            console.print(
                "[yellow]  📦 after_cycle: contexts over budget for 3+ cycles, "
                "recommending compaction[/yellow]"
            )

    result = {
        "needs_compaction": needs_compaction,
        "over_budget_agents": over_budget_agents,
        "avg_utilization": round(avg_utilization, 2),
    }

    if over_budget_agents:
        console.print(
            f"[dim]  📊 after_cycle: {', '.join(over_budget_agents)} over budget "
            f"(avg utilization: {avg_utilization:.0%})[/dim]"
        )

    return result


def get_cycle_token_stats() -> list[dict]:
    """Return recent per-cycle token stats (for monitoring dashboards)."""
    return list(_cycle_token_log)


def reset_cycle_stats() -> None:
    """Reset cycle token tracking (for tests)."""
    _cycle_token_log.clear()
