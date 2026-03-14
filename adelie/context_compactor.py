"""
adelie/context_compactor.py

Context compaction for the Adelie orchestrator.
Maintains a rolling summary of past cycles and enforces a token budget
on prompts sent to AI agents, preventing unbounded context growth.

Inspired by openclaw's compaction.ts — adapted for Adelie's simpler
cycle-based architecture where context = system_state + KB content.
"""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from rich.console import Console

console = Console()


# ── Token Estimation ─────────────────────────────────────────────────────────

# Safety margin for token estimation: chars/4 is approximate,
# so we multiply by this factor for budget enforcement.
# (Inspired by openclaw's compaction.ts SAFETY_MARGIN = 1.2)
SAFETY_MARGIN = 1.2


def estimate_tokens(text: str, safe: bool = False) -> int:
    """
    Rough token estimate (chars / 4).
    Good enough for budgeting — real tokenizer adds latency for little gain.

    Args:
        text: Input text to estimate.
        safe: If True, apply SAFETY_MARGIN for conservative budgeting.
    """
    raw = max(1, len(text) // 4)
    if safe:
        return int(raw * SAFETY_MARGIN)
    return raw


# ── Cycle History ────────────────────────────────────────────────────────────


@dataclass
class CycleSummary:
    """Compact representation of one past cycle."""

    iteration: int
    state: str
    action: str
    reasoning: str
    files_written: int
    kb_total: int


class CycleHistory:
    """
    Maintains a rolling summary of past orchestrator cycles.
    Recent cycles are kept in detail; older ones are compressed into
    a single-paragraph summary to save tokens.
    """

    def __init__(self, detail_window: int = 3, max_summary_tokens: int = 500):
        self._detail_window = detail_window
        self._max_summary_tokens = max_summary_tokens
        self._recent: deque[CycleSummary] = deque(maxlen=detail_window)
        self._compressed_summary: str = ""
        self._total_cycles: int = 0

    def record(
        self,
        iteration: int,
        state: str,
        expert_output: dict | None,
        files_written: int = 0,
        kb_total: int = 0,
    ) -> None:
        """Record a completed cycle."""
        self._total_cycles += 1

        summary = CycleSummary(
            iteration=iteration,
            state=state,
            action=expert_output.get("action", "?") if expert_output else "?",
            reasoning=_truncate(
                expert_output.get("reasoning", "") if expert_output else "", 100
            ),
            files_written=files_written,
            kb_total=kb_total,
        )

        # If deque is full, compress the oldest into the rolling summary
        if len(self._recent) >= self._detail_window:
            oldest = self._recent[0]
            self._compress_oldest(oldest)

        self._recent.append(summary)

    def get_context(self) -> str:
        """
        Build a compact history context string for agent prompts.
        Returns compressed older history + detailed recent cycles.
        """
        parts: list[str] = []

        if self._compressed_summary:
            parts.append(f"## Prior History (cycles 1–{self._total_cycles - len(self._recent)})")
            parts.append(self._compressed_summary)

        if self._recent:
            parts.append("## Recent Cycles")
            for cs in self._recent:
                parts.append(
                    f"- Loop #{cs.iteration}: state={cs.state} → "
                    f"action={cs.action} | "
                    f"files={cs.files_written}, kb={cs.kb_total} | "
                    f"{cs.reasoning}"
                )

        return "\n".join(parts) if parts else ""

    @property
    def total_cycles(self) -> int:
        return self._total_cycles

    def reset(self) -> None:
        self._recent.clear()
        self._compressed_summary = ""
        self._total_cycles = 0

    def _compress_oldest(self, oldest: CycleSummary) -> None:
        """Add oldest cycle to the compressed summary, keeping it within token budget."""
        entry = (
            f"#{oldest.iteration}:{oldest.state}→{oldest.action}"
            f"(files={oldest.files_written})"
        )

        if self._compressed_summary:
            candidate = f"{self._compressed_summary}; {entry}"
        else:
            candidate = entry

        # Trim from the front if over budget
        if estimate_tokens(candidate) > self._max_summary_tokens:
            # Drop oldest entries (before first semicolon)
            parts = candidate.split("; ")
            while len(parts) > 1 and estimate_tokens("; ".join(parts)) > self._max_summary_tokens:
                parts.pop(0)
            candidate = "; ".join(parts)

        self._compressed_summary = candidate


# ── Context Budget Enforcement ───────────────────────────────────────────────


@dataclass
class ContextBudget:
    """Token budget configuration for agent prompts."""

    # Max tokens for the full user prompt (system_state + KB + history)
    max_prompt_tokens: int = 12000

    # Budget allocation (fractions of max_prompt_tokens)
    system_state_share: float = 0.15  # ~15% for system state
    kb_content_share: float = 0.50    # ~50% for KB content
    history_share: float = 0.15       # ~15% for cycle history
    expert_output_share: float = 0.20 # ~20% for expert output context


DEFAULT_BUDGET = ContextBudget()


def truncate_to_budget(text: str, max_tokens: int, label: str = "") -> str:
    """
    Truncate text to fit within a token budget.
    Uses SAFETY_MARGIN for conservative estimation.
    Adds a note if truncated so the AI knows content was cut.
    """
    current = estimate_tokens(text, safe=True)
    if current <= max_tokens:
        return text

    # Approximate character count for budget (with margin)
    max_chars = int(max_tokens * 4 / SAFETY_MARGIN)
    truncated = text[:max_chars]

    # Try to break at last newline for cleaner truncation
    last_nl = truncated.rfind("\n", max(0, max_chars - 200))
    if last_nl > max_chars // 2:
        truncated = truncated[:last_nl]

    suffix = f"\n\n[... {label} truncated: {estimate_tokens(text)} → {estimate_tokens(truncated)} tokens ...]"
    return truncated + suffix


def compact_system_state(state: dict, max_tokens: int) -> str:
    """
    Serialize system state with token budget enforcement.
    Removes verbose fields first, then truncates if still over.
    """
    # Create a compact version — drop large fields if over budget
    compact = dict(state)

    full_json = json.dumps(compact, indent=2, ensure_ascii=False)
    if estimate_tokens(full_json) <= max_tokens:
        return full_json

    # Level 1: Reduce project_tree to just stats
    if "project_tree" in compact:
        tree = compact["project_tree"]
        if isinstance(tree, str) and len(tree) > 500:
            # Keep just the header line
            first_line = tree.split("\n")[0] if "\n" in tree else tree[:200]
            compact["project_tree"] = first_line + "\n(tree details omitted for brevity)"

    full_json = json.dumps(compact, indent=2, ensure_ascii=False)
    if estimate_tokens(full_json) <= max_tokens:
        return full_json

    # Level 2: Remove source_stats entirely
    compact.pop("source_stats", None)

    full_json = json.dumps(compact, indent=2, ensure_ascii=False)
    if estimate_tokens(full_json) <= max_tokens:
        return full_json

    # Level 3: Remove project_tree entirely
    compact.pop("project_tree", None)

    full_json = json.dumps(compact, indent=2, ensure_ascii=False)
    return truncate_to_budget(full_json, max_tokens, "system state")


def compact_kb_content(kb_content: str, max_tokens: int) -> str:
    """
    Truncate KB content to fit within token budget.
    Tries to keep complete file sections rather than cutting mid-file.
    """
    if estimate_tokens(kb_content) <= max_tokens:
        return kb_content

    # Split by file sections (marked by --- or ## headers)
    sections = kb_content.split("\n---\n")
    if len(sections) <= 1:
        sections = kb_content.split("\n## ")
        if len(sections) > 1:
            sections = [sections[0]] + ["## " + s for s in sections[1:]]

    # Keep as many complete sections as fit
    kept: list[str] = []
    current_tokens = 0
    for section in sections:
        section_tokens = estimate_tokens(section)
        if current_tokens + section_tokens > max_tokens and kept:
            break
        kept.append(section)
        current_tokens += section_tokens

    result = "\n---\n".join(kept)
    if len(kept) < len(sections):
        omitted = len(sections) - len(kept)
        result += f"\n\n[... {omitted} KB section(s) omitted to fit context budget ...]"

    return result


def compact_expert_output(expert_output: dict | None, max_tokens: int) -> str:
    """Serialize expert output with budget enforcement."""
    if not expert_output:
        return "(none yet — first run)"

    full_json = json.dumps(expert_output, indent=2, ensure_ascii=False)
    if estimate_tokens(full_json) <= max_tokens:
        return full_json

    # Keep essential fields only
    compact = {
        "action": expert_output.get("action", ""),
        "reasoning": _truncate(expert_output.get("reasoning", ""), 200),
        "commands": expert_output.get("commands", [])[:5],
        "next_situation": expert_output.get("next_situation", ""),
        "coder_tasks": [
            {"name": t.get("name", ""), "layer": t.get("layer", 0)}
            for t in expert_output.get("coder_tasks", [])[:3]
        ],
    }
    return truncate_to_budget(
        json.dumps(compact, indent=2, ensure_ascii=False),
        max_tokens,
        "expert output",
    )


# ── Helpers ──────────────────────────────────────────────────────────────────


def _truncate(text: str, max_len: int) -> str:
    """Truncate string with ellipsis."""
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."


# ── LLM-based Summarization ─────────────────────────────────────────────────


def summarize_with_llm(history_text: str, max_tokens: int = 300) -> str:
    """
    Use the LLM to intelligently summarize old cycle history.
    Falls back to rule-based truncation on failure.

    Inspired by openclaw compaction.ts: summarizeWithFallback.

    Args:
        history_text: Raw history string to summarize.
        max_tokens:   Target token budget for the summary.

    Returns:
        Summarized text, or truncated original on LLM failure.
    """
    if estimate_tokens(history_text, safe=True) <= max_tokens:
        return history_text

    try:
        from adelie.llm_client import generate

        system_prompt = (
            "You are a concise summarizer. Summarize the following orchestrator "
            "cycle history into a brief paragraph. Preserve: specific iteration numbers, "
            "state transitions, file counts, and any error patterns. "
            "Remove: individual action details, reasoning text. "
            "Keep UUIDs, file paths, and numerical values EXACTLY as they appear. "
            f"Output MUST be under {max_tokens * 4} characters. "
            "Respond with ONLY the summary text, no JSON."
        )

        summary = generate(
            system_prompt=system_prompt,
            user_prompt=f"Summarize this cycle history:\n\n{history_text}",
            temperature=0.1,
        )

        # Validate the result is actually shorter
        if estimate_tokens(summary, safe=True) <= max_tokens * 1.5:
            return summary

        # LLM output too long — fall back to truncation
        console.print("[dim]  ⚠️ LLM summary too long, falling back to truncation[/dim]")
        return truncate_to_budget(history_text, max_tokens, "cycle history")

    except Exception as e:
        console.print(f"[dim]  ⚠️ LLM summarization failed ({e}), using truncation[/dim]")
        return truncate_to_budget(history_text, max_tokens, "cycle history")
