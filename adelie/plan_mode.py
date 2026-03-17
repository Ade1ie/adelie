"""
adelie/plan_mode.py

Plan Mode — generates a change plan and waits for user approval
before executing code changes.

When PLAN_MODE is enabled, the orchestrator will:
1. Receive Expert AI's coder_tasks
2. Generate a human-readable plan
3. Save it to .adelie/plans/
4. Wait for user approval via interactive CLI
5. Execute only after approval

Inspired by gemini-cli's Plan Mode.
"""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from adelie.config import ADELIE_ROOT


PLANS_DIR = ADELIE_ROOT / "plans"


class PlanStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class Plan:
    """A change plan awaiting approval."""

    def __init__(
        self,
        plan_id: str,
        cycle: int,
        coder_tasks: list[dict],
        expert_reasoning: str = "",
        status: PlanStatus = PlanStatus.PENDING,
        created_at: str = "",
        reviewed_at: str = "",
        reject_reason: str = "",
    ):
        self.plan_id = plan_id
        self.cycle = cycle
        self.coder_tasks = coder_tasks
        self.expert_reasoning = expert_reasoning
        self.status = status
        self.created_at = created_at or datetime.now().isoformat(timespec="seconds")
        self.reviewed_at = reviewed_at
        self.reject_reason = reject_reason

    def to_dict(self) -> dict:
        return {
            "plan_id": self.plan_id,
            "cycle": self.cycle,
            "coder_tasks": self.coder_tasks,
            "expert_reasoning": self.expert_reasoning,
            "status": self.status.value,
            "created_at": self.created_at,
            "reviewed_at": self.reviewed_at,
            "reject_reason": self.reject_reason,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Plan":
        return cls(
            plan_id=data["plan_id"],
            cycle=data.get("cycle", 0),
            coder_tasks=data.get("coder_tasks", []),
            expert_reasoning=data.get("expert_reasoning", ""),
            status=PlanStatus(data.get("status", "pending")),
            created_at=data.get("created_at", ""),
            reviewed_at=data.get("reviewed_at", ""),
            reject_reason=data.get("reject_reason", ""),
        )

    def render_markdown(self) -> str:
        """Render plan as human-readable markdown."""
        lines = [
            f"# Change Plan — {self.plan_id}",
            f"",
            f"**Cycle**: #{self.cycle}  |  **Status**: {self.status.value}  |  **Created**: {self.created_at}",
            f"",
        ]

        if self.expert_reasoning:
            lines.append(f"## Expert AI Reasoning")
            lines.append(f"{self.expert_reasoning}")
            lines.append("")

        lines.append(f"## Planned Tasks ({len(self.coder_tasks)})")
        lines.append("")

        for i, task in enumerate(self.coder_tasks, 1):
            name = task.get("name", f"task_{i}")
            desc = task.get("task", task.get("description", "(no description)"))
            layer = task.get("layer", 0)
            files = task.get("target_files", [])

            lines.append(f"### {i}. {name} (Layer {layer})")
            lines.append(f"{desc}")
            if files:
                lines.append(f"")
                lines.append(f"**Target files**: {', '.join(files)}")
            lines.append("")

        if self.reject_reason:
            lines.append(f"## Rejection Reason")
            lines.append(f"{self.reject_reason}")
            lines.append("")

        return "\n".join(lines)


class PlanManager:
    """
    Manages the plan approval workflow.

    Usage:
        manager = PlanManager()
        plan = manager.create_plan(cycle=5, coder_tasks=[...], reasoning="...")
        # User reviews...
        manager.approve(plan.plan_id)
        # or
        manager.reject(plan.plan_id, "Need more detail on migration")
    """

    def __init__(self):
        PLANS_DIR.mkdir(parents=True, exist_ok=True)

    def create_plan(
        self,
        cycle: int,
        coder_tasks: list[dict],
        expert_reasoning: str = "",
    ) -> Plan:
        """Create a new plan awaiting approval."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        plan_id = f"plan_{ts}"

        plan = Plan(
            plan_id=plan_id,
            cycle=cycle,
            coder_tasks=coder_tasks,
            expert_reasoning=expert_reasoning,
        )

        self._save(plan)
        return plan

    def approve(self, plan_id: str) -> bool:
        """Approve a pending plan."""
        plan = self.get(plan_id)
        if not plan or plan.status != PlanStatus.PENDING:
            return False
        plan.status = PlanStatus.APPROVED
        plan.reviewed_at = datetime.now().isoformat(timespec="seconds")
        self._save(plan)
        return True

    def reject(self, plan_id: str, reason: str = "") -> bool:
        """Reject a pending plan."""
        plan = self.get(plan_id)
        if not plan or plan.status != PlanStatus.PENDING:
            return False
        plan.status = PlanStatus.REJECTED
        plan.reviewed_at = datetime.now().isoformat(timespec="seconds")
        plan.reject_reason = reason
        self._save(plan)
        return True

    def get(self, plan_id: str) -> Optional[Plan]:
        """Get a plan by ID."""
        plan_file = PLANS_DIR / f"{plan_id}.json"
        if not plan_file.exists():
            return None
        try:
            data = json.loads(plan_file.read_text(encoding="utf-8"))
            return Plan.from_dict(data)
        except Exception:
            return None

    def get_pending(self) -> Optional[Plan]:
        """Get the currently pending plan (most recent)."""
        pending = []
        for f in sorted(PLANS_DIR.glob("plan_*.json"), reverse=True):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if data.get("status") == PlanStatus.PENDING.value:
                    pending.append(Plan.from_dict(data))
            except Exception:
                continue
        return pending[0] if pending else None

    def get_recent(self, limit: int = 5) -> list[Plan]:
        """Get recent plans."""
        plans = []
        for f in sorted(PLANS_DIR.glob("plan_*.json"), reverse=True)[:limit]:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                plans.append(Plan.from_dict(data))
            except Exception:
                continue
        return plans

    def expire_old_pending(self) -> int:
        """Expire pending plans that are too old (> 1 hour)."""
        from datetime import timedelta
        expired = 0
        cutoff = datetime.now() - timedelta(hours=1)

        for f in PLANS_DIR.glob("plan_*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if data.get("status") != PlanStatus.PENDING.value:
                    continue
                created = datetime.fromisoformat(data.get("created_at", ""))
                if created < cutoff:
                    data["status"] = PlanStatus.EXPIRED.value
                    f.write_text(json.dumps(data, indent=2), encoding="utf-8")
                    expired += 1
            except Exception:
                continue

        return expired

    def _save(self, plan: Plan) -> None:
        """Save a plan to disk."""
        plan_file = PLANS_DIR / f"{plan.plan_id}.json"
        plan_file.write_text(
            json.dumps(plan.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        # Also save the markdown version
        md_file = PLANS_DIR / f"{plan.plan_id}.md"
        md_file.write_text(plan.render_markdown(), encoding="utf-8")
