"""
adelie/tool_registry.py

Dynamic tool registration system — manages available tools for AI agents.

Built-in tools: shell_exec, file_read, file_write, grep_search, glob_find, web_search
User-defined tools: loaded from .adelie/tools/*.py

Inspired by gemini-cli's Tool Registry system.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from adelie.config import PROJECT_ROOT


class ToolCategory(str, Enum):
    SHELL = "shell"
    FILE = "file"
    SEARCH = "search"
    BUILD = "build"
    CUSTOM = "custom"
    MCP = "mcp"


@dataclass
class Tool:
    """A registered tool that agents can use."""
    name: str
    description: str
    category: ToolCategory
    usage: str = ""             # usage hint for agents (e.g. "grep_search(pattern, path)")
    agents: list[str] = field(default_factory=list)  # empty = available to all
    enabled: bool = True
    builtin: bool = True        # False for user-defined tools
    handler: Optional[Callable[..., Any]] = field(default=None, repr=False)
    mcp_server: Optional[str] = None   # MCP server name (for MCP tools)
    mcp_tool_name: Optional[str] = None  # Original tool name on MCP server


class ToolRegistry:
    """
    Central registry for all tools available to Adelie agents.

    Use:
        registry = ToolRegistry()
        registry.register_builtins()
        registry.load_user_tools()
        tools = registry.get_tools_for_agent("runner")
    """

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    # ── Registration ─────────────────────────────────────────────────────────

    def register(self, tool: Tool) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> bool:
        """Unregister a tool by name."""
        return self._tools.pop(name, None) is not None

    def enable(self, name: str) -> bool:
        """Enable a tool."""
        if name in self._tools:
            self._tools[name].enabled = True
            return True
        return False

    def disable(self, name: str) -> bool:
        """Disable a tool."""
        if name in self._tools:
            self._tools[name].enabled = False
            return True
        return False

    # ── Queries ───────────────────────────────────────────────────────────────

    def get_all(self) -> list[Tool]:
        """Get all registered tools."""
        return list(self._tools.values())

    def get_enabled(self) -> list[Tool]:
        """Get all enabled tools."""
        return [t for t in self._tools.values() if t.enabled]

    def get_tool(self, name: str) -> Optional[Tool]:
        """Get a tool by name."""
        return self._tools.get(name)

    def get_tools_for_agent(self, agent_name: str) -> list[Tool]:
        """
        Get all enabled tools available to a specific agent.

        Args:
            agent_name: Agent identifier (e.g. "runner", "expert", "coder")

        Returns:
            List of enabled Tools applicable to this agent.
        """
        agent_lower = agent_name.lower()
        return [
            t for t in self._tools.values()
            if t.enabled
            and (not t.agents or agent_lower in [a.lower() for a in t.agents])
        ]

    # ── Prompt Generation ────────────────────────────────────────────────────

    def get_tools_prompt(self, agent_name: str = "") -> str:
        """
        Generate a prompt section listing available tools.

        Args:
            agent_name: If provided, filter tools for this agent.

        Returns:
            Formatted tools prompt text, or empty string if no tools.
        """
        tools = self.get_tools_for_agent(agent_name) if agent_name else self.get_enabled()
        if not tools:
            return ""

        parts = ["\n## Available Tools"]
        by_category: dict[str, list[Tool]] = {}
        for tool in tools:
            cat = tool.category.value
            by_category.setdefault(cat, []).append(tool)

        for cat, cat_tools in sorted(by_category.items()):
            parts.append(f"\n### {cat.title()} Tools")
            for tool in cat_tools:
                parts.append(f"- **{tool.name}**: {tool.description}")
                if tool.usage:
                    parts.append(f"  Usage: `{tool.usage}`")

        return "\n".join(parts) + "\n"

    # ── Built-in Tools ───────────────────────────────────────────────────────

    def register_builtins(self) -> None:
        """Register all built-in tools."""
        builtins = [
            Tool(
                name="shell_exec",
                description="Execute a shell command in the project directory",
                category=ToolCategory.SHELL,
                usage="shell_exec(command, cwd='.')",
                agents=["runner"],
            ),
            Tool(
                name="file_read",
                description="Read the content of a file",
                category=ToolCategory.FILE,
                usage="file_read(path)",
                agents=["coder", "expert", "reviewer", "scanner"],
            ),
            Tool(
                name="file_write",
                description="Write content to a file (create or overwrite)",
                category=ToolCategory.FILE,
                usage="file_write(path, content)",
                agents=["coder", "writer"],
            ),
            Tool(
                name="file_patch",
                description="Apply a patch/diff to an existing file",
                category=ToolCategory.FILE,
                usage="file_patch(path, search, replace)",
                agents=["coder"],
            ),
            Tool(
                name="grep_search",
                description="Search for a pattern in files using regex",
                category=ToolCategory.SEARCH,
                usage="grep_search(pattern, path='.', include='*.py')",
                agents=["expert", "coder", "reviewer", "scanner"],
            ),
            Tool(
                name="glob_find",
                description="Find files matching a glob pattern",
                category=ToolCategory.SEARCH,
                usage="glob_find(pattern, path='.')",
                agents=["expert", "coder", "scanner"],
            ),
            Tool(
                name="web_search",
                description="Search the web for information (Gemini grounding or browser fallback)",
                category=ToolCategory.SEARCH,
                usage="web_search(query, context='')",
                agents=["research", "expert"],
            ),
            Tool(
                name="npm_run",
                description="Run an npm/yarn script",
                category=ToolCategory.BUILD,
                usage="npm_run(script_name, args='')",
                agents=["runner", "tester"],
            ),
            Tool(
                name="pip_install",
                description="Install Python packages",
                category=ToolCategory.BUILD,
                usage="pip_install(packages)",
                agents=["runner"],
            ),
        ]
        for tool in builtins:
            self.register(tool)

    # ── MCP Tools ────────────────────────────────────────────────────────────

    def register_mcp_tools(self, mcp_manager) -> int:
        """
        Register tools discovered from MCP servers.

        Args:
            mcp_manager: McpManager instance with connected servers.

        Returns:
            Number of MCP tools registered.
        """
        tools = mcp_manager.get_all_tools()
        count = 0
        for mcp_tool in tools:
            tool = Tool(
                name=mcp_tool.qualified_name,
                description=mcp_tool.description,
                category=ToolCategory.MCP,
                usage=f"{mcp_tool.name}({', '.join(mcp_tool.input_schema.get('properties', {}).keys())})",
                agents=[],  # available to all agents
                enabled=True,
                builtin=False,
                mcp_server=mcp_tool.server_name,
                mcp_tool_name=mcp_tool.name,
            )
            self.register(tool)
            count += 1
        return count

    def remove_mcp_tools(self) -> int:
        """Remove all MCP tools from the registry."""
        mcp_names = [n for n, t in self._tools.items() if t.category == ToolCategory.MCP]
        for name in mcp_names:
            del self._tools[name]
        return len(mcp_names)

    def get_mcp_tools(self) -> list[Tool]:
        """Get all registered MCP tools."""
        return [t for t in self._tools.values() if t.category == ToolCategory.MCP]

    # ── User-Defined Tools ───────────────────────────────────────────────────

    def load_user_tools(self) -> int:
        """
        Load user-defined tools from .adelie/tools/*.py.

        Each file should define a `register(registry)` function
        that calls registry.register(Tool(...)).

        Returns:
            Number of user tools loaded.
        """
        tools_dir = _find_tools_dir()
        if not tools_dir or not tools_dir.exists():
            return 0

        loaded = 0
        for py_file in sorted(tools_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            try:
                spec = importlib.util.spec_from_file_location(
                    f"adelie_user_tool_{py_file.stem}", str(py_file)
                )
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    if hasattr(module, "register"):
                        module.register(self)
                        loaded += 1
            except Exception:
                continue

        return loaded

    # ── Persistence ──────────────────────────────────────────────────────────

    def save_state(self) -> None:
        """Save enabled/disabled state to .adelie/tools_state.json."""
        import json
        state_file = _find_tools_state_path()
        if not state_file:
            return
        state = {name: tool.enabled for name, tool in self._tools.items()}
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def load_state(self) -> None:
        """Restore enabled/disabled state from .adelie/tools_state.json."""
        import json
        state_file = _find_tools_state_path()
        if not state_file or not state_file.exists():
            return
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
            for name, enabled in state.items():
                if name in self._tools:
                    self._tools[name].enabled = enabled
        except Exception:
            pass


# ── Module-level helpers ─────────────────────────────────────────────────────


def _find_adelie_dir() -> Optional[Path]:
    """Find the .adelie directory from PROJECT_ROOT upwards."""
    current = PROJECT_ROOT
    for _ in range(5):
        adelie_dir = current / ".adelie"
        if adelie_dir.is_dir():
            return adelie_dir
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def _find_tools_dir() -> Optional[Path]:
    """Find the .adelie/tools/ directory."""
    adelie_dir = _find_adelie_dir()
    if adelie_dir:
        return adelie_dir / "tools"
    return None


def _find_tools_state_path() -> Optional[Path]:
    """Find the path to .adelie/tools_state.json."""
    adelie_dir = _find_adelie_dir()
    if adelie_dir:
        return adelie_dir / "tools_state.json"
    return None


# ── Singleton ────────────────────────────────────────────────────────────────

_global_registry: Optional[ToolRegistry] = None


def get_registry() -> ToolRegistry:
    """Get the global tool registry (lazy-initialized)."""
    global _global_registry
    if _global_registry is None:
        _global_registry = ToolRegistry()
        _global_registry.register_builtins()
        _global_registry.load_user_tools()
        _global_registry.load_state()
    return _global_registry
