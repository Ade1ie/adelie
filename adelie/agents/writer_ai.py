"""
adelie/agents/writer_ai.py

Writer AI agent.
Reads the current system state + Expert AI output and writes/updates
categorized files in the Knowledge Base workspace.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from rich.console import Console

from adelie.config import WORKSPACE_PATH, KB_CATEGORIES, PROJECT_ROOT
from adelie.context_compactor import (
    compact_system_state,
    compact_expert_output,
    DEFAULT_BUDGET,
)
from adelie.kb import retriever
from adelie.llm_client import generate
from adelie.phases import get_phase_prompt

console = Console()


def _get_project_file_snapshot_for_writer() -> str:
    """
    Provide Writer AI with scope guidance based on actual project files.
    Prevents writing deployment/security docs before code exists.
    """
    if not PROJECT_ROOT.exists():
        return ""

    SOURCE_EXTS = {".ts", ".tsx", ".js", ".jsx", ".py", ".go", ".rs", ".java", ".kt", ".vue", ".svelte"}
    SKIP_DIRS = {"node_modules", "__pycache__", ".git", ".adelie", "dist", "build", ".venv", "venv"}

    source_files = [
        p for p in PROJECT_ROOT.rglob("*")
        if p.is_file()
        and p.suffix in SOURCE_EXTS
        and not (set(p.parts) & SKIP_DIRS)
    ]
    src_count = len(source_files)

    if src_count == 0:
        return (
            "⚠️ WRITER SCOPE: No source code exists yet in this project.\n"
            "- DO NOT write deployment guides, security audits, or CI/CD pipelines.\n"
            "  Those are premature when there is no code to deploy.\n"
            "- Instead write: architecture plans, tech stack decisions, implementation\n"
            "  roadmaps, and component design documents.\n"
            "- Spec files describe FUTURE goals, not current reality."
        )
    elif src_count < 5:
        return (
            f"⚠️ WRITER SCOPE: Only {src_count} source file(s) exist (early scaffolding).\n"
            "- Focus on implementation guides, coding patterns, and API specs.\n"
            "- Deployment/security docs are premature at this stage.\n"
            "- Prioritize writing content that helps the Coder AI build features."
        )
    else:
        return f"✅ WRITER SCOPE: {src_count} source files found — all documentation types are appropriate."


def _list_existing_files() -> str:
    """Build a summary of all existing KB files per category for the Writer AI prompt."""
    lines = []
    for cat in KB_CATEGORIES:
        cat_dir = WORKSPACE_PATH / cat
        if cat_dir.exists():
            files = sorted(f.name for f in cat_dir.glob("*.md"))
        else:
            files = []
        count = len(files)
        if files:
            lines.append(f"- {cat}/ ({count} file{'s' if count != 1 else ''}): {', '.join(files)}")
        else:
            lines.append(f"- {cat}/ (0 files) ← EMPTY, needs content!")
    return "\n".join(lines)

# ── Prompts ───────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are Writer AI — the knowledge curator in an autonomous AI loop system.

Your job:
1. Read the current system context and Expert AI's latest output.
2. Decide what knowledge to write or update in the Knowledge Base.
3. Output a JSON array of file write operations.

Knowledge Base categories (use ONLY these exact names):
- skills         : How-to guides, procedures, capabilities
- dependencies   : External APIs, libraries, services
- errors         : Known errors, root causes, recovery strategies
- logic          : Command logic, decision patterns, planning
- exports        : Results or data for external use
- maintenance    : System health notes, status updates

IMPORTANT FILENAME RULES:
- Do NOT include the category name in the filename. The category is separate.
- Use short, descriptive filenames: "api_design.md", "authentication.md"
- BAD: "skills_api_design.md", "logic_bootstrap.md"
- GOOD: "api_design.md", "bootstrap.md"
- If updating an existing file, use the SAME filename to overwrite it.

Output ONLY a valid JSON array (no markdown fences, no extra text):
[
  {
    "category": "<one of the 6 categories above, no trailing slash>",
    "filename": "<short_descriptive_name.md>",
    "tags": ["tag1", "tag2"],
    "summary": "One-line description",
    "content": "Full markdown content of the file"
  }
]

If nothing new needs to be written, output an empty array: []
Do NOT repeat or regenerate files that already exist with the same content.
"""


