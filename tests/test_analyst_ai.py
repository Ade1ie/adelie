"""tests/test_analyst_ai.py — Tests for Analyst AI (mocks LLM)."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest


MOCK_ANALYSIS = {
    "market_analysis": {
        "target_market": "Small businesses",
        "competitors": ["Competitor A"],
        "differentiators": ["AI-powered"],
        "market_size_estimate": "medium",
    },
    "revenue_strategy": {
        "model": "SaaS subscription",
        "pricing_tiers": [{"name": "Free", "price": "$0", "features": ["basic"]}],
        "revenue_timeline": "3 months",
    },
    "growth_opportunities": [
        {"opportunity": "API integrations", "effort": "medium", "impact": "high", "priority": 1}
    ],
    "risks": [
        {"risk": "Market competition", "severity": "medium", "mitigation": "Focus on niche"}
    ],
    "recommendations": ["Launch MVP fast", "Get user feedback", "Iterate weekly"],
    "overall_health": "7/10 — Good foundation",
}


@pytest.fixture
def tmp_workspace(tmp_path, monkeypatch):
    import adelie.config as cfg
    import adelie.kb.retriever as r
    ws = tmp_path / ".adelie" / "kb"
    ws.mkdir(parents=True)
    monkeypatch.setattr(cfg, "WORKSPACE_PATH", ws)
    monkeypatch.setattr(r, "WORKSPACE_PATH", ws)
    monkeypatch.setattr(r, "INDEX_FILE", ws / "index.json")
    r.ensure_workspace()
    return tmp_path


class TestAnalystAI:
    def test_returns_analysis(self, tmp_workspace, monkeypatch):
        import adelie.agents.analyst_ai as a
        monkeypatch.setattr(a, "WORKSPACE_PATH", tmp_workspace / ".adelie" / "kb")
        monkeypatch.setattr(a, "ANALYSIS_ROOT", tmp_workspace / ".adelie" / "analysis")

        # Write some KB files
        skills_dir = tmp_workspace / ".adelie" / "kb" / "skills"
        skills_dir.mkdir(exist_ok=True)
        (skills_dir / "vision.md").write_text("# Product Vision\nA SaaS app", encoding="utf-8")

        with patch("adelie.agents.analyst_ai.generate") as mock_gen:
            mock_gen.return_value = json.dumps(MOCK_ANALYSIS)
            result = a.run_analysis(analysis_type="full")

        assert result["overall_health"] == "7/10 — Good foundation"
        assert len(result["recommendations"]) == 3

    def test_saves_report(self, tmp_workspace, monkeypatch):
        import adelie.agents.analyst_ai as a
        analysis_dir = tmp_workspace / ".adelie" / "analysis"
        monkeypatch.setattr(a, "WORKSPACE_PATH", tmp_workspace / ".adelie" / "kb")
        monkeypatch.setattr(a, "ANALYSIS_ROOT", analysis_dir)

        skills_dir = tmp_workspace / ".adelie" / "kb" / "skills"
        skills_dir.mkdir(exist_ok=True)
        (skills_dir / "arch.md").write_text("# Architecture\nMicroservices", encoding="utf-8")

        with patch("adelie.agents.analyst_ai.generate") as mock_gen:
            mock_gen.return_value = json.dumps(MOCK_ANALYSIS)
            a.run_analysis(analysis_type="market")

        reports = list(analysis_dir.glob("market_*.md"))
        assert len(reports) == 1
        content = reports[0].read_text()
        assert "Small businesses" in content

    def test_empty_kb_returns_empty(self, tmp_workspace, monkeypatch):
        import adelie.agents.analyst_ai as a
        monkeypatch.setattr(a, "WORKSPACE_PATH", tmp_workspace / ".adelie" / "kb")
        # KB is empty — no files to analyze
        result = a.run_analysis(analysis_type="full")
        assert result == {}
