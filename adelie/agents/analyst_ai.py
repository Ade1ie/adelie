"""
adelie/agents/analyst_ai.py

Analyst AI — strategic analysis for market fit, revenue, and growth.

Uses LLM to analyze the entire KB and produce actionable reports:
  - Market analysis & competitive landscape
  - Revenue strategy & monetization optimization
  - Growth opportunities & feature prioritization
  - User feedback synthesis (when available)

Reports saved to .adelie/analysis/
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from rich.console import Console

from adelie.config import WORKSPACE_PATH
from adelie.kb import retriever
from adelie.llm_client import generate

console = Console()

ANALYSIS_ROOT = WORKSPACE_PATH.parent / "analysis"

SYSTEM_PROMPT = """You are Analyst AI — a business strategist and market analyst in an autonomous AI loop.

You receive the project's entire Knowledge Base and must produce strategic analysis.

Output a single valid JSON object:
{
  "market_analysis": {
    "target_market": "Description of target market and users",
    "competitors": ["competitor1", "competitor2"],
    "differentiators": ["unique value prop 1", "unique value prop 2"],
    "market_size_estimate": "small/medium/large with reasoning"
  },
  "revenue_strategy": {
    "model": "SaaS subscription / freemium / one-time / etc",
    "pricing_tiers": [
      {"name": "Free", "price": "$0", "features": ["feature1"]},
      {"name": "Pro", "price": "$X/mo", "features": ["feature1", "feature2"]}
    ],
    "revenue_timeline": "When to expect first revenue"
  },
  "growth_opportunities": [
    {
      "opportunity": "Description",
      "effort": "low/medium/high",
      "impact": "low/medium/high",
      "priority": 1
    }
  ],
  "risks": [
    {
      "risk": "Description",
      "severity": "low/medium/high",
      "mitigation": "How to address"
    }
  ],
  "recommendations": ["Top 3 actionable recommendations"],
  "overall_health": "Score 1-10 with brief explanation"
}

RULES:
- Base analysis on actual KB content — don't invent product details
- Be realistic about market size and revenue projections
- Prioritize actionable, specific recommendations over generic advice
- Consider the current project phase when making recommendations
- Identify concrete risks, not hypothetical concerns
"""


def run_analysis(
    analysis_type: str = "full",
) -> dict:
    """
    Run strategic analysis based on the KB.

    Args:
        analysis_type: "full", "market", "revenue", or "growth"

    Returns:
        Analysis result dict.
    """
    console.print(f"[bold magenta]📊 Analyst AI[/bold magenta] — {analysis_type} analysis")

    # Read entire KB for context
    kb_content = []
    for cat_dir in WORKSPACE_PATH.iterdir():
        if not cat_dir.is_dir():
            continue
        for f in sorted(cat_dir.glob("*.md")):
            try:
                content = f.read_text(encoding="utf-8")
                rel = f.relative_to(WORKSPACE_PATH)
                kb_content.append(f"--- {rel} ---\n{content[:1000]}")
            except Exception:
                pass

    if not kb_content:
        console.print("[dim]  No KB content to analyze.[/dim]")
        return {}

    # Also check for coder logs
    coder_root = WORKSPACE_PATH.parent / "coder"
    if coder_root.exists():
        for log_file in coder_root.rglob("log.md"):
            try:
                content = log_file.read_text(encoding="utf-8")
                rel = log_file.relative_to(WORKSPACE_PATH.parent)
                kb_content.append(f"--- {rel} ---\n{content[:500]}")
            except Exception:
                pass

    # Also check for test results and health reports
    for subdir in ["tests/results", "monitor", "reviews"]:
        check_dir = WORKSPACE_PATH.parent / subdir
        if check_dir.exists():
            for f in sorted(check_dir.glob("*.md"))[-3:]:  # Last 3
                try:
                    content = f.read_text(encoding="utf-8")
                    rel = f.relative_to(WORKSPACE_PATH.parent)
                    kb_content.append(f"--- {rel} ---\n{content[:500]}")
                except Exception:
                    pass

    user_prompt = (
        f"## Analysis Type: {analysis_type}\n\n"
        f"## Knowledge Base Content\n\n"
        + "\n\n".join(kb_content)
        + "\n\nPerform the analysis. Output a JSON object."
    )

    try:
        raw = generate(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.4,
        )
    except Exception as e:
        console.print(f"[red]❌ Analyst AI LLM error: {e}[/red]")
        return {}

    # Parse
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group())
            except json.JSONDecodeError:
                console.print("[yellow]⚠️  Analyst AI — invalid JSON[/yellow]")
                return {}
        else:
            return {}

    # Display key findings
    health = result.get("overall_health", "N/A")
    console.print(f"  Project Health: {health}")

    recommendations = result.get("recommendations", [])
    if recommendations:
        console.print("  Top Recommendations:")
        for i, rec in enumerate(recommendations[:3], 1):
            console.print(f"    {i}. {rec}")

    growth = result.get("growth_opportunities", [])
    if growth:
        top = sorted(growth, key=lambda x: x.get("priority", 99))[:3]
        console.print(f"  Growth Opportunities: {len(growth)} identified")

    # Save report
    ANALYSIS_ROOT.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = ANALYSIS_ROOT / f"{analysis_type}_{ts}.md"

    report = (
        f"# {analysis_type.title()} Analysis — "
        f"{datetime.now().isoformat(timespec='seconds')}\n\n"
    )

    # Market
    market = result.get("market_analysis", {})
    if market:
        report += (
            f"## Market Analysis\n"
            f"- **Target Market**: {market.get('target_market', 'N/A')}\n"
            f"- **Market Size**: {market.get('market_size_estimate', 'N/A')}\n"
            f"- **Competitors**: {', '.join(market.get('competitors', []))}\n"
            f"- **Differentiators**: {', '.join(market.get('differentiators', []))}\n\n"
        )

    # Revenue
    revenue = result.get("revenue_strategy", {})
    if revenue:
        report += (
            f"## Revenue Strategy\n"
            f"- **Model**: {revenue.get('model', 'N/A')}\n"
            f"- **Timeline**: {revenue.get('revenue_timeline', 'N/A')}\n"
        )
        tiers = revenue.get("pricing_tiers", [])
        if tiers:
            report += "- **Pricing**:\n"
            for t in tiers:
                report += f"  - {t.get('name', '?')}: {t.get('price', '?')} — {', '.join(t.get('features', []))}\n"
        report += "\n"

    # Growth
    if growth:
        report += "## Growth Opportunities\n"
        for g in growth:
            report += (
                f"- **{g.get('opportunity', '?')}** "
                f"(effort: {g.get('effort', '?')}, impact: {g.get('impact', '?')}, "
                f"priority: {g.get('priority', '?')})\n"
            )
        report += "\n"

    # Risks
    risks = result.get("risks", [])
    if risks:
        report += "## Risks\n"
        for r in risks:
            report += (
                f"- **{r.get('risk', '?')}** [{r.get('severity', '?')}] — "
                f"Mitigation: {r.get('mitigation', '?')}\n"
            )
        report += "\n"

    # Recommendations
    if recommendations:
        report += "## Recommendations\n"
        for i, rec in enumerate(recommendations, 1):
            report += f"{i}. {rec}\n"

    report_path.write_text(report, encoding="utf-8")
    console.print(f"[bold magenta]📊 Analyst AI[/bold magenta] — report saved")

    return result
