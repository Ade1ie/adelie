"""
adelie/dashboard.py

Real-time web dashboard for the Adelie orchestrator.
Serves a single-page dashboard on a configurable port (default 5042).

Features:
  - SSE (Server-Sent Events) for live push to browsers
  - JSON REST API for initial state / history
  - Thread-safe event broadcasting with batching
  - ThreadingHTTPServer for concurrent SSE + API handling
  - No external dependencies — uses stdlib http.server

Started automatically from interactive.py when `adelie run` is called.
"""

from __future__ import annotations

import collections
import json
import queue
import re
import socketserver
import threading
import time
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Optional

from adelie.dashboard_html import DASHBOARD_HTML


# ── Event Bus ────────────────────────────────────────────────────────────────

class EventBus:
    """Thread-safe pub/sub for SSE clients with event coalescing."""

    def __init__(self):
        self._clients: list[queue.Queue] = []
        self._lock = threading.Lock()

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=500)
        with self._lock:
            self._clients.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            try:
                self._clients.remove(q)
            except ValueError:
                pass

    def publish(self, event_type: str, data: dict) -> None:
        payload = f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"
        with self._lock:
            dead: list[queue.Queue] = []
            for q in self._clients:
                try:
                    q.put_nowait(payload)
                except queue.Full:
                    dead.append(q)
            for q in dead:
                try:
                    self._clients.remove(q)
                except ValueError:
                    pass

    @property
    def client_count(self) -> int:
        with self._lock:
            return len(self._clients)


# ── Log Ring Buffer ──────────────────────────────────────────────────────────

class LogBuffer:
    """Thread-safe ring buffer for recent log entries using deque for O(1) ops."""

    def __init__(self, maxlen: int = 200):
        self._buf: collections.deque = collections.deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def append(self, entry: dict) -> None:
        with self._lock:
            self._buf.append(entry)

    def get_all(self) -> list[dict]:
        with self._lock:
            return list(self._buf)


# ── Dashboard State ──────────────────────────────────────────────────────────

class DashboardState:
    """
    Central state holder for the dashboard.
    Updated by UILogger hooks; read by HTTP handlers.
    """

    def __init__(self):
        self.goal: str = ""
        self.phase: str = "initial"
        self.workspace: str = ""
        self.cycle: int = 0
        self.state: str = "normal"
        self.agents: dict[str, dict] = {}
        self.metrics: dict = {}
        self.features: dict = {}  # Policy/Memory/Production/Harness status
        self.events = EventBus()
        self.logs = LogBuffer(maxlen=200)
        self._lock = threading.Lock()
        self._orchestrator = None  # Reference for intercept
        # Debounce tracking for agent updates
        self._agent_last_publish: dict[str, float] = {}
        self._agent_debounce_ms: float = 0.05  # 50ms debounce for same agent

    def update_agent(self, name: str, info: dict) -> None:
        now = time.monotonic()
        with self._lock:
            self.agents[name] = info
            last = self._agent_last_publish.get(name, 0)
            # Coalesce rapid agent updates (< 50ms apart) unless state changed
            prev_state = self._agent_last_publish.get(f"{name}_state")
            cur_state = info.get("state")
            if cur_state == prev_state and (now - last) < self._agent_debounce_ms:
                return
            self._agent_last_publish[name] = now
            self._agent_last_publish[f"{name}_state"] = cur_state
        self.events.publish("agent", {"name": name, **info})

    def update_cycle(self, iteration: int, phase: str, state: str) -> None:
        with self._lock:
            self.cycle = iteration
            self.phase = phase
            self.state = state
            # Reset agents
            for name in list(self.agents.keys()):
                self.agents[name] = {"state": "idle", "detail": "idle", "elapsed": 0}
            self._agent_last_publish.clear()
        self.events.publish("cycle_start", {"iteration": iteration, "phase": phase, "state": state})
        self.events.publish("state", {"cycle": iteration, "phase": phase, "goal": self.goal})

    def update_metrics(self, metrics: dict) -> None:
        with self._lock:
            self.metrics = metrics
        self.events.publish("metrics", metrics)

    def update_features(self, features: dict) -> None:
        """Update feature status (policy, memory, production, harness)."""
        with self._lock:
            self.features = features
        self.events.publish("features", features)

    def add_log(self, category: str, message: str) -> None:
        entry = {
            "timestamp": datetime.now().isoformat(timespec="milliseconds"),
            "category": category,
            "message": message,
        }
        self.logs.append(entry)
        self.events.publish("log", entry)

    def get_snapshot(self) -> dict:
        with self._lock:
            return {
                "goal": self.goal,
                "phase": self.phase,
                "workspace": self.workspace,
                "cycle": self.cycle,
                "state": self.state,
                "agents": dict(self.agents),
                "metrics": dict(self.metrics),
                "features": dict(self.features),
            }


# ── HTTP Request Handler ─────────────────────────────────────────────────────

