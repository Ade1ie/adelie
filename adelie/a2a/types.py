"""
adelie/a2a/types.py

A2A protocol types.
Inspired by Gemini CLI's a2a-server event types
(CoderAgentEvent, TaskState, TaskMetadata).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class TaskState(str, Enum):
    """Task lifecycle states."""
    SUBMITTED = "submitted"
    WORKING = "working"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class EventType(str, Enum):
    """A2A event types (Gemini CLI pattern)."""
    TEXT_CONTENT = "text-content"
    STATE_CHANGE = "state-change"
    TOOL_CALL_UPDATE = "tool-call-update"
    THOUGHT = "thought"
    ERROR = "error"


@dataclass
class A2AEvent:
    """An event emitted during task execution."""
    event_type: EventType
    task_id: str
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


@dataclass
class A2ATask:
    """A task submitted by an external agent."""
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    prompt: str = ""
    state: TaskState = TaskState.SUBMITTED
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    updated_at: str = ""
    result: str = ""
    error: str = ""
    events: List[A2AEvent] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def transition(self, new_state: TaskState) -> None:
        """Transition to a new state."""
        self.state = new_state
        self.updated_at = datetime.now().isoformat(timespec="seconds")

    def add_event(self, event_type: EventType, data: Dict[str, Any] = None) -> A2AEvent:
        """Add an event to the task."""
        event = A2AEvent(
            event_type=event_type,
            task_id=self.task_id,
            data=data or {},
        )
        self.events.append(event)
        return event

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict (for API responses)."""
        return {
            "task_id": self.task_id,
            "prompt": self.prompt,
            "state": self.state.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "result": self.result,
            "error": self.error,
            "event_count": len(self.events),
            "metadata": self.metadata,
        }

    @property
    def is_terminal(self) -> bool:
        """Whether the task is in a terminal state."""
        return self.state in (TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED)
