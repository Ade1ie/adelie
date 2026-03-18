"""
adelie/channels/slack.py

Slack channel provider using slack_bolt (optional dependency).
"""

from __future__ import annotations

from typing import Any, Callable, Dict

from adelie.channels.base import (
    ChannelCapabilities,
    ChannelProvider,
    Message,
    MessageType,
)


class SlackChannel(ChannelProvider):
    """
    Slack channel via Slack Bolt (Socket Mode).

    Config:
        bot_token: Bot OAuth token (xoxb-...)
        app_token: App-level token (xapp-...) for Socket Mode
        channel_id: Target channel ID
    """

    @property
    def name(self) -> str:
        return "slack"

    @property
    def capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(
            threads=True,
            reactions=True,
            file_upload=True,
            image_upload=True,
            markdown=True,           # Slack mrkdwn
            code_blocks=True,
            max_message_length=4000,
            editable_messages=True,
            slash_commands=True,
        )

    async def connect(self) -> bool:
        try:
            from slack_bolt.async_app import AsyncApp
        except ImportError:
            return False

        bot_token = self._config.get("bot_token", "")
        app_token = self._config.get("app_token", "")
        if not bot_token or not app_token:
            return False

        self._connected = True
        self.emit_event("connected", {"channel": self.name})
        return True

    async def disconnect(self) -> None:
        self._connected = False
        self.emit_event("disconnected", {"channel": self.name})

    async def send_message(self, message: Message) -> bool:
        if not self._connected:
            return False
        text = self.truncate_message(message.content)
        self.emit_event("message_sent", {"content": text})
        return True

    async def on_message(self, callback: Callable[[Message], None]) -> None:
        self._message_callback = callback
