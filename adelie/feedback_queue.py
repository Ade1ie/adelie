"""
adelie/feedback_queue.py

File-based user feedback queue.
Users can submit feedback via CLI, Telegram, or any other channel.
The orchestrator reads pending feedback each cycle and injects it
into the Expert AI's context.

Storage: .adelie/feedback/{timestamp}_{id}.json
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

from rich.console import Console

from adelie.config import ADELIE_ROOT

console = Console()

FEEDBACK_DIR = ADELIE_ROOT / "feedback"


def _ensure_dir() -> None:
    FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)


def submit_feedback(
    message: str,
    priority: str = "normal",
    source: str = "cli",
) -> dict:
    """
    Submit user feedback to the queue.

    Args:
        message: The feedback text from the user.
        priority: "low", "normal", "high", "critical"
        source: Where the feedback came from ("cli", "telegram", "web")

    Returns:
        Dict with feedback ID and path.
    """
    _ensure_dir()

    feedback_id = uuid.uuid4().hex[:8]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{ts}_{feedback_id}.json"
    filepath = FEEDBACK_DIR / filename

    data = {
        "id": feedback_id,
        "message": message,
        "priority": priority,
        "source": source,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "processed": False,
    }

    filepath.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    console.print(f"[green]✅ Feedback submitted[/green] (id: {feedback_id})")
    return {"id": feedback_id, "path": str(filepath)}


def read_pending() -> list[dict]:
    """
    Read all unprocessed feedback, ordered by timestamp (oldest first).

    Returns:
        List of feedback dicts.
    """
    _ensure_dir()
    pending = []

    for f in sorted(FEEDBACK_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if not data.get("processed", False):
                data["_path"] = str(f)
                pending.append(data)
        except (json.JSONDecodeError, Exception):
            continue

    # Sort by priority (critical > high > normal > low)
    priority_order = {"critical": 0, "high": 1, "normal": 2, "low": 3}
    pending.sort(key=lambda x: priority_order.get(x.get("priority", "normal"), 2))

    return pending


def mark_processed(feedback_id: str) -> bool:
    """
    Mark a feedback item as processed.

    Args:
        feedback_id: The feedback ID to mark.

    Returns:
        True if found and marked.
    """
    _ensure_dir()

    for f in FEEDBACK_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if data.get("id") == feedback_id:
                data["processed"] = True
                data["processed_at"] = datetime.now().isoformat(timespec="seconds")
                f.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
                return True
        except Exception:
            continue
    return False


def clear_processed() -> int:
    """Remove all processed feedback files. Returns count removed."""
    _ensure_dir()
    removed = 0
    for f in FEEDBACK_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if data.get("processed", False):
                f.unlink()
                removed += 1
        except Exception:
            continue
    return removed


def format_for_prompt(feedback_list: list[dict]) -> str:
    """Format pending feedback for injection into LLM prompts."""
    if not feedback_list:
        return ""

    lines = [f"## 🗣️ User Feedback ({len(feedback_list)} pending)\n"]
    for fb in feedback_list:
        priority_icon = {
            "critical": "🔴",
            "high": "🟠",
            "normal": "🟢",
            "low": "⚪",
        }.get(fb.get("priority", "normal"), "🟢")

        lines.append(
            f"- {priority_icon} [{fb.get('priority', 'normal').upper()}] "
            f"({fb.get('source', 'cli')}, {fb.get('timestamp', '?')}): "
            f"{fb.get('message', '')}"
        )

    lines.append(
        "\n⚠️ IMPORTANT: User feedback takes PRIORITY over autonomous decisions. "
        "Address these items in your next action plan."
    )
    return "\n".join(lines)
