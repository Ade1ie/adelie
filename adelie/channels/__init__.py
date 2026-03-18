"""
adelie/channels/__init__.py

Multichannel abstraction for Adelie.

Provides a unified interface for communication channels
(CLI, Discord, Slack, Telegram, Gateway API).
"""

from adelie.channels.base import (
    ChannelProvider,
    ChannelCapabilities,
    Message,
    MessageType,
)

__all__ = [
    "ChannelProvider",
    "ChannelCapabilities",
    "Message",
    "MessageType",
]
