"""
adelie/agents/inform_ai.py

Inform AI agent.
Reads the entire Knowledge Base and generates a comprehensive
project status report for the user — documenting progress,
current state, and next steps.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from rich.console import Console

from adelie.config import WORKSPACE_PATH
from adelie.kb import retriever
from adelie.llm_client import generate

console = Console()

# ── Prompts ───────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are Inform AI — the project reporter in an autonomous AI loop system.

Your job:
1. Read the full Knowledge Base and system context.
2. Generate a clear, well-structured markdown status report for the USER.
3. The report should be human-readable and informative.

Report format (markdown):
# 📋 Adelie Project Status Report

## Summary
A brief description of the overall project state.

## Progress
- What has been accomplished so far
- Key files and knowledge created

## Current State
- System health (normal/error/maintenance)
- Active LLM provider and model
- Knowledge Base statistics

## Knowledge Base Contents
Summarize the key knowledge files by category.

## Next Steps
Based on the current KB and goal, recommend what should happen next.

## Issues & Warnings
Any problems detected, errors encountered, or areas of concern.

Rules:
- Write in the user's language (detect from the goal/KB content).
- Be concise but thorough.
- Format as clean markdown.
- Include specific file names and details from the KB.
- Output ONLY the markdown report, no JSON wrapping.
"""


def run(
    system_state: dict,
    goal: str = "",
    loop_iteration: int = 0,
) -> str:
    """
    Run the Inform AI agent to generate a status report.

    Args:
        system_state:   Current orchestrator state dict.
        goal:           The user's high-level goal.
        loop_iteration: Current loop count.

    Returns:
        Markdown-formatted status report string.
    """
    retriever.ensure_workspace()

    console.print(f"[blue]📋 Inform AI[/blue] generating project status report…")

    # ── Gather all KB content ─────────────────────────────────────────────────
    kb_index = retriever.get_index_summary()

    # Read all files from all categories
    all_paths: list[Path] = []
    for cat in ["skills", "logic", "dependencies", "errors", "exports", "maintenance"]:
        cat_dir = WORKSPACE_PATH / cat
        if cat_dir.exists():
            all_paths.extend(sorted(cat_dir.glob("*.md")))

    kb_content = retriever.read_files(all_paths)

    # ── Build prompt ──────────────────────────────────────────────────────────
    state_str = json.dumps(system_state, indent=2, ensure_ascii=False)
    user_prompt = f"""## Project Goal
{goal}

## System State (loop #{loop_iteration})
{state_str}

## Knowledge Base Index
{kb_index}

## Full Knowledge Base Contents
{kb_content}

Based on the above, generate a comprehensive project status report.
"""

    try:
        report = generate(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.4,
        )
    except Exception as e:
        console.print(f"[red]❌ Inform AI error: {e}[/red]")
        report = f"# ❌ Inform AI Error\n\nFailed to generate report: {e}"

    # Save report to workspace
    report_path = WORKSPACE_PATH / "exports" / "status_report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    header = f"<!-- generated: {datetime.now().isoformat(timespec='seconds')} -->\n\n"
    report_path.write_text(header + report, encoding="utf-8")

    retriever.update_index(
        "exports/status_report.md",
        tags=["report", "status", "inform"],
        summary=f"Project status report at loop #{loop_iteration}",
    )

    console.print(f"[blue]📋 Inform AI[/blue] report saved to [bold]exports/status_report.md[/bold]")
    return report
