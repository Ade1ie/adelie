"""tests/test_mcp_client.py — Tests for MCP client, manager, and registry integration."""
from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch, PropertyMock

import pytest


# ── McpClient Tests ──────────────────────────────────────────────────────────


class TestMcpToolInfo:
    def test_qualified_name(self):
        from adelie.mcp_client import McpToolInfo
        tool = McpToolInfo(name="read_file", server_name="filesystem")
        assert tool.qualified_name == "mcp_filesystem_read_file"

    def test_qualified_name_with_hyphens(self):
        from adelie.mcp_client import McpToolInfo
        tool = McpToolInfo(name="search-code", server_name="my-server")
        assert tool.qualified_name == "mcp_my_server_search_code"

    def test_qualified_name_with_dots(self):
        from adelie.mcp_client import McpToolInfo
        tool = McpToolInfo(name="git.status", server_name="dev.tools")
        assert tool.qualified_name == "mcp_dev_tools_git_status"


class TestMcpServerConfig:
    def test_default_values(self):
        from adelie.mcp_client import McpServerConfig
        config = McpServerConfig()
        assert config.command is None
        assert config.args == []
        assert config.timeout == 600
        assert config.enabled is True

    def test_custom_values(self):
        from adelie.mcp_client import McpServerConfig
        config = McpServerConfig(
            command="npx",
            args=["-y", "server"],
            env={"KEY": "val"},
            timeout=30,
        )
        assert config.command == "npx"
        assert len(config.args) == 2
        assert config.env == {"KEY": "val"}


class TestMcpClientBasic:
    def test_initial_status(self):
        from adelie.mcp_client import McpClient, McpServerConfig, McpServerStatus
        client = McpClient("test", McpServerConfig())
        assert client.status == McpServerStatus.DISCONNECTED

    def test_connect_fails_without_command(self):
        from adelie.mcp_client import McpClient, McpServerConfig, McpServerStatus
        client = McpClient("test", McpServerConfig())
        assert not client.connect()
        assert client.status == McpServerStatus.ERROR

    def test_disconnect_from_disconnected(self):
        from adelie.mcp_client import McpClient, McpServerConfig, McpServerStatus
        client = McpClient("test", McpServerConfig())
        client.disconnect()  # should not raise
        assert client.status == McpServerStatus.DISCONNECTED

    def test_discover_tools_when_not_connected(self):
        from adelie.mcp_client import McpClient, McpServerConfig
        client = McpClient("test", McpServerConfig())
        tools = client.discover_tools()
        assert tools == []

    def test_call_tool_when_not_connected(self):
        from adelie.mcp_client import McpClient, McpServerConfig
        client = McpClient("test", McpServerConfig())
        result = client.call_tool("some_tool", {})
        assert "error" in result

    def test_get_tools_empty_initially(self):
        from adelie.mcp_client import McpClient, McpServerConfig
        client = McpClient("test", McpServerConfig())
        assert client.get_tools() == []


class TestMcpClientProtocol:
    """Test the JSON-RPC request/response handling."""

    def test_next_id_increments(self):
        from adelie.mcp_client import McpClient, McpServerConfig
        client = McpClient("test", McpServerConfig())
        id1 = client._next_id()
        id2 = client._next_id()
        assert id2 == id1 + 1

    def test_extract_text_from_response(self):
        from adelie.mcp_client import McpClient
        resp = {
            "content": [
                {"type": "text", "text": "Hello"},
                {"type": "text", "text": "World"},
            ]
        }
        assert McpClient._extract_text(resp) == "Hello\nWorld"

    def test_extract_text_empty(self):
        from adelie.mcp_client import McpClient
        resp = {"content": []}
        result = McpClient._extract_text(resp)
        assert isinstance(result, str)


# ── McpManager Tests ─────────────────────────────────────────────────────────


class TestMcpManagerConfig:
    def test_load_config_no_file(self, tmp_path):
        from adelie.mcp_manager import McpManager
        manager = McpManager(config_path=tmp_path / "nofile.json")
        count = manager.load_config()
        assert count == 0

    def test_load_config_valid(self, tmp_path):
        from adelie.mcp_manager import McpManager
        config_file = tmp_path / "mcp.json"
        config_file.write_text(json.dumps({
            "mcpServers": {
                "test-server": {
                    "command": "echo",
                    "args": ["hello"],
                    "env": {"FOO": "bar"},
                },
                "disabled-server": {
                    "command": "echo",
                    "enabled": False,
                },
            }
        }), encoding="utf-8")

        manager = McpManager(config_path=config_file)
        count = manager.load_config()
        assert count == 2

    def test_load_config_invalid_json(self, tmp_path):
        from adelie.mcp_manager import McpManager
        config_file = tmp_path / "mcp.json"
        config_file.write_text("not json", encoding="utf-8")
        manager = McpManager(config_path=config_file)
        count = manager.load_config()
        assert count == 0

    def test_load_config_empty_servers(self, tmp_path):
        from adelie.mcp_manager import McpManager
        config_file = tmp_path / "mcp.json"
        config_file.write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")
        manager = McpManager(config_path=config_file)
        count = manager.load_config()
        assert count == 0


