"""
adelie/agents/dynamic_agent.py

DynamicAgent — runtime-configurable agent class.

Created from harness.json's dynamic_agents definitions, these agents
receive their role, prompt, and constraints at instantiation time.
They participate in the pipeline like any built-in agent but can be
added/removed by Expert AI via MODIFY_HARNESS.

Permission model:
  - observer: KB read only
  - analyst:  KB read + write + export (default for dynamic agents)
  - operator: Above + coder task creation (requires user approval)
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from rich.console import Console

from adelie.harness_manager import AgentPermission
from adelie.kb import retriever
from adelie.llm_client import generate

console = Console()


class DynamicAgent:
    """
    An agent whose role and prompt are defined at runtime.

    Attributes:
        name:          Unique identifier (e.g., "solidity_auditor_ai")
        prompt_template: System prompt that defines the agent's personality
        active_in_phases: List of phase IDs where this agent runs
        permission:    AgentPermission level
        schedule:      Scheduling config (frequency, interval)
        config:        Full raw config from harness.json
    """

    def __init__(self, config: dict):
        self.name: str = config["name"]
        self.prompt_template: str = config.get("prompt_template", "")
        self.active_in_phases: list[str] = config.get("active_in_phases", [])

        perms = config.get("permissions", {})
        self.permission = AgentPermission(
            perms.get("level", AgentPermission.ANALYST.value)
        )
        self.can_write_kb: bool = perms.get("kb_write", True)
        self.can_export: bool = perms.get("export", True)
        self.can_create_coder_tasks: bool = perms.get("coder_layer_access", False)

        self.schedule: dict = config.get("schedule", {"frequency": "every_cycle"})
        self.config: dict = config

    def is_active_in(self, phase: str) -> bool:
        """Check if this agent should run in the given phase."""
        return phase in self.active_in_phases

    def run(
        self,
        system_state: dict,
        loop_iteration: int = 0,
        extra_context: str = "",
    ) -> dict:
        """
        Execute this dynamic agent for one cycle.

        Args:
            system_state:   Current orchestrator state
            loop_iteration: Current loop iteration
            extra_context:  Additional context to inject

        Returns:
            dict with agent's structured output:
              - analysis: str         — Agent's analysis/findings
              - recommendations: list — Actionable recommendations
              - kb_updates: list      — KB files to create/update (if analyst+)
              - coder_tasks: list     — Coder tasks (only if operator permission)
              - severity: str         — "info" | "warning" | "critical"
        """
        console.print(
            f"[cyan]🔧 {self.name}[/cyan] running (permission={self.permission.value})…"
        )

        # Build prompt
        system_prompt = self.prompt_template or (
            f"You are {self.name} — a specialized AI agent in the Adelie autonomous loop.\n"
            f"Output a single valid JSON object with: analysis, recommendations, "
            f"kb_updates, severity fields."
        )

        # Restrict output schema based on permission
        output_schema = {
            "analysis": "Your detailed analysis/findings as a string",
            "recommendations": ["List of actionable recommendation strings"],
            "severity": "info | warning | critical",
        }

        if self.can_write_kb:
            output_schema["kb_updates"] = [
                {"category": "skills|logic|dependencies", "filename": "file.md", "content": "..."}
            ]

        if self.can_create_coder_tasks:
            output_schema["coder_tasks"] = [
                {"layer": 0, "name": "coder_name", "task": "description", "files": []}
            ]

        state_str = json.dumps(system_state, indent=2, ensure_ascii=False)

        user_prompt = f"""## System State (loop #{loop_iteration})
{state_str}

{extra_context}

## Your Task
Analyze the current project state according to your role.
Output ONLY a valid JSON object with these fields:
{json.dumps(output_schema, indent=2)}

Remember: output ONLY a valid JSON object.
"""

        try:
            raw = generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.3,
            )
            result = json.loads(raw)
        except json.JSONDecodeError:
            # Try to extract JSON from response
            import re
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                try:
                    result = json.loads(match.group())
                except json.JSONDecodeError:
                    result = self._fallback_result("JSON parse error")
            else:
                result = self._fallback_result("No JSON in response")
        except Exception as e:
            console.print(f"[red]❌ {self.name} error: {e}[/red]")
            result = self._fallback_result(str(e))

        # Enforce permissions — strip unauthorized fields
        if not self.can_write_kb:
            result.pop("kb_updates", None)
        if not self.can_create_coder_tasks:
            result.pop("coder_tasks", None)

        # Write KB updates if permitted
        if self.can_write_kb and result.get("kb_updates"):
            self._apply_kb_updates(result["kb_updates"])

        severity = result.get("severity", "info")
        analysis_preview = (result.get("analysis", "")[:80] + "…") if result.get("analysis") else "no analysis"
        console.print(
            f"[cyan]🔧 {self.name}[/cyan] → severity=[bold]{severity}[/bold]  {analysis_preview}"
        )

        return result

    def _apply_kb_updates(self, updates: list[dict]) -> None:
        """Write KB updates from the agent's output."""
        from adelie.config import WORKSPACE_PATH

        for update in updates:
            if not isinstance(update, dict):
                continue
            category = update.get("category", "logic")
            filename = update.get("filename", "")
            content = update.get("content", "")
            if not filename or not content:
                continue

            file_path = WORKSPACE_PATH / category / filename
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")

            rel = f"{category}/{filename}"
            retriever.update_index(
                rel,
                tags=[self.name, "dynamic-agent"],
                summary=f"Written by dynamic agent {self.name}",
            )
            console.print(
                f"  [dim]📝 {self.name} wrote: {rel}[/dim]"
            )

    def _fallback_result(self, reason: str) -> dict:
        """Return a safe fallback result."""
        return {
            "analysis": f"Agent {self.name} failed: {reason}",
            "recommendations": [],
            "severity": "info",
        }

    def __repr__(self) -> str:
        return (
            f"DynamicAgent(name={self.name!r}, "
            f"phases={self.active_in_phases}, "
            f"permission={self.permission.value})"
        )


# ── Factory ──────────────────────────────────────────────────────────────────


def create_dynamic_agents(agent_configs: list[dict]) -> dict[str, DynamicAgent]:
    """
    Create DynamicAgent instances from harness config.

    Args:
        agent_configs: List of agent config dicts from harness.json

    Returns:
        Dict mapping agent name → DynamicAgent instance
    """
    agents = {}
    for config in agent_configs:
        if not isinstance(config, dict) or "name" not in config:
            continue
        try:
            agent = DynamicAgent(config)
            agents[agent.name] = agent
        except Exception as e:
            console.print(f"[yellow]⚠️  Failed to create agent '{config.get('name', '?')}': {e}[/yellow]")
    return agents
