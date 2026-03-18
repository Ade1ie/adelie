"""
adelie/mcp_client.py

MCP (Model Context Protocol) client for connecting to external tool servers.

Supports stdio and SSE transports. Inspired by gemini-cli's mcp-client.ts.
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("adelie.mcp")

# ── Constants ────────────────────────────────────────────────────────────────

MCP_DEFAULT_TIMEOUT_SEC = 600  # 10 minutes (matches gemini-cli)
MCP_TOOL_PREFIX = "mcp_"


class McpServerStatus(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class McpServerConfig:
    """Configuration for a single MCP server."""
    command: Optional[str] = None
    args: List[str] = field(default_factory=list)
    url: Optional[str] = None          # for SSE transport
    env: Dict[str, str] = field(default_factory=dict)
    timeout: int = MCP_DEFAULT_TIMEOUT_SEC
    enabled: bool = True


@dataclass
class McpToolInfo:
    """A tool discovered from an MCP server."""
    name: str
    server_name: str
    description: str = ""
    input_schema: Dict[str, Any] = field(default_factory=dict)

    @property
    def qualified_name(self) -> str:
        """Generate registry-safe qualified name: mcp_{server}_{tool}."""
        clean_server = self.server_name.replace("-", "_").replace(".", "_")
        clean_name = self.name.replace("-", "_").replace(".", "_")
        return f"{MCP_TOOL_PREFIX}{clean_server}_{clean_name}"


class McpClient:
    """
    Client for a single MCP server.

    Manages the connection lifecycle (connect → discover → call → disconnect)
    using the MCP protocol over stdio or SSE transport.
    """

    def __init__(self, server_name: str, config: McpServerConfig):
        self.server_name = server_name
        self.config = config
        self.status = McpServerStatus.DISCONNECTED
        self._process: Optional[subprocess.Popen] = None
        self._tools: List[McpToolInfo] = []
        self._request_id = 0
        self._lock = threading.Lock()
        self._reader_thread: Optional[threading.Thread] = None
        self._pending: Dict[int, threading.Event] = {}
        self._results: Dict[int, Any] = {}
        self._stop_event = threading.Event()

    # ── Connection ───────────────────────────────────────────────────────

    def connect(self) -> bool:
        """Connect to the MCP server via stdio transport."""
        if self.status == McpServerStatus.CONNECTED:
            return True

        if not self.config.command:
            logger.error(f"MCP server '{self.server_name}': no command configured")
            self.status = McpServerStatus.ERROR
            return False

        self.status = McpServerStatus.CONNECTING

        try:
            env = {**dict(__import__("os").environ), **self.config.env}

            cmd = [self.config.command] + self.config.args
            logger.info(f"MCP '{self.server_name}': starting {' '.join(cmd)}")

            self._process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                bufsize=0,
            )

            self._stop_event.clear()
            self._reader_thread = threading.Thread(
                target=self._read_loop,
                daemon=True,
                name=f"mcp-reader-{self.server_name}",
            )
            self._reader_thread.start()

            # Send initialize request
            resp = self._send_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "adelie",
                    "version": "0.1.0",
                },
            })

            if resp is None:
                raise RuntimeError("No response to initialize")

            # Send initialized notification
            self._send_notification("notifications/initialized", {})

            self.status = McpServerStatus.CONNECTED
            logger.info(f"MCP '{self.server_name}': connected successfully")
            return True

        except Exception as e:
            logger.error(f"MCP '{self.server_name}': connection failed: {e}")
            self.status = McpServerStatus.ERROR
            self._cleanup_process()
            return False

    def disconnect(self) -> None:
        """Disconnect from the MCP server."""
        if self._process:
            self._stop_event.set()
            self._cleanup_process()
        self.status = McpServerStatus.DISCONNECTED
        self._tools.clear()
        logger.info(f"MCP '{self.server_name}': disconnected")

    # ── Tool Discovery ───────────────────────────────────────────────────

    def discover_tools(self) -> List[McpToolInfo]:
        """
        Discover available tools from the MCP server.

        Returns:
            List of McpToolInfo objects describing available tools.
        """
        if self.status != McpServerStatus.CONNECTED:
            logger.warning(f"MCP '{self.server_name}': not connected, skipping tool discovery")
            return []

        try:
            resp = self._send_request("tools/list", {})
            if resp is None:
                return []

            tools_data = resp.get("tools", [])
            self._tools = []

            for td in tools_data:
                tool = McpToolInfo(
                    name=td.get("name", ""),
                    server_name=self.server_name,
                    description=td.get("description", ""),
                    input_schema=td.get("inputSchema", {}),
                )
                self._tools.append(tool)

            logger.info(
                f"MCP '{self.server_name}': discovered {len(self._tools)} tools: "
                f"{[t.name for t in self._tools]}"
            )
            return list(self._tools)

        except Exception as e:
            logger.error(f"MCP '{self.server_name}': tool discovery failed: {e}")
            return []

    # ── Tool Invocation ──────────────────────────────────────────────────

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call a tool on the MCP server.

        Args:
            tool_name: Original tool name (not qualified).
            arguments: Tool arguments.

        Returns:
            Tool result as a dict with 'content' key.
        """
        if self.status != McpServerStatus.CONNECTED:
            return {"error": f"Server '{self.server_name}' not connected"}

        try:
            resp = self._send_request("tools/call", {
                "name": tool_name,
                "arguments": arguments,
            })

            if resp is None:
                return {"error": "No response from MCP server"}

            if resp.get("isError"):
                return {"error": self._extract_text(resp)}

            return resp

        except Exception as e:
            return {"error": f"MCP tool call failed: {e}"}

    def get_tools(self) -> List[McpToolInfo]:
        """Return previously discovered tools."""
        return list(self._tools)

    # ── JSON-RPC Transport ───────────────────────────────────────────────

    def _next_id(self) -> int:
        with self._lock:
            self._request_id += 1
            return self._request_id

    def _send_request(self, method: str, params: Dict[str, Any]) -> Optional[Dict]:
        """Send a JSON-RPC request and wait for the response."""
        if not self._process or not self._process.stdin:
            return None

        req_id = self._next_id()
        msg = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }

        event = threading.Event()
        self._pending[req_id] = event

        try:
            data = json.dumps(msg)
            content = f"Content-Length: {len(data)}\r\n\r\n{data}"
            self._process.stdin.write(content.encode("utf-8"))
            self._process.stdin.flush()

            if not event.wait(timeout=self.config.timeout):
                logger.error(f"MCP '{self.server_name}': request timeout (method={method})")
                return None

            result = self._results.pop(req_id, None)
            if isinstance(result, dict) and "error" in result:
                error = result["error"]
                logger.error(
                    f"MCP '{self.server_name}': server error: "
                    f"{error.get('message', 'unknown')}"
                )
                return None

            return result

        except Exception as e:
            logger.error(f"MCP '{self.server_name}': send failed: {e}")
            return None
        finally:
            self._pending.pop(req_id, None)

    def _send_notification(self, method: str, params: Dict[str, Any]) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        if not self._process or not self._process.stdin:
            return

        msg = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }

        try:
            data = json.dumps(msg)
            content = f"Content-Length: {len(data)}\r\n\r\n{data}"
            self._process.stdin.write(content.encode("utf-8"))
            self._process.stdin.flush()
        except Exception as e:
            logger.error(f"MCP '{self.server_name}': notification failed: {e}")

    def _read_loop(self) -> None:
        """Background thread: reads JSON-RPC messages from stdout."""
        try:
            while not self._stop_event.is_set():
                if not self._process or not self._process.stdout:
                    break

                # Read headers
                headers = {}
                while True:
                    line = self._process.stdout.readline()
                    if not line:
                        return  # EOF
                    line = line.decode("utf-8", errors="replace").strip()
                    if not line:
                        break
                    if ":" in line:
                        key, val = line.split(":", 1)
                        headers[key.strip().lower()] = val.strip()

                content_length = int(headers.get("content-length", "0"))
                if content_length == 0:
                    continue

                body = self._process.stdout.read(content_length)
                if not body:
                    continue

                try:
                    msg = json.loads(body.decode("utf-8"))
                except json.JSONDecodeError:
                    continue

                # Handle response
                msg_id = msg.get("id")
                if msg_id is not None and msg_id in self._pending:
                    if "error" in msg:
                        self._results[msg_id] = {"error": msg["error"]}
                    else:
                        self._results[msg_id] = msg.get("result", {})
                    self._pending[msg_id].set()

        except Exception as e:
            if not self._stop_event.is_set():
                logger.error(f"MCP '{self.server_name}': reader error: {e}")

    # ── Helpers ──────────────────────────────────────────────────────────

    def _cleanup_process(self) -> None:
        """Terminate the MCP server process."""
        if self._process:
            try:
                self._process.stdin.close() if self._process.stdin else None
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None

    @staticmethod
    def _extract_text(resp: Dict) -> str:
        """Extract text content from MCP response."""
        content = resp.get("content", [])
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
        return "\n".join(parts) if parts else str(resp)
