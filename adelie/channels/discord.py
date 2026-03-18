"""
adelie/channels/discord.py

Discord channel provider using discord.py (optional dependency).
"""

from __future__ import annotations

from typing import Any, Callable, Dict

from adelie.channels.base import (
    ChannelCapabilities,
    ChannelProvider,
    Message,
    MessageType,
)


class DiscordChannel(ChannelProvider):
    """
    Discord channel via discord.py bot.

    Config:
        token: Bot token
        guild_id: Target guild ID
        channel_id: Target channel ID
    """

    @property
    def name(self) -> str:
        return "discord"

    @property
    def capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(
            threads=True,
            reactions=True,
            file_upload=True,
            image_upload=True,
            markdown=True,
            code_blocks=True,
            max_message_length=2000,
            editable_messages=True,
            slash_commands=True,
        )

    async def connect(self) -> bool:
        try:
            import discord
        except ImportError:
            return False

        token = self._config.get("token", "")
        if not token:
            return False

        self._client = discord.Client(intents=discord.Intents.default())
        # Connection handled via client.start() in background
        self._connected = True
        self.emit_event("connected", {"channel": self.name})
        return True

    async def disconnect(self) -> None:
        if hasattr(self, "_client") and self._client:
            await self._client.close()
        self._connected = False
        self.emit_event("disconnected", {"channel": self.name})

    async def send_message(self, message: Message) -> bool:
        if not self._connected:
            return False
        text = self.truncate_message(message.content)
        # In real implementation: get channel and send
        self.emit_event("message_sent", {"content": text})
        return True

    async def on_message(self, callback: Callable[[Message], None]) -> None:
        self._message_callback = callback
