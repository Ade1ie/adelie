"""
adelie/agents/reviewer_ai.py

Reviewer AI — reviews code produced by Coder AI for quality and bugs.

Uses LLM to analyze source files and generates review reports with
severity levels: CRITICAL, WARNING, INFO.

Reports are saved to .adelie/reviews/{coder}_{timestamp}.md
If CRITICAL issues are found, the review result signals the orchestrator
to request a Coder re-run.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from rich.console import Console

from adelie.config import WORKSPACE_PATH, PROJECT_ROOT
from adelie.llm_client import generate
from adelie.rules_loader import get_rules_prompt_section, get_context_prompt_section
from adelie.prompt_loader import load_prompt
from adelie.skill_manager import get_skills_prompt_section

console = Console()

REVIEW_ROOT = WORKSPACE_PATH.parent / "reviews"

_FALLBACK_PROMPT = """You are Reviewer AI — a senior code reviewer in an autonomous AI loop.
Output a single valid JSON object with overall_score, issues, summary, and approved fields."""

SYSTEM_PROMPT = load_prompt("reviewer", _FALLBACK_PROMPT)


def run_review(
    coder_name: str,
    written_files: list[dict],
    workspace_root: Path | None = None,
) -> dict:
    """
    Review code files produced by a coder.

    Args:
        coder_name: which coder produced the files
        written_files: list of {"filepath": ..., "language": ..., "description": ...}
        workspace_root: project root directory

    Returns:
        Review result dict with issues, score, and approved flag.
    """
    if workspace_root is None:
        workspace_root = PROJECT_ROOT

    if not written_files:
        return {"overall_score": 10, "issues": [], "summary": "No files to review.", "approved": True}

    console.print(f"[bold magenta]🔍 Reviewer AI[/bold magenta] — reviewing {coder_name} ({len(written_files)} file(s))")

    # Read the actual file contents
    file_contents = []
    for finfo in written_files:
        fp = finfo.get("filepath", "")
        full_path = workspace_root / fp
        if full_path.exists():
            try:
                content = full_path.read_text(encoding="utf-8")
                lang = finfo.get("language", "")
                file_contents.append(
                    f"--- {fp} ({lang}) ---\n{content}"
                )
            except Exception:
                file_contents.append(f"--- {fp} --- (could not read)")
        else:
            file_contents.append(f"--- {fp} --- (file not found)")

    # Get active policy constraints summary
    policy_section = ""
    try:
        from adelie.policy_engine import PolicyEngine
        engine = PolicyEngine()
        policy_section = engine.get_prompt_summary()
    except Exception:
        pass

    user_prompt = (
        f"## Coder: {coder_name}\n"
        f"## Files to Review\n\n"
        + "\n\n".join(file_contents)
        + f"\n\n{get_context_prompt_section()}{get_rules_prompt_section()}{get_skills_prompt_section('reviewer')}"
        + policy_section
        + "\n\nReview these files and output a JSON object."
    )

    try:
        raw = generate(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.2,
        )
    except Exception as e:
        console.print(f"[red]❌ Reviewer AI error: {e}[/red]")
        return {"overall_score": 0, "issues": [], "summary": f"Review failed: {e} — rejecting for safety.", "approved": False}

    # Parse
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group())
            except json.JSONDecodeError:
                result = {"overall_score": 0, "issues": [], "summary": "Could not parse review — rejecting for safety.", "approved": False}
        else:
            result = {"overall_score": 0, "issues": [], "summary": "Could not parse review — rejecting for safety.", "approved": False}

    issues = result.get("issues", [])
    score = result.get("overall_score", 5)
    approved = result.get("approved", True)
    summary = result.get("summary", "")

    # Count by severity
    critical = sum(1 for i in issues if i.get("severity") == "CRITICAL")
    warnings = sum(1 for i in issues if i.get("severity") == "WARNING")
    infos = sum(1 for i in issues if i.get("severity") == "INFO")

    # Display
    score_color = "green" if score >= 7 else "yellow" if score >= 4 else "red"
    console.print(
        f"  Score: [{score_color}]{score}/10[/{score_color}] | "
        f"🔴 {critical} critical | ⚠️  {warnings} warnings | ℹ️  {infos} info"
    )

    if not approved:
        console.print(f"  [red]❌ Review REJECTED — critical issues found[/red]")
    else:
        console.print(f"  [green]✅ Review APPROVED[/green]")

    # Save review report
    REVIEW_ROOT.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = REVIEW_ROOT / f"{coder_name}_{ts}.md"

    report = (
        f"# Code Review: {coder_name}\n"
        f"**Date**: {datetime.now().isoformat(timespec='seconds')}\n"
        f"**Score**: {score}/10\n"
        f"**Approved**: {'✅ Yes' if approved else '❌ No'}\n\n"
        f"## Summary\n{summary}\n\n"
    )

    if issues:
        report += "## Issues\n\n"
        for issue in issues:
            sev = issue.get("severity", "INFO")
            icon = "🔴" if sev == "CRITICAL" else "⚠️" if sev == "WARNING" else "ℹ️"
            line_info = f" (line {issue.get('line')})" if issue.get('line') else ""
            report += (
                f"### {icon} [{sev}] {issue.get('title', 'Untitled')}\n"
                f"- **File**: `{issue.get('file', '?')}`{line_info}\n"
                f"- **Description**: {issue.get('description', '')}\n"
                f"- **Suggestion**: {issue.get('suggestion', '')}\n\n"
            )

    report += f"\n## Files Reviewed\n"
    for finfo in written_files:
        report += f"- `{finfo.get('filepath', '?')}` — {finfo.get('description', '')}\n"

    report_path.write_text(report, encoding="utf-8")

    return result
