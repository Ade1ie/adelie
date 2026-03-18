"""tests/test_channels.py — Tests for the multichannel abstraction."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Callable
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adelie.channels.base import (
    ChannelCapabilities,
    ChannelProvider,
    Message,
    MessageType,
)


# ── Test helpers ─────────────────────────────────────────────────────────────


class MockChannel(ChannelProvider):
    """Concrete channel for testing."""

    def __init__(self, channel_name="mock", **kwargs):
        super().__init__(**kwargs)
        self._name = channel_name
        self._sent: list[Message] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(
            threads=True,
            markdown=True,
            max_message_length=100,
        )

    async def connect(self) -> bool:
        self._connected = True
        return True

    async def disconnect(self) -> None:
        self._connected = False

    async def send_message(self, message: Message) -> bool:
        self._sent.append(message)
        return True

    async def on_message(self, callback: Callable[[Message], None]) -> None:
        self._callback = callback


# ── Message Tests ────────────────────────────────────────────────────────────


class TestMessage:
    def test_default_message(self):
        msg = Message(content="hello")
        assert msg.content == "hello"
        assert msg.message_type == MessageType.TEXT
        assert msg.is_text

    def test_command_detection(self):
        assert Message(content="/help").is_command
        assert not Message(content="hello").is_command

    def test_metadata(self):
        msg = Message(content="hi", metadata={"key": "val"})
        assert msg.metadata["key"] == "val"


class TestCapabilities:
    def test_defaults(self):
        caps = ChannelCapabilities()
        assert not caps.threads
        assert not caps.reactions
        assert caps.max_message_length == 4096

    def test_custom(self):
        caps = ChannelCapabilities(threads=True, reactions=True, max_message_length=2000)
        assert caps.threads
        assert caps.max_message_length == 2000


# ── Provider Tests ───────────────────────────────────────────────────────────


class TestChannelProvider:
    def test_connect_disconnect(self):
        ch = MockChannel()
        assert not ch.is_connected
        asyncio.get_event_loop().run_until_complete(ch.connect())
        assert ch.is_connected
        asyncio.get_event_loop().run_until_complete(ch.disconnect())
        assert not ch.is_connected

    def test_send_message(self):
        ch = MockChannel()
        asyncio.get_event_loop().run_until_complete(ch.connect())
        msg = Message(content="test")
        result = asyncio.get_event_loop().run_until_complete(ch.send_message(msg))
        assert result is True
        assert len(ch._sent) == 1

    def test_truncate_message(self):
        ch = MockChannel()  # max_length = 100
        short = ch.truncate_message("short")
        assert short == "short"
        long_text = "x" * 200
        truncated = ch.truncate_message(long_text)
        assert len(truncated) == 100
        assert truncated.endswith("...")

    def test_event_system(self):
        ch = MockChannel()
        events = []
        ch.on_event("test_event", lambda data: events.append(data))
        ch.emit_event("test_event", {"key": "value"})
        assert len(events) == 1
        assert events[0]["key"] == "value"

    def test_event_handler_exception(self):
        ch = MockChannel()
        ch.on_event("bad", lambda d: 1 / 0)  # Will raise
        ch.emit_event("bad", {})  # Should not propagate


# ── Router Tests ─────────────────────────────────────────────────────────────


class TestChannelRouter:
    def test_register_unregister(self):
        from adelie.channels.router import ChannelRouter
        router = ChannelRouter()
        ch = MockChannel()
        router.register(ch)
        assert "mock" in router.channel_names
        assert router.unregister("mock")
        assert "mock" not in router.channel_names

    def test_unregister_nonexistent(self):
        from adelie.channels.router import ChannelRouter
        router = ChannelRouter()
        assert not router.unregister("nope")

    def test_connect_all(self):
        from adelie.channels.router import ChannelRouter
        router = ChannelRouter()
        router.register(MockChannel(channel_name="a"))
        router.register(MockChannel(channel_name="b"))
        results = asyncio.get_event_loop().run_until_complete(router.connect_all())
        assert results == {"a": True, "b": True}
        assert router.connected_count == 2

    def test_disconnect_all(self):
        from adelie.channels.router import ChannelRouter
        router = ChannelRouter()
        ch = MockChannel()
        router.register(ch)
        asyncio.get_event_loop().run_until_complete(router.connect_all())
        asyncio.get_event_loop().run_until_complete(router.disconnect_all())
        assert router.connected_count == 0

    def test_send_to(self):
        from adelie.channels.router import ChannelRouter
        router = ChannelRouter()
        ch = MockChannel()
        router.register(ch)
        asyncio.get_event_loop().run_until_complete(ch.connect())

        msg = Message(content="hello")
        result = asyncio.get_event_loop().run_until_complete(router.send_to("mock", msg))
        assert result is True
        assert len(ch._sent) == 1

    def test_send_to_disconnected(self):
        from adelie.channels.router import ChannelRouter
        router = ChannelRouter()
        ch = MockChannel()
        router.register(ch)  # Not connected

        result = asyncio.get_event_loop().run_until_complete(
            router.send_to("mock", Message(content="hi"))
        )
        assert result is False

    def test_broadcast(self):
        from adelie.channels.router import ChannelRouter
        router = ChannelRouter()
        ch_a = MockChannel(channel_name="a")
        ch_b = MockChannel(channel_name="b")
        router.register(ch_a)
        router.register(ch_b)
        asyncio.get_event_loop().run_until_complete(router.connect_all())

        results = asyncio.get_event_loop().run_until_complete(
            router.broadcast(Message(content="broadcast!"))
        )
        assert results == {"a": True, "b": True}
        assert len(ch_a._sent) == 1
        assert len(ch_b._sent) == 1

    def test_get_channels(self):
        from adelie.channels.router import ChannelRouter
        router = ChannelRouter()
        router.register(MockChannel(channel_name="test"))
        info = router.get_channels()
        assert len(info) == 1
        assert info[0]["name"] == "test"
        assert info[0]["capabilities"]["threads"] is True


# ── Config Tests ─────────────────────────────────────────────────────────────


class TestChannelConfig:
    def test_load_no_config(self, tmp_path):
        from adelie.channels.router import load_channel_config
        result = load_channel_config(tmp_path / "nope.json")
        assert result == {}

    def test_load_valid_config(self, tmp_path):
        from adelie.channels.router import load_channel_config
        config_path = tmp_path / "channels.json"
        config_path.write_text(json.dumps({
            "channels": {
                "discord": {"token": "xxx"},
                "slack": {"bot_token": "xoxb-xxx"},
            }
        }))
        result = load_channel_config(config_path)
        assert "channels" in result
        assert "discord" in result["channels"]


# ── Discord/Slack Import Tests ───────────────────────────────────────────────


class TestDiscordChannel:
    def test_name_and_capabilities(self):
        from adelie.channels.discord import DiscordChannel
        ch = DiscordChannel()
        assert ch.name == "discord"
        assert ch.capabilities.threads
        assert ch.capabilities.max_message_length == 2000

    def test_connect_without_token(self):
        from adelie.channels.discord import DiscordChannel
        ch = DiscordChannel(config={})
        with patch.dict("sys.modules", {"discord": MagicMock()}):
            result = asyncio.get_event_loop().run_until_complete(ch.connect())
        assert result is False


class TestSlackChannel:
    def test_name_and_capabilities(self):
        from adelie.channels.slack import SlackChannel
        ch = SlackChannel()
        assert ch.name == "slack"
        assert ch.capabilities.threads
        assert ch.capabilities.max_message_length == 4000

    def test_connect_without_tokens(self):
        from adelie.channels.slack import SlackChannel
        ch = SlackChannel(config={})
        with patch.dict("sys.modules", {"slack_bolt": MagicMock(), "slack_bolt.async_app": MagicMock()}):
            result = asyncio.get_event_loop().run_until_complete(ch.connect())
        assert result is False
