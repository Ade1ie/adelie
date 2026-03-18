"""
adelie/gateway.py

Lightweight REST API gateway for external clients.

Provides HTTP endpoints to monitor and control the Adelie orchestrator.
No external dependencies — uses Python's built-in http.server module.

Inspired by OpenClaw's gateway (WebSocket server with auth/status/control).

Endpoints:
    GET  /api/status    — orchestrator state + metrics
    GET  /api/tools     — registered tool list
    GET  /api/checkpoints — checkpoint list
    POST /api/feedback  — submit user feedback
    POST /api/control   — pause/resume/shutdown

Usage:
    from adelie.gateway import AdelieGateway
    gw = AdelieGateway(orchestrator, port=8080)
    gw.start()   # starts in background thread
    gw.stop()
"""

from __future__ import annotations

import json
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Dict, Optional
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger("adelie.gateway")

# ── Constants ────────────────────────────────────────────────────────────────

DEFAULT_PORT = 8080
API_PREFIX = "/api"


class AdelieGateway:
    """
    Lightweight HTTP API gateway for Adelie orchestrator.

    Runs in a background thread, exposing REST endpoints for
    external clients (web dashboards, IDE extensions, mobile apps).
    """

    def __init__(
        self,
        orchestrator=None,
        port: int = DEFAULT_PORT,
        host: str = "127.0.0.1",
        token: str = "",
    ):
        self._orchestrator = orchestrator
        self._port = port
        self._host = host
        self._token = token
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._event_listeners: list = []

    # ── Lifecycle ────────────────────────────────────────────────────────

    def start(self) -> bool:
        """Start the gateway server in a background thread."""
        if self._server:
            return False

        try:
            handler = _make_handler(self)
            self._server = HTTPServer((self._host, self._port), handler)
            self._thread = threading.Thread(
                target=self._server.serve_forever,
                daemon=True,
                name="adelie-gateway",
            )
            self._thread.start()
            logger.info(f"Gateway started on http://{self._host}:{self._port}")
            return True
        except Exception as e:
            logger.error(f"Gateway start failed: {e}")
            return False

    def stop(self) -> None:
        """Stop the gateway server."""
        if self._server:
            self._server.shutdown()
            self._server = None
            self._thread = None
            logger.info("Gateway stopped")

    @property
    def is_running(self) -> bool:
        return self._server is not None

    @property
    def url(self) -> str:
        return f"http://{self._host}:{self._port}"

    # ── API Handlers ─────────────────────────────────────────────────────

    def handle_status(self) -> Dict[str, Any]:
        """GET /api/status"""
        orch = self._orchestrator
        if not orch:
            return {"status": "no_orchestrator"}

        return {
            "running": getattr(orch, "_running", False),
            "loop_iteration": getattr(orch, "loop_iteration", 0),
            "state": getattr(orch, "state", "unknown"),
            "phase": getattr(orch, "phase", "unknown"),
            "goal": getattr(orch, "goal", ""),
        }

    def handle_tools(self) -> Dict[str, Any]:
        """GET /api/tools"""
        try:
            from adelie.tool_registry import get_registry
            registry = get_registry()
            tools = []
            for tool in registry.get_all():
                tools.append({
                    "name": tool.name,
                    "category": tool.category.value if hasattr(tool.category, 'value') else str(tool.category),
                    "description": tool.description,
                    "enabled": tool.enabled,
                    "mcp_server": tool.mcp_server,
                })
            return {"tools": tools, "count": len(tools)}
        except Exception as e:
            return {"error": str(e)}

    def handle_checkpoints(self) -> Dict[str, Any]:
        """GET /api/checkpoints"""
        try:
            from adelie.checkpoint import CheckpointManager
            mgr = CheckpointManager()
            cps = mgr.list_checkpoints()
            return {
                "checkpoints": [
                    {
                        "id": cp.checkpoint_id,
                        "created_at": cp.created_at,
                        "cycle": cp.cycle,
                        "phase": cp.phase,
                        "files_count": len(cp.files),
                        "description": cp.description,
                    }
                    for cp in cps
                ],
                "count": len(cps),
            }
        except Exception as e:
            return {"error": str(e)}

    def handle_feedback(self, body: Dict) -> Dict[str, Any]:
        """POST /api/feedback"""
        try:
            from adelie.feedback_queue import submit
            message = body.get("message", "")
            priority = body.get("priority", "normal")
            if not message:
                return {"error": "message is required"}
            fb_id = submit(message, priority=priority, source="gateway")
            return {"ok": True, "feedback_id": fb_id}
        except ImportError:
            return {"error": "feedback_queue module not available"}
        except Exception as e:
            return {"error": str(e)}

    def handle_control(self, body: Dict) -> Dict[str, Any]:
        """POST /api/control"""
        orch = self._orchestrator
        if not orch:
            return {"error": "no orchestrator"}

        action = body.get("action", "").lower()

        if action == "pause":
            orch.pause()
            return {"ok": True, "action": "paused"}
        elif action == "resume":
            orch.resume()
            return {"ok": True, "action": "resumed"}
        elif action == "shutdown":
            orch._running = False
            return {"ok": True, "action": "shutdown_requested"}
        else:
            return {"error": f"Unknown action: {action}. Use: pause, resume, shutdown"}

    # ── Auth ─────────────────────────────────────────────────────────────

    def check_auth(self, headers: dict) -> bool:
        """Validate token auth if configured."""
        if not self._token:
            return True  # No auth required
        auth = headers.get("Authorization", "")
        return auth == f"Bearer {self._token}"


# ── HTTP Handler ─────────────────────────────────────────────────────────────


def _make_handler(gateway: AdelieGateway):
    """Create a request handler class bound to the gateway instance."""

    class GatewayHandler(BaseHTTPRequestHandler):

        def log_message(self, format, *args):
            """Suppress default HTTP logging — use our logger instead."""
            logger.debug(f"Gateway: {format % args}")

        def _send_json(self, data: dict, status: int = 200):
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(data, ensure_ascii=False, default=str).encode("utf-8"))

        def _read_body(self) -> dict:
            length = int(self.headers.get("Content-Length", 0))
            if length == 0:
                return {}
            body = self.rfile.read(length)
            try:
                return json.loads(body.decode("utf-8"))
            except Exception:
                return {}

        def do_OPTIONS(self):
            """Handle CORS preflight."""
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
            self.end_headers()

        def do_GET(self):
            if not gateway.check_auth(dict(self.headers)):
                return self._send_json({"error": "unauthorized"}, 401)

            path = urlparse(self.path).path

            routes = {
                f"{API_PREFIX}/status": gateway.handle_status,
                f"{API_PREFIX}/tools": gateway.handle_tools,
                f"{API_PREFIX}/checkpoints": gateway.handle_checkpoints,
            }

            handler = routes.get(path)
            if handler:
                self._send_json(handler())
            elif path == f"{API_PREFIX}/health":
                self._send_json({"ok": True})
            else:
                self._send_json({"error": "not found"}, 404)

        def do_POST(self):
            if not gateway.check_auth(dict(self.headers)):
                return self._send_json({"error": "unauthorized"}, 401)

            path = urlparse(self.path).path
            body = self._read_body()

            if path == f"{API_PREFIX}/feedback":
                self._send_json(gateway.handle_feedback(body))
            elif path == f"{API_PREFIX}/control":
                self._send_json(gateway.handle_control(body))
            else:
                self._send_json({"error": "not found"}, 404)

    return GatewayHandler
