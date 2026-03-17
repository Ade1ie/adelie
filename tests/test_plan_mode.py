"""tests/test_plan_mode.py — Tests for Plan Mode module."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def plans_dir(tmp_path):
    """Use a temp directory for plans."""
    plans = tmp_path / "plans"
    plans.mkdir()
    return plans


@pytest.fixture
def plan_manager(plans_dir):
    """PlanManager with temp directory."""
    with patch("adelie.plan_mode.PLANS_DIR", plans_dir):
        from adelie.plan_mode import PlanManager
        return PlanManager()


# ── Plan Creation Tests ──────────────────────────────────────────────────────


class TestPlanCreation:
    def test_create_plan(self, plan_manager, plans_dir):
        with patch("adelie.plan_mode.PLANS_DIR", plans_dir):
            plan = plan_manager.create_plan(
                cycle=5,
                coder_tasks=[{"name": "task1", "task": "Fix bug"}],
                expert_reasoning="Bug needs fixing",
            )
            assert plan.plan_id.startswith("plan_")
            assert plan.cycle == 5
            assert len(plan.coder_tasks) == 1
            assert plan.status.value == "pending"
            assert plan.expert_reasoning == "Bug needs fixing"

    def test_plan_saved_to_disk(self, plan_manager, plans_dir):
        with patch("adelie.plan_mode.PLANS_DIR", plans_dir):
            plan = plan_manager.create_plan(cycle=1, coder_tasks=[])
            json_file = plans_dir / f"{plan.plan_id}.json"
            md_file = plans_dir / f"{plan.plan_id}.md"
            assert json_file.exists()
            assert md_file.exists()

    def test_plan_json_is_valid(self, plan_manager, plans_dir):
        with patch("adelie.plan_mode.PLANS_DIR", plans_dir):
            plan = plan_manager.create_plan(cycle=3, coder_tasks=[{"name": "t1", "task": "build"}])
            json_file = plans_dir / f"{plan.plan_id}.json"
            data = json.loads(json_file.read_text())
            assert data["status"] == "pending"
            assert data["cycle"] == 3


# ── Approval / Rejection Tests ───────────────────────────────────────────────


class TestApprovalRejection:
    def test_approve_plan(self, plan_manager, plans_dir):
        with patch("adelie.plan_mode.PLANS_DIR", plans_dir):
            plan = plan_manager.create_plan(cycle=1, coder_tasks=[])
            assert plan_manager.approve(plan.plan_id)
            updated = plan_manager.get(plan.plan_id)
            assert updated.status.value == "approved"
            assert updated.reviewed_at != ""

    def test_reject_plan_with_reason(self, plan_manager, plans_dir):
        with patch("adelie.plan_mode.PLANS_DIR", plans_dir):
            plan = plan_manager.create_plan(cycle=1, coder_tasks=[])
            assert plan_manager.reject(plan.plan_id, "Too complex")
            updated = plan_manager.get(plan.plan_id)
            assert updated.status.value == "rejected"
            assert updated.reject_reason == "Too complex"

    def test_cannot_approve_rejected_plan(self, plan_manager, plans_dir):
        with patch("adelie.plan_mode.PLANS_DIR", plans_dir):
            plan = plan_manager.create_plan(cycle=1, coder_tasks=[])
            plan_manager.reject(plan.plan_id, "No")
            assert not plan_manager.approve(plan.plan_id)

    def test_cannot_reject_approved_plan(self, plan_manager, plans_dir):
        with patch("adelie.plan_mode.PLANS_DIR", plans_dir):
            plan = plan_manager.create_plan(cycle=1, coder_tasks=[])
            plan_manager.approve(plan.plan_id)
            assert not plan_manager.reject(plan.plan_id, "reason")

    def test_approve_nonexistent_returns_false(self, plan_manager, plans_dir):
        with patch("adelie.plan_mode.PLANS_DIR", plans_dir):
            assert not plan_manager.approve("plan_nonexistent")


# ── Query Tests ──────────────────────────────────────────────────────────────


class TestQueries:
    def test_get_pending(self, plan_manager, plans_dir):
        with patch("adelie.plan_mode.PLANS_DIR", plans_dir):
            plan_manager.create_plan(cycle=1, coder_tasks=[])
            pending = plan_manager.get_pending()
            assert pending is not None
            assert pending.status.value == "pending"

    def test_no_pending_after_approval(self, plan_manager, plans_dir):
        with patch("adelie.plan_mode.PLANS_DIR", plans_dir):
            plan = plan_manager.create_plan(cycle=1, coder_tasks=[])
            plan_manager.approve(plan.plan_id)
            assert plan_manager.get_pending() is None

    def test_get_recent(self, plan_manager, plans_dir):
        import time
        with patch("adelie.plan_mode.PLANS_DIR", plans_dir):
            for i in range(3):
                plan_manager.create_plan(cycle=i, coder_tasks=[])
                time.sleep(0.01)  # Avoid same-second collision
            recent = plan_manager.get_recent(limit=5)
            assert len(recent) >= 2


# ── Markdown Rendering Tests ────────────────────────────────────────────────


class TestMarkdownRendering:
    def test_render_markdown(self, plans_dir):
        from adelie.plan_mode import Plan
        with patch("adelie.plan_mode.PLANS_DIR", plans_dir):
            plan = Plan(
                plan_id="plan_test",
                cycle=5,
                coder_tasks=[
                    {"name": "create_api", "task": "Create REST API endpoint", "layer": 1},
                    {"name": "add_tests", "task": "Add unit tests", "layer": 2},
                ],
                expert_reasoning="Need new API endpoint for user management",
            )
            md = plan.render_markdown()
            assert "Change Plan" in md
            assert "create_api" in md
            assert "add_tests" in md
            assert "Expert AI Reasoning" in md


# ── Expiry Tests ─────────────────────────────────────────────────────────────


class TestExpiry:
    def test_expire_old_pending(self, plan_manager, plans_dir):
        with patch("adelie.plan_mode.PLANS_DIR", plans_dir):
            plan = plan_manager.create_plan(cycle=1, coder_tasks=[])
            # Manually set created_at to 2 hours ago
            json_file = plans_dir / f"{plan.plan_id}.json"
            data = json.loads(json_file.read_text())
            old_time = (datetime.now() - timedelta(hours=2)).isoformat(timespec="seconds")
            data["created_at"] = old_time
            json_file.write_text(json.dumps(data), encoding="utf-8")

            expired = plan_manager.expire_old_pending()
            assert expired == 1

            updated = plan_manager.get(plan.plan_id)
            assert updated.status.value == "expired"


# ── Serialization Tests ──────────────────────────────────────────────────────


class TestSerialization:
    def test_to_dict_and_from_dict(self):
        from adelie.plan_mode import Plan, PlanStatus
        plan = Plan(
            plan_id="plan_abc",
            cycle=10,
            coder_tasks=[{"name": "x", "task": "y"}],
            status=PlanStatus.APPROVED,
        )
        d = plan.to_dict()
        restored = Plan.from_dict(d)
        assert restored.plan_id == "plan_abc"
        assert restored.cycle == 10
        assert restored.status == PlanStatus.APPROVED
        assert len(restored.coder_tasks) == 1