def run(
    system_state: dict,
    expert_output: dict | None = None,
    loop_iteration: int = 0,
) -> list[dict]:
    """
    Run the Writer AI agent for one cycle.

    Returns:
        List of write operations performed (for logging).
    """
    retriever.ensure_workspace()

    # Build prompt context — with token budget enforcement
    kb_summary = retriever.get_index_summary()
    budget = DEFAULT_BUDGET
    state_budget = int(budget.max_prompt_tokens * budget.system_state_share)
    expert_budget = int(budget.max_prompt_tokens * budget.expert_output_share)
    state_str = compact_system_state(system_state, state_budget)
    expert_str = compact_expert_output(expert_output, expert_budget)

    # Inject phase-specific directives
    phase = system_state.get("phase", "initial")
    phase_directive = get_phase_prompt(phase, "writer")

    # Load project goal if it exists
    goal_content = ""
    goal_path = WORKSPACE_PATH / "logic" / "project_goal.md"
    if goal_path.exists():
        try:
            goal_content = goal_path.read_text(encoding="utf-8")
        except Exception:
            pass

    user_prompt = f"""{phase_directive}

{f"## Project Goal{chr(10)}{goal_content}{chr(10)}" if goal_content else ""}
## Current System State (loop #{loop_iteration})
{state_str}

## Expert AI Last Output
{expert_str}

## Current Knowledge Base Index
{kb_summary}

## Existing KB Files (DO NOT rewrite these unless content is genuinely outdated)
{_list_existing_files()}

## DIVERSIFICATION RULES
- You MUST create NEW files with NEW filenames, not update the same files repeatedly.
- If a category has 0 files, prioritize creating a file there.
- Only update existing files if there is genuinely new information to add.
- Focus on creating files that cover DIFFERENT topics than what already exists.
- If the KB already has planning docs, create implementation/technical docs instead.

## SCOPE GUIDANCE — Read Before Writing
{_get_project_file_snapshot_for_writer()}

Based on the above context, what knowledge files should be created or updated?
Do NOT recreate files with roughly the same content as existing ones.
Remember: output ONLY a valid JSON array.
"""

    console.print(f"[cyan]📝 Writer AI[/cyan] generating knowledge updates (loop #{loop_iteration})…")

    MAX_WRITER_JSON_RETRIES = 1
    operations: list[dict] = []
    current_prompt = user_prompt

    for attempt in range(MAX_WRITER_JSON_RETRIES + 1):
        try:
            raw = generate(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=current_prompt,
                temperature=0.4,
            )
            operations = json.loads(raw)
            if isinstance(operations, list):
                break
            console.print(f"[yellow]⚠️  Writer AI returned non-list JSON (attempt {attempt + 1}) — retrying.[/yellow]")
            operations = []
        except json.JSONDecodeError:
            # Try regex extraction
            match = re.search(r'\[.*\]', raw, re.DOTALL)
            if match:
                try:
                    operations = json.loads(match.group())
                    if isinstance(operations, list):
                        break
                except json.JSONDecodeError:
                    pass

            if attempt < MAX_WRITER_JSON_RETRIES:
                console.print(f"[yellow]⚠️  Writer AI returned invalid JSON (retry {attempt + 1}).[/yellow]")
                current_prompt = (
                    user_prompt
                    + "\n\n⚠️ PREVIOUS OUTPUT WAS NOT VALID JSON. "
                    "Output ONLY a valid JSON array — no markdown fences, no extra text. "
                    "The output must start with [ and end with ]."
                )
                continue
            console.print(f"[yellow]⚠️  Writer AI JSON parse failed after retries — skipping.[/yellow]")
            return []
        except Exception as e:
            console.print(f"[red]❌ Writer AI error: {e}[/red]")
            raise

    if not isinstance(operations, list):
        console.print("[yellow]⚠️  Writer AI returned non-list JSON — skipping.[/yellow]")
        return []

    written: list[dict] = []
    for op in operations:
        cat = op.get("category", "").strip().rstrip("/")
        filename = op.get("filename", "").strip()
        tags = op.get("tags", [])
        summary = op.get("summary", "")
        content = op.get("content", "")

        # Validate category
        if cat not in KB_CATEGORIES:
            console.print(f"[yellow]⚠️  Unknown category '{cat}' — skipping.[/yellow]")
            continue
        if not filename:
            continue

        # Sanitize filename — strip category prefix if the LLM included it
        filename = re.sub(r"[^\w\-. ]", "_", filename).replace(" ", "_")
        # Remove category prefix from filename (e.g., "logic_bootstrap.md" → "bootstrap.md")
        for prefix in KB_CATEGORIES:
            if filename.lower().startswith(f"{prefix}_"):
                filename = filename[len(prefix) + 1:]
                break
        # Strip version suffixes (_v2, _v3, etc.) — always update original
        filename = re.sub(r"_v\d+\.md$", ".md", filename)
        if not filename.endswith(".md"):
            filename += ".md"

        # Per-category file cap — max 8 files per category
        MAX_FILES_PER_CATEGORY = 8
        cat_dir = WORKSPACE_PATH / cat
        existing_files = sorted(cat_dir.glob("*.md"), key=lambda f: f.stat().st_mtime) if cat_dir.exists() else []
        if len(existing_files) >= MAX_FILES_PER_CATEGORY and not (cat_dir / filename).exists():
            # Replace the oldest file
            oldest = existing_files[0]
            console.print(f"[dim]  🔄 Category '{cat}' full — replacing {oldest.name}[/dim]")
            oldest.unlink()
            # Also remove from index
            old_rel = f"{cat}/{oldest.name}"
            index = retriever.get_index()
            if old_rel in index:
                del index[old_rel]
                retriever.INDEX_FILE.write_text(json.dumps(index, indent=2), encoding="utf-8")

        out_path: Path = WORKSPACE_PATH / cat / filename

        # Avoid overwriting with similar content
        if out_path.exists():
            existing = out_path.read_text(encoding="utf-8")
            # Strip metadata headers for comparison
            existing_body = "\n".join(
                l for l in existing.splitlines() if not l.startswith("<!--")
            ).strip()
            new_body = content.strip()

            # Exact match → skip
            if existing_body == new_body:
                console.print(f"[dim]  ⏭  Skipped {cat}/{filename} (unchanged)[/dim]")
                continue

            # Fuzzy similarity: if content length difference < 10%, likely just a rewrite
            len_existing = len(existing_body)
            len_new = len(new_body)
            if len_existing > 100 and len_new > 100:
                ratio = min(len_existing, len_new) / max(len_existing, len_new)
                if ratio > 0.90:
                    # Check first 200 chars — if very similar, skip
                    compare_len = min(200, len(existing_body), len(new_body))
                    if compare_len < 20:
                        pass  # Too short to compare meaningfully
                    else:
                        common_start = 0
                        for a, b in zip(existing_body[:compare_len], new_body[:compare_len]):
                            if a == b:
                                common_start += 1
                        if common_start / compare_len > 0.7:
                            console.print(f"[dim]  ⏭  Skipped {cat}/{filename} (similar content)[/dim]")
                            continue

        # Prepend a frontmatter header for human readability
        header = (
            f"<!-- tags: {', '.join(tags)} -->\n"
            f"<!-- summary: {summary} -->\n"
            f"<!-- updated: {datetime.now().isoformat(timespec='seconds')} -->\n\n"
        )
        out_path.write_text(header + content, encoding="utf-8")

        # Update KB index
        rel = f"{cat}/{filename}"
        retriever.update_index(rel, tags, summary)

        console.print(f"[green]  ✓ Wrote[/green] [bold]{rel}[/bold]")
        written.append({"path": rel, "tags": tags, "summary": summary})

    console.print(f"[cyan]📝 Writer AI[/cyan] done — {len(written)} file(s) written.")
    return written
