"""
adelie/a2a/server.py

A2A HTTP server — extends the Gateway with agent-to-agent endpoints.

Endpoints:
    POST /a2a/tasks          — Create a new task
    GET  /a2a/tasks           — List all tasks
    GET  /a2a/tasks/<id>      — Get task status
    POST /a2a/tasks/<id>/cancel — Cancel a task

Inspired by Gemini CLI's a2a-server HTTP layer.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

from adelie.a2a.types import A2ATask, TaskState, EventType
from adelie.a2a.persistence import TaskStore

logger = logging.getLogger("adelie.a2a")


class A2AServer:
    """
    Agent-to-Agent protocol server.

    Can run standalone or alongside the Gateway on a different port.
    """

    def __init__(
        self,
        port: int = 8090,
        host: str = "127.0.0.1",
        token: str = "",
        store: Optional[TaskStore] = None,
    ):
        self._port = port
        self._host = host
        self._token = token
        self._store = store or TaskStore()
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._task_handler: Optional[Callable[[A2ATask], None]] = None

    def start(self) -> bool:
        """Start the A2A server in background."""
        if self._server:
            return False
        try:
            handler = _make_a2a_handler(self)
            self._server = HTTPServer((self._host, self._port), handler)
            self._thread = threading.Thread(
                target=self._server.serve_forever,
                daemon=True,
                name="adelie-a2a",
            )
            self._thread.start()
            logger.info(f"A2A server started on http://{self._host}:{self._port}")
            return True
        except Exception as e:
            logger.error(f"A2A server start failed: {e}")
            return False

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server = None
            self._thread = None

    @property
    def is_running(self) -> bool:
        return self._server is not None

    def on_task(self, handler: Callable[[A2ATask], None]) -> None:
        """Register handler for new tasks (called when task is submitted)."""
        self._task_handler = handler

    # ── Task Operations ──────────────────────────────────────────────────

    def create_task(self, prompt: str, metadata: Dict = None) -> A2ATask:
        """Create a new task."""
        task = A2ATask(prompt=prompt, metadata=metadata or {})
        self._store.save(task)
        if self._task_handler:
            self._task_handler(task)
        return task

    def get_task(self, task_id: str) -> Optional[A2ATask]:
        return self._store.load(task_id)

    def list_tasks(self) -> List[A2ATask]:
        return self._store.list_tasks()

    def cancel_task(self, task_id: str) -> bool:
        task = self._store.load(task_id)
        if not task or task.is_terminal:
            return False
        task.transition(TaskState.CANCELLED)
        self._store.save(task)
        return True

    def check_auth(self, headers: dict) -> bool:
        if not self._token:
            return True
        auth = headers.get("Authorization", "")
        return auth == f"Bearer {self._token}"


# ── HTTP Handler ─────────────────────────────────────────────────────────────


def _make_a2a_handler(server: A2AServer):

    class A2AHandler(BaseHTTPRequestHandler):

        def log_message(self, format, *args):
            logger.debug(f"A2A: {format % args}")

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

        def do_GET(self):
            if not server.check_auth(dict(self.headers)):
                return self._send_json({"error": "unauthorized"}, 401)

            path = urlparse(self.path).path

            # GET /a2a/tasks
            if path == "/a2a/tasks":
                tasks = server.list_tasks()
                self._send_json({
                    "tasks": [t.to_dict() for t in tasks],
                    "count": len(tasks),
                })
                return

            # GET /a2a/tasks/<id>
            m = re.match(r"^/a2a/tasks/([a-f0-9]+)$", path)
            if m:
                task = server.get_task(m.group(1))
                if task:
                    self._send_json(task.to_dict())
                else:
                    self._send_json({"error": "task not found"}, 404)
                return

            self._send_json({"error": "not found"}, 404)

        def do_POST(self):
            if not server.check_auth(dict(self.headers)):
                return self._send_json({"error": "unauthorized"}, 401)

            path = urlparse(self.path).path
            body = self._read_body()

            # POST /a2a/tasks
            if path == "/a2a/tasks":
                prompt = body.get("prompt", "")
                if not prompt:
                    return self._send_json({"error": "prompt is required"}, 400)
                task = server.create_task(prompt, metadata=body.get("metadata", {}))
                self._send_json(task.to_dict(), 201)
                return

            # POST /a2a/tasks/<id>/cancel
            m = re.match(r"^/a2a/tasks/([a-f0-9]+)/cancel$", path)
            if m:
                success = server.cancel_task(m.group(1))
                if success:
                    self._send_json({"ok": True, "action": "cancelled"})
                else:
                    self._send_json({"error": "task not found or already terminal"}, 404)
                return

            self._send_json({"error": "not found"}, 404)

    return A2AHandler