class TestMcpManagerLifecycle:
    def test_has_servers_false_initially(self, tmp_path):
        from adelie.mcp_manager import McpManager
        manager = McpManager(config_path=tmp_path / "nofile.json")
        assert not manager.has_servers

    def test_connected_count_zero_initially(self, tmp_path):
        from adelie.mcp_manager import McpManager
        manager = McpManager(config_path=tmp_path / "nofile.json")
        assert manager.connected_count == 0

    def test_stop_all_no_error(self, tmp_path):
        from adelie.mcp_manager import McpManager
        manager = McpManager(config_path=tmp_path / "nofile.json")
        manager.stop_all()  # should not raise

    def test_call_tool_unknown_server(self, tmp_path):
        from adelie.mcp_manager import McpManager
        manager = McpManager(config_path=tmp_path / "nofile.json")
        result = manager.call_tool("unknown", "tool", {})
        assert "error" in result

    def test_get_all_tools_empty(self, tmp_path):
        from adelie.mcp_manager import McpManager
        manager = McpManager(config_path=tmp_path / "nofile.json")
        assert manager.get_all_tools() == []

    def test_get_status_empty(self, tmp_path):
        from adelie.mcp_manager import McpManager
        manager = McpManager(config_path=tmp_path / "nofile.json")
        assert manager.get_status() == {}


class TestMcpManagerQualifiedName:
    def test_parse_valid_name(self):
        from adelie.mcp_manager import McpManager
        server, tool = McpManager._parse_qualified_name("mcp_myserver_mytool")
        assert server == "myserver"
        assert tool == "mytool"

    def test_parse_no_prefix(self):
        from adelie.mcp_manager import McpManager
        server, tool = McpManager._parse_qualified_name("plain_name")
        assert server is None
        assert tool is None

    def test_parse_underscore_in_tool(self):
        from adelie.mcp_manager import McpManager
        server, tool = McpManager._parse_qualified_name("mcp_server_read_file")
        assert server == "server"
        assert tool == "read_file"

    def test_call_qualified_tool_invalid_name(self, tmp_path):
        from adelie.mcp_manager import McpManager
        manager = McpManager(config_path=tmp_path / "nofile.json")
        result = manager.call_qualified_tool("bad_name", {})
        assert "error" in result


# ── ToolRegistry MCP Integration Tests ───────────────────────────────────────


class TestToolRegistryMcpIntegration:
    def test_mcp_category_exists(self):
        from adelie.tool_registry import ToolCategory
        assert ToolCategory.MCP == "mcp"

    def test_tool_has_mcp_fields(self):
        from adelie.tool_registry import Tool, ToolCategory
        tool = Tool(
            name="mcp_test_tool",
            description="Test",
            category=ToolCategory.MCP,
            mcp_server="test",
            mcp_tool_name="tool",
        )
        assert tool.mcp_server == "test"
        assert tool.mcp_tool_name == "tool"

    def test_register_mcp_tools(self):
        from adelie.tool_registry import ToolRegistry, ToolCategory
        from adelie.mcp_client import McpToolInfo

        mock_manager = MagicMock()
        mock_manager.get_all_tools.return_value = [
            McpToolInfo(
                name="read_file",
                server_name="filesystem",
                description="Read a file",
                input_schema={"properties": {"path": {"type": "string"}}},
            ),
            McpToolInfo(
                name="list_repos",
                server_name="github",
                description="List repositories",
                input_schema={"properties": {"org": {"type": "string"}}},
            ),
        ]

        registry = ToolRegistry()
        count = registry.register_mcp_tools(mock_manager)
        assert count == 2

        # Check tools are registered with correct names
        tool1 = registry.get_tool("mcp_filesystem_read_file")
        assert tool1 is not None
        assert tool1.category == ToolCategory.MCP
        assert tool1.mcp_server == "filesystem"
        assert tool1.mcp_tool_name == "read_file"
        assert tool1.agents == []  # available to all agents

        tool2 = registry.get_tool("mcp_github_list_repos")
        assert tool2 is not None
        assert tool2.mcp_server == "github"

    def test_remove_mcp_tools(self):
        from adelie.tool_registry import ToolRegistry, Tool, ToolCategory

        registry = ToolRegistry()
        registry.register_builtins()
        registry.register(Tool(
            name="mcp_test_tool",
            description="MCP tool",
            category=ToolCategory.MCP,
            mcp_server="test",
        ))

        builtin_count = len(registry.get_all()) - 1  # minus the MCP tool
        removed = registry.remove_mcp_tools()
        assert removed == 1
        assert len(registry.get_all()) == builtin_count
        assert registry.get_tool("mcp_test_tool") is None

    def test_get_mcp_tools(self):
        from adelie.tool_registry import ToolRegistry, Tool, ToolCategory

        registry = ToolRegistry()
        registry.register_builtins()
        registry.register(Tool(
            name="mcp_fs_read",
            description="Read",
            category=ToolCategory.MCP,
        ))
        registry.register(Tool(
            name="mcp_gh_list",
            description="List",
            category=ToolCategory.MCP,
        ))

        mcp_tools = registry.get_mcp_tools()
        assert len(mcp_tools) == 2
        assert all(t.category == ToolCategory.MCP for t in mcp_tools)

    def test_mcp_tools_available_to_all_agents(self):
        from adelie.tool_registry import ToolRegistry, Tool, ToolCategory

        registry = ToolRegistry()
        registry.register_builtins()
        registry.register(Tool(
            name="mcp_test_tool",
            description="MCP tool for all",
            category=ToolCategory.MCP,
            agents=[],  # empty = available to all
        ))

        for agent in ["expert", "coder", "runner", "writer", "reviewer", "tester"]:
            tools = registry.get_tools_for_agent(agent)
            names = [t.name for t in tools]
            assert "mcp_test_tool" in names, f"MCP tool not available to {agent}"

    def test_mcp_tools_in_prompt(self):
        from adelie.tool_registry import ToolRegistry, Tool, ToolCategory

        registry = ToolRegistry()
        registry.register(Tool(
            name="mcp_fs_read",
            description="Read a file from filesystem",
            category=ToolCategory.MCP,
            usage="read_file(path)",
        ))

        prompt = registry.get_tools_prompt()
        assert "Mcp Tools" in prompt
        assert "mcp_fs_read" in prompt
        assert "Read a file from filesystem" in prompt
