"""
adelie/mcp_manager.py

Manages the lifecycle of multiple MCP server connections.

Loads configuration from .adelie/mcp.json, starts/stops servers,
and provides a unified interface for tool discovery and invocation.

Inspired by gemini-cli's McpClientManager.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from adelie.config import ADELIE_ROOT
from adelie.mcp_client import McpClient, McpServerConfig, McpServerStatus, McpToolInfo

logger = logging.getLogger("adelie.mcp")


class McpManager:
    """
    Manages multiple MCP server connections.

    Loads configuration from .adelie/mcp.json and provides
    a unified interface for the orchestrator and tool registry.

    Usage:
        manager = McpManager()
        manager.start_all()          # connect to all configured servers
        tools = manager.get_all_tools()  # get discovered tools
        result = manager.call_tool("server_name", "tool_name", {...})
        manager.stop_all()           # cleanup
    """

    def __init__(self, config_path: Optional[Path] = None):
        self._clients: Dict[str, McpClient] = {}
        self._config_path = config_path or (ADELIE_ROOT / "mcp.json")
        self._configs: Dict[str, McpServerConfig] = {}

    # ── Configuration ────────────────────────────────────────────────────

    def load_config(self) -> int:
        """
        Load MCP server configurations from .adelie/mcp.json.

        Returns:
            Number of server configs loaded.
        """
        if not self._config_path.exists():
            logger.info(f"No MCP config found at {self._config_path}")
            return 0

        try:
            raw = json.loads(self._config_path.read_text(encoding="utf-8"))
            servers = raw.get("mcpServers", {})

            self._configs.clear()
            for name, cfg in servers.items():
                self._configs[name] = McpServerConfig(
                    command=cfg.get("command"),
                    args=cfg.get("args", []),
                    url=cfg.get("url"),
                    env=cfg.get("env", {}),
                    timeout=cfg.get("timeout", 600),
                    enabled=cfg.get("enabled", True),
                )

            logger.info(f"Loaded {len(self._configs)} MCP server config(s)")
            return len(self._configs)

        except Exception as e:
            logger.error(f"Failed to load MCP config: {e}")
            return 0

    # ── Lifecycle ────────────────────────────────────────────────────────

    def start_all(self) -> Dict[str, bool]:
        """
        Connect to all configured and enabled MCP servers, then discover tools.

        Returns:
            Dict mapping server name to connection success status.
        """
        if not self._configs:
            self.load_config()

        results = {}
        for name, config in self._configs.items():
            if not config.enabled:
                logger.info(f"MCP '{name}': disabled, skipping")
                results[name] = False
                continue

            results[name] = self._start_server(name, config)

        connected = sum(1 for v in results.values() if v)
        logger.info(f"MCP servers: {connected}/{len(results)} connected")
        return results

    def _start_server(self, name: str, config: McpServerConfig) -> bool:
        """Connect to a single MCP server and discover its tools."""
        # Disconnect existing client if any
        if name in self._clients:
            self._clients[name].disconnect()

        client = McpClient(name, config)
        self._clients[name] = client

        if not client.connect():
            return False

        client.discover_tools()
        return True

    def stop_all(self) -> None:
        """Disconnect all MCP servers."""
        for name, client in self._clients.items():
            try:
                client.disconnect()
            except Exception as e:
                logger.error(f"Error stopping MCP '{name}': {e}")

        self._clients.clear()
        logger.info("All MCP servers stopped")

    def restart_server(self, name: str) -> bool:
        """Restart a single MCP server by name."""
        config = self._configs.get(name)
        if not config:
            logger.error(f"No MCP config for server '{name}'")
            return False
        return self._start_server(name, config)

    # ── Tool Access ──────────────────────────────────────────────────────

    def get_all_tools(self) -> List[McpToolInfo]:
        """Get all discovered tools from all connected servers."""
        tools = []
        for client in self._clients.values():
            if client.status == McpServerStatus.CONNECTED:
                tools.extend(client.get_tools())
        return tools

    def get_server_tools(self, server_name: str) -> List[McpToolInfo]:
        """Get tools from a specific server."""
        client = self._clients.get(server_name)
        if client and client.status == McpServerStatus.CONNECTED:
            return client.get_tools()
        return []

    def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Call a tool on a specific MCP server.

        Args:
            server_name: Name of the MCP server.
            tool_name: Original tool name on the server.
            arguments: Tool arguments.

        Returns:
            Tool result dict.
        """
        client = self._clients.get(server_name)
        if not client:
            return {"error": f"MCP server '{server_name}' not found"}

        return client.call_tool(tool_name, arguments)

    def call_qualified_tool(
        self,
        qualified_name: str,
        arguments: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Call a tool using its qualified name (mcp_{server}_{tool}).

        Parses the qualified name to find the server and original tool name.
        """
        server_name, tool_name = self._parse_qualified_name(qualified_name)
        if not server_name or not tool_name:
            return {"error": f"Invalid MCP tool name: {qualified_name}"}
        return self.call_tool(server_name, tool_name, arguments)

    # ── Status ───────────────────────────────────────────────────────────

    def get_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all MCP servers."""
        status = {}
        for name, client in self._clients.items():
            status[name] = {
                "status": client.status.value,
                "tools": len(client.get_tools()),
                "tool_names": [t.name for t in client.get_tools()],
            }
        return status

    @property
    def has_servers(self) -> bool:
        """Check if any MCP servers are configured."""
        return bool(self._configs)

    @property
    def connected_count(self) -> int:
        """Count of connected MCP servers."""
        return sum(
            1 for c in self._clients.values()
            if c.status == McpServerStatus.CONNECTED
        )

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _parse_qualified_name(name: str) -> tuple:
        """
        Parse 'mcp_{server}_{tool}' into (server_name, tool_name).

        Returns (None, None) if the name doesn't match the expected format.
        """
        from adelie.mcp_client import MCP_TOOL_PREFIX

        if not name.startswith(MCP_TOOL_PREFIX):
            return (None, None)

        without_prefix = name[len(MCP_TOOL_PREFIX):]
        parts = without_prefix.split("_", 1)
        if len(parts) == 2:
            return (parts[0], parts[1])
        return (None, None)