def _strip_rich_markup(text: str) -> str:
    """Remove [bold], [cyan], [/cyan], etc. from Rich markup text."""
    return re.sub(r"\[/?[^\]]*\]", "", str(text))


class DashboardHandler(BaseHTTPRequestHandler):
    """HTTP handler for dashboard routes."""

    # Suppress default stderr logging
    def log_message(self, format, *args):
        pass

    def _send_json(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        ds: DashboardState = self.server._dashboard_state  # type: ignore

        if self.path == "/":
            self._send_html(DASHBOARD_HTML)

        elif self.path == "/api/state":
            self._send_json(ds.get_snapshot())

        elif self.path == "/api/logs":
            self._send_json({"logs": ds.logs.get_all()})

        elif self.path == "/api/metrics":
            try:
                from adelie.metrics import read_cycles
                cycles = read_cycles(last_n=30)
                self._send_json({"cycles": cycles})
            except Exception:
                self._send_json({"cycles": []})

        elif self.path == "/api/features":
            self._send_json(ds.features or {})

        elif self.path == "/events":
            self._handle_sse(ds)

        else:
            self.send_error(404)

    def do_POST(self):
        ds: DashboardState = self.server._dashboard_state  # type: ignore

        if self.path == "/api/intercept":
            # Read body
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length) if content_length else b'{}'
            try:
                data = json.loads(body.decode('utf-8'))
            except Exception:
                data = {}

            reason = data.get('reason', 'Dashboard intercept')

            if ds._orchestrator:
                result = ds._orchestrator.intercept(reason)
                self._send_json(result)
            else:
                self._send_json({"error": "Orchestrator not connected"}, 503)
        else:
            self.send_error(404)

    def _handle_sse(self, ds: DashboardState) -> None:
        """Stream Server-Sent Events to the client with batched flushing."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        # Send initial state
        state_data = json.dumps(ds.get_snapshot(), ensure_ascii=False, default=str)
        self.wfile.write(f"event: state\ndata: {state_data}\n\n".encode("utf-8"))
        self.wfile.flush()

        client_q = ds.events.subscribe()
        try:
            while True:
                # Batch: collect all available events within a short window
                batch: list[str] = []
                try:
                    # Block up to 100ms for first event, then drain
                    payload = client_q.get(timeout=0.1)
                    batch.append(payload)
                except queue.Empty:
                    pass

                # Drain any additional queued events (non-blocking)
                while not client_q.empty() and len(batch) < 50:
                    try:
                        batch.append(client_q.get_nowait())
                    except queue.Empty:
                        break

                if batch:
                    # Write all events in one I/O call
                    combined = "".join(batch)
                    self.wfile.write(combined.encode("utf-8"))
                    self.wfile.flush()
                else:
                    # Send keepalive every ~15s (150 empty 100ms cycles)
                    # Use a counter to avoid frequent keepalives
                    if not hasattr(self, '_keepalive_counter'):
                        self._keepalive_counter = 0
                    self._keepalive_counter += 1
                    if self._keepalive_counter >= 150:  # ~15 seconds
                        self.wfile.write(": keepalive\n\n".encode("utf-8"))
                        self.wfile.flush()
                        self._keepalive_counter = 0

        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            ds.events.unsubscribe(client_q)


# ── Threading HTTP Server ────────────────────────────────────────────────────

class ThreadingDashboardHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    """Multi-threaded HTTP server so SSE connections don't block API requests."""
    daemon_threads = True
    allow_reuse_address = True

    def handle_error(self, request, client_address):
        """Silently ignore client-side disconnects (common on Windows)."""
        import sys
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionAbortedError, ConnectionResetError, BrokenPipeError)):
            return  # client closed connection early — nothing to do
        super().handle_error(request, client_address)


# ── Dashboard Server ─────────────────────────────────────────────────────────

class DashboardServer:
    """
    Threaded HTTP server that serves the Adelie dashboard.

    Usage:
        ds = DashboardServer(state=dashboard_state, port=5042)
        ds.start()   # non-blocking
        ...
        ds.stop()
    """

    def __init__(self, state: DashboardState, port: int = 5042):
        self.state = state
        self.port = port
        self._httpd: Optional[ThreadingDashboardHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> bool:
        """Start the dashboard server in a background thread. Returns True on success."""
        try:
            self._httpd = ThreadingDashboardHTTPServer(("0.0.0.0", self.port), DashboardHandler)
            self._httpd._dashboard_state = self.state  # type: ignore
            self._httpd.timeout = 0.5
            self._thread = threading.Thread(
                target=self._serve_forever,
                daemon=True,
                name="adelie-dashboard",
            )
            self._thread.start()
            return True
        except OSError as e:
            # Port in use or permission denied
            return False

    def _serve_forever(self) -> None:
        """Serve until stopped."""
        if self._httpd:
            self._httpd.serve_forever()

    def stop(self) -> None:
        """Shut down the dashboard server."""
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None

    @property
    def url(self) -> str:
        return f"http://localhost:{self.port}"
