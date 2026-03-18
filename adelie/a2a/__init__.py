"""
adelie/a2a/__init__.py

Agent-to-Agent (A2A) protocol for Adelie.
Allows external agents to create tasks, query status,
and receive real-time events.
"""

from adelie.a2a.types import (
    TaskState,
    A2ATask,
    A2AEvent,
    EventType,
)

__all__ = ["TaskState", "A2ATask", "A2AEvent", "EventType"]
