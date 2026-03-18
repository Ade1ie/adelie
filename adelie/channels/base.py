"""
adelie/channels/base.py

Abstract channel provider and message types.

Inspired by OpenClaw's channel-config.ts / channel-capabilities.ts pattern.
Each channel defines what it can do (capabilities) and how to send/receive.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


# ── Message Types ────────────────────────────────────────────────────────────


class MessageType(str, Enum):
    TEXT = "text"
    FILE = "file"
    IMAGE = "image"
    CODE = "code"
    SYSTEM = "system"
    REACTION = "reaction"


@dataclass
class Message:
    """A channel message."""
    content: str
    channel_id: str = ""
    sender: str = ""
    message_type: MessageType = MessageType.TEXT
    thread_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    @property
    def is_text(self) -> bool:
        return self.message_type == MessageType.TEXT

    @property
    def is_command(self) -> bool:
        return self.content.startswith("/")


# ── Capabilities ─────────────────────────────────────────────────────────────


@dataclass
class ChannelCapabilities:
    """What a channel can do (OpenClaw pattern)."""
    threads: bool = False          # Thread/reply support
    reactions: bool = False        # Emoji reactions
    file_upload: bool = False      # File attachment
    image_upload: bool = False     # Image attachment
    markdown: bool = False         # Markdown formatting
    code_blocks: bool = False      # Code block formatting
    max_message_length: int = 4096
    editable_messages: bool = False
    slash_commands: bool = False


# ── Abstract Provider ────────────────────────────────────────────────────────


class ChannelProvider(ABC):
    """
    Abstract base class for communication channels.

    Subclasses implement the specifics of each platform
    (Discord, Slack, Telegram, CLI, etc.)
    """

    def __init__(self, channel_id: str = "", config: Dict[str, Any] = None):
        self._channel_id = channel_id
        self._config = config or {}
        self._event_handlers: Dict[str, List[Callable]] = {}
        self._connected = False

    @property
    @abstractmethod
    def name(self) -> str:
        """Channel name (e.g. 'discord', 'slack', 'cli')."""
        ...

    @property
    @abstractmethod
    def capabilities(self) -> ChannelCapabilities:
        """Channel capabilities."""
        ...

    @abstractmethod
    async def connect(self) -> bool:
        """Connect to the channel. Returns True on success."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the channel."""
        ...

    @abstractmethod
    async def send_message(self, message: Message) -> bool:
        """Send a message to the channel."""
        ...

    @abstractmethod
    async def on_message(self, callback: Callable[[Message], None]) -> None:
        """Register a callback for incoming messages."""
        ...

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def channel_id(self) -> str:
        return self._channel_id

    def on_event(self, event_type: str, callback: Callable) -> None:
        """Register an event handler."""
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(callback)

    def emit_event(self, event_type: str, data: Any = None) -> None:
        """Emit an event to all registered handlers."""
        for handler in self._event_handlers.get(event_type, []):
            try:
                handler(data)
            except Exception:
                pass

    def truncate_message(self, text: str) -> str:
        """Truncate a message to the channel's max length."""
        max_len = self.capabilities.max_message_length
        if len(text) <= max_len:
            return text
        return text[: max_len - 3] + "..."
