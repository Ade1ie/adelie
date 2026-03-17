"""tests/test_tool_registry.py — Tests for Tool Registry module."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest


# ── Registration Tests ───────────────────────────────────────────────────────


class TestToolRegistration:
    def test_register_builtin_tools(self):
        from adelie.tool_registry import ToolRegistry
        registry = ToolRegistry()
        registry.register_builtins()
        tools = registry.get_all()
        assert len(tools) >= 5
        names = [t.name for t in tools]
        assert "shell_exec" in names
        assert "file_read" in names
        assert "file_write" in names
        assert "grep_search" in names
        assert "web_search" in names

    def test_register_custom_tool(self):
        from adelie.tool_registry import ToolRegistry, Tool, ToolCategory
        registry = ToolRegistry()
        tool = Tool(
            name="custom_lint",
            description="Run custom linter",
            category=ToolCategory.BUILD,
            usage="custom_lint(path)",
            builtin=False,
        )
        registry.register(tool)
        assert registry.get_tool("custom_lint") is not None
        assert registry.get_tool("custom_lint").builtin is False

    def test_unregister_tool(self):
        from adelie.tool_registry import ToolRegistry, Tool, ToolCategory
        registry = ToolRegistry()
        registry.register(Tool(name="tmp_tool", description="temp", category=ToolCategory.SHELL))
        assert registry.unregister("tmp_tool")
        assert registry.get_tool("tmp_tool") is None

    def test_unregister_nonexistent_returns_false(self):
        from adelie.tool_registry import ToolRegistry
        registry = ToolRegistry()
        assert not registry.unregister("nonexistent")


# ── Enable / Disable Tests ───────────────────────────────────────────────────


class TestEnableDisable:
    def test_disable_tool(self):
        from adelie.tool_registry import ToolRegistry
        registry = ToolRegistry()
        registry.register_builtins()
        assert registry.disable("shell_exec")
        tool = registry.get_tool("shell_exec")
        assert not tool.enabled

    def test_enable_tool(self):
        from adelie.tool_registry import ToolRegistry
        registry = ToolRegistry()
        registry.register_builtins()
        registry.disable("shell_exec")
        assert registry.enable("shell_exec")
        tool = registry.get_tool("shell_exec")
        assert tool.enabled

    def test_disable_nonexistent_returns_false(self):
        from adelie.tool_registry import ToolRegistry
        registry = ToolRegistry()
        assert not registry.disable("nonexistent")

    def test_get_enabled_excludes_disabled(self):
        from adelie.tool_registry import ToolRegistry
        registry = ToolRegistry()
        registry.register_builtins()
        registry.disable("shell_exec")
        enabled = registry.get_enabled()
        names = [t.name for t in enabled]
        assert "shell_exec" not in names
        assert "file_read" in names


# ── Agent Filtering Tests ────────────────────────────────────────────────────


class TestAgentFiltering:
    def test_runner_gets_runner_tools(self):
        from adelie.tool_registry import ToolRegistry
        registry = ToolRegistry()
        registry.register_builtins()
        runner_tools = registry.get_tools_for_agent("runner")
        names = [t.name for t in runner_tools]
        assert "shell_exec" in names
        # file_read is for coder/expert/reviewer/scanner, not runner
        assert "file_read" not in names

    def test_expert_gets_search_tools(self):
        from adelie.tool_registry import ToolRegistry
        registry = ToolRegistry()
        registry.register_builtins()
        expert_tools = registry.get_tools_for_agent("expert")
        names = [t.name for t in expert_tools]
        assert "grep_search" in names
        assert "web_search" in names
        assert "glob_find" in names

    def test_case_insensitive_agent_match(self):
        from adelie.tool_registry import ToolRegistry
        registry = ToolRegistry()
        registry.register_builtins()
        tools_lower = registry.get_tools_for_agent("runner")
        tools_upper = registry.get_tools_for_agent("Runner")
        assert len(tools_lower) == len(tools_upper)


# ── Prompt Generation Tests ──────────────────────────────────────────────────


class TestPromptGeneration:
    def test_get_tools_prompt_not_empty(self):
        from adelie.tool_registry import ToolRegistry
        registry = ToolRegistry()
        registry.register_builtins()
        prompt = registry.get_tools_prompt("expert")
        assert "Available Tools" in prompt
        assert "grep_search" in prompt

    def test_empty_registry_returns_empty_prompt(self):
        from adelie.tool_registry import ToolRegistry
        registry = ToolRegistry()
        prompt = registry.get_tools_prompt("expert")
        assert prompt == ""

    def test_prompt_groups_by_category(self):
        from adelie.tool_registry import ToolRegistry
        registry = ToolRegistry()
        registry.register_builtins()
        prompt = registry.get_tools_prompt()
        assert "Shell Tools" in prompt or "File Tools" in prompt


# ── Persistence Tests ────────────────────────────────────────────────────────


class TestPersistence:
    def test_save_and_load_state(self, tmp_path):
        from adelie.tool_registry import ToolRegistry

        with patch("adelie.tool_registry._find_tools_state_path", return_value=tmp_path / "state.json"):
            registry = ToolRegistry()
            registry.register_builtins()
            registry.disable("shell_exec")
            registry.save_state()

            # Load into a new registry
            registry2 = ToolRegistry()
            registry2.register_builtins()
            registry2.load_state()
            assert not registry2.get_tool("shell_exec").enabled
            assert registry2.get_tool("file_read").enabled

    def test_load_state_no_file(self, tmp_path):
        from adelie.tool_registry import ToolRegistry

        with patch("adelie.tool_registry._find_tools_state_path", return_value=tmp_path / "noexist.json"):
            registry = ToolRegistry()
            registry.register_builtins()
            registry.load_state()  # Should not raise
            assert registry.get_tool("shell_exec").enabled

    def test_load_state_corrupt_file(self, tmp_path):
        from adelie.tool_registry import ToolRegistry

        corrupt_file = tmp_path / "corrupt.json"
        corrupt_file.write_text("not json", encoding="utf-8")
        with patch("adelie.tool_registry._find_tools_state_path", return_value=corrupt_file):
            registry = ToolRegistry()
            registry.register_builtins()
            registry.load_state()  # Should not raise
            assert registry.get_tool("shell_exec").enabled


# ── User-Defined Tools Tests ────────────────────────────────────────────────


class TestUserTools:
    def test_load_user_tools_from_directory(self, tmp_path):
        from adelie.tool_registry import ToolRegistry

        # Create a user tool
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        (tools_dir / "my_tool.py").write_text(
            'from adelie.tool_registry import Tool, ToolCategory\n'
            'def register(registry):\n'
            '    registry.register(Tool(name="my_tool", '
            'description="My custom tool", category=ToolCategory.CUSTOM, '
            'builtin=False))\n',
            encoding="utf-8",
        )

        with patch("adelie.tool_registry._find_tools_dir", return_value=tools_dir):
            registry = ToolRegistry()
            loaded = registry.load_user_tools()
            assert loaded == 1
            assert registry.get_tool("my_tool") is not None
            assert not registry.get_tool("my_tool").builtin

    def test_load_skips_underscore_files(self, tmp_path):
        from adelie.tool_registry import ToolRegistry

        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        (tools_dir / "_helper.py").write_text("def register(r): pass\n", encoding="utf-8")

        with patch("adelie.tool_registry._find_tools_dir", return_value=tools_dir):
            registry = ToolRegistry()
            loaded = registry.load_user_tools()
            assert loaded == 0

    def test_load_no_tools_dir(self):
        from adelie.tool_registry import ToolRegistry

        with patch("adelie.tool_registry._find_tools_dir", return_value=None):
            registry = ToolRegistry()
            loaded = registry.load_user_tools()
            assert loaded == 0
