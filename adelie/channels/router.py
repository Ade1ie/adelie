"""
adelie/channels/router.py

Channel router — manages multiple channels and routes messages.
Inspired by OpenClaw's multichannel routing + session management.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from adelie.channels.base import ChannelProvider, Message

logger = logging.getLogger("adelie.channels")


@dataclass
class ChannelSession:
    """A session bound to a specific channel + user."""
    session_id: str
    channel_name: str
    channel_id: str
    user_id: str
    created_at: str = ""
    message_count: int = 0


class ChannelRouter:
    """
    Routes messages between multiple channel providers.

    Usage:
        router = ChannelRouter()
        router.register(discord_channel)
        router.register(slack_channel)
        await router.connect_all()
        await router.broadcast(Message(content="Hello from Adelie!"))
    """

    def __init__(self):
        self._channels: Dict[str, ChannelProvider] = {}
        self._sessions: Dict[str, ChannelSession] = {}
        self._global_handlers: List[Callable[[Message, str], None]] = []

    def register(self, channel: ChannelProvider) -> None:
        """Register a channel provider."""
        self._channels[channel.name] = channel
        logger.info(f"Registered channel: {channel.name}")

    def unregister(self, name: str) -> bool:
        """Unregister a channel provider."""
        return self._channels.pop(name, None) is not None

    async def connect_all(self) -> Dict[str, bool]:
        """Connect all registered channels."""
        results = {}
        for name, channel in self._channels.items():
            try:
                results[name] = await channel.connect()
            except Exception as e:
                logger.error(f"Failed to connect {name}: {e}")
                results[name] = False
        return results

    async def disconnect_all(self) -> None:
        """Disconnect all channels."""
        for channel in self._channels.values():
            try:
                await channel.disconnect()
            except Exception:
                pass

    async def send_to(self, channel_name: str, message: Message) -> bool:
        """Send message to a specific channel."""
        channel = self._channels.get(channel_name)
        if not channel or not channel.is_connected:
            return False
        return await channel.send_message(message)

    async def broadcast(self, message: Message) -> Dict[str, bool]:
        """Broadcast message to all connected channels."""
        results = {}
        for name, channel in self._channels.items():
            if channel.is_connected:
                try:
                    results[name] = await channel.send_message(message)
                except Exception:
                    results[name] = False
        return results

    def on_message(self, callback: Callable[[Message, str], None]) -> None:
        """Register a global handler for messages from any channel.
        Callback receives (message, channel_name)."""
        self._global_handlers.append(callback)

    # ── Channel Info ─────────────────────────────────────────────────────

    def get_channels(self) -> List[Dict[str, Any]]:
        """List registered channels and their status."""
        return [
            {
                "name": name,
                "connected": channel.is_connected,
                "capabilities": {
                    "threads": channel.capabilities.threads,
                    "reactions": channel.capabilities.reactions,
                    "file_upload": channel.capabilities.file_upload,
                    "markdown": channel.capabilities.markdown,
                    "max_length": channel.capabilities.max_message_length,
                },
            }
            for name, channel in self._channels.items()
        ]

    @property
    def connected_count(self) -> int:
        return sum(1 for c in self._channels.values() if c.is_connected)

    @property
    def channel_names(self) -> List[str]:
        return list(self._channels.keys())


def load_channel_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Load channel configuration from .adelie/channels.json.

    Example:
    {
        "channels": {
            "discord": {"token": "...", "channel_id": "..."},
            "slack": {"bot_token": "xoxb-...", "app_token": "xapp-..."}
        }
    }
    """
    if config_path is None:
        from adelie.config import PROJECT_ROOT
        config_path = PROJECT_ROOT / ".adelie" / "channels.json"

    if not config_path.exists():
        return {}

    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
