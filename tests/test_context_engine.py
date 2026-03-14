"""tests/test_context_engine.py — Tests for per-agent context engine."""
from __future__ import annotations

import pytest

from adelie.context_engine import (
    AgentType,
    AssembledContext,
    ContextProfile,
    after_cycle,
    assemble_context,
    get_budget,
    get_cycle_token_stats,
    get_profile,
    list_profiles,
    reset_cycle_stats,
    AGENT_PROFILES,
)
from adelie.context_compactor import estimate_tokens


class TestAgentProfiles:
    def test_all_agents_have_profiles(self):
        for agent_type in AgentType:
            assert agent_type in AGENT_PROFILES

    def test_expert_has_most_context(self):
        expert = AGENT_PROFILES[AgentType.EXPERT]
        monitor = AGENT_PROFILES[AgentType.MONITOR]
        assert expert.max_tokens > monitor.max_tokens
        assert expert.needs_kb_content is True
        assert expert.needs_cycle_history is True

    def test_writer_needs_expert_output(self):
        writer = AGENT_PROFILES[AgentType.WRITER]
        assert writer.needs_expert_output is True
        assert writer.needs_kb_content is False

    def test_coder_needs_tree_and_configs(self):
        coder = AGENT_PROFILES[AgentType.CODER]
        assert coder.needs_project_tree is True
        assert coder.needs_key_configs is True
        assert coder.needs_system_state is False

    def test_monitor_is_minimal(self):
        monitor = AGENT_PROFILES[AgentType.MONITOR]
        assert monitor.max_tokens == 4000
        assert monitor.needs_kb_content is False
        assert monitor.needs_project_tree is False


class TestAssembleContext:
    def test_expert_gets_all_sections(self):
        ctx = assemble_context(
            agent_type=AgentType.EXPERT,
            system_state={"goal": "test", "phase": "initial", "situation": "normal"},
            kb_content="## File\nsome knowledge",
            kb_index="• skills/a.md: test",
            cycle_history="Loop #1: action=CONTINUE",
            project_tree="src/main.py (1KB)",
            source_stats={"total_files": 5},
        )
        assert "System State" in ctx.render()
        assert "Knowledge Base Content" in ctx.render()
        assert "Cycle History" in ctx.render()

    def test_coder_gets_only_tree_and_configs(self):
        ctx = assemble_context(
            agent_type=AgentType.CODER,
            system_state={"goal": "test"},
            kb_content="should not appear",
            project_tree="src/main.py",
            key_configs="package.json content",
        )
        rendered = ctx.render()
        assert "Project Structure" in rendered
        assert "Configuration" in rendered
        assert "System State" not in rendered
        assert "Knowledge Base Content" not in rendered

    def test_monitor_gets_minimal(self):
        ctx = assemble_context(
            agent_type=AgentType.MONITOR,
            system_state={"situation": "normal"},
            kb_content="should not appear",
            project_tree="should not appear",
        )
        rendered = ctx.render()
        assert "System State" in rendered
        assert "Knowledge Base" not in rendered
        assert "Project Structure" not in rendered

    def test_string_agent_type_works(self):
        ctx = assemble_context(
            agent_type="writer",
            system_state={"phase": "initial"},
            expert_output={"action": "CONTINUE"},
        )
        assert ctx.agent_type == AgentType.WRITER

    def test_unknown_agent_type_falls_back(self):
        ctx = assemble_context(
            agent_type="nonexistent",
            system_state={"phase": "initial"},
        )
        assert ctx.agent_type == AgentType.EXPERT

    def test_within_budget(self):
        ctx = assemble_context(
            agent_type=AgentType.MONITOR,
            system_state={"situation": "normal"},
        )
        assert ctx.within_budget is True

    def test_large_content_truncated(self):
        ctx = assemble_context(
            agent_type=AgentType.MONITOR,  # 4000 token budget
            system_state={"goal": "x" * 50000},
        )
        # Should be truncated to fit budget
        assert ctx.total_tokens < 5000


class TestConvenienceFunctions:
    def test_get_profile(self):
        profile = get_profile(AgentType.EXPERT)
        assert profile.needs_kb_content is True

    def test_get_profile_by_string(self):
        profile = get_profile("writer")
        assert profile.needs_expert_output is True

    def test_get_budget(self):
        assert get_budget("expert") == 14000
        assert get_budget("monitor") == 4000

    def test_list_profiles(self):
        profiles = list_profiles()
        assert "expert" in profiles
        assert "writer" in profiles
        assert "kb" in profiles["expert"]["needs"]


class TestAssembledContext:
    def test_render_empty(self):
        ctx = AssembledContext(agent_type=AgentType.MONITOR)
        assert ctx.render() == ""

    def test_render_multiple_sections(self):
        ctx = AssembledContext(agent_type=AgentType.EXPERT)
        ctx.sections["System State"] = "state data"
        ctx.sections["KB Content"] = "kb data"
        rendered = ctx.render()
        assert "## System State" in rendered
        assert "## KB Content" in rendered


class TestAfterCycle:
    def setup_method(self):
        reset_cycle_stats()

    def test_no_contexts_ok(self):
        result = after_cycle(assembled_contexts=None)
        assert result["needs_compaction"] is False
        assert result["over_budget_agents"] == []

    def test_within_budget_no_compaction(self):
        ctx = AssembledContext(agent_type=AgentType.MONITOR, budget=4000, total_tokens=1000)
        result = after_cycle(assembled_contexts=[ctx])
        assert result["needs_compaction"] is False
        assert result["over_budget_agents"] == []
        assert result["avg_utilization"] == 0.25

    def test_over_budget_detected(self):
        ctx = AssembledContext(agent_type=AgentType.EXPERT, budget=14000, total_tokens=20000)
        result = after_cycle(assembled_contexts=[ctx])
        assert "expert" in result["over_budget_agents"]
        assert result["avg_utilization"] > 1.0

    def test_compaction_recommended_after_3_cycles(self):
        """After 3 consecutive over-budget cycles, compaction is recommended."""
        ctx = AssembledContext(agent_type=AgentType.EXPERT, budget=14000, total_tokens=20000)
        for _ in range(2):
            result = after_cycle(assembled_contexts=[ctx])
            assert result["needs_compaction"] is False

        result = after_cycle(assembled_contexts=[ctx])
        assert result["needs_compaction"] is True

    def test_stats_tracking(self):
        ctx = AssembledContext(agent_type=AgentType.MONITOR, budget=4000, total_tokens=1000)
        after_cycle(assembled_contexts=[ctx])
        after_cycle(assembled_contexts=[ctx])
        stats = get_cycle_token_stats()
        assert len(stats) == 2
