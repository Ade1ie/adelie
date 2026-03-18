"""tests/test_gateway.py — Tests for the Adelie REST API gateway."""
from __future__ import annotations

import json
import threading
import time
import urllib.request
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_orchestrator():
    """Create a mock orchestrator."""
    orch = MagicMock()
    orch._running = True
    orch.loop_iteration = 5
    orch.state = "normal"
    orch.phase = "mid"
    orch.goal = "Test goal"
    return orch


@pytest.fixture
def gateway(mock_orchestrator):
    """Start a gateway on a random port, yield it, then stop."""
    from adelie.gateway import AdelieGateway
    # Use port 0 to let OS pick an available port
    gw = AdelieGateway(orchestrator=mock_orchestrator, port=0, host="127.0.0.1")

    # We need to bind to get the actual port
    from http.server import HTTPServer
    from adelie.gateway import _make_handler
    handler = _make_handler(gw)
    server = HTTPServer(("127.0.0.1", 0), handler)
    gw._server = server
    gw._port = server.server_address[1]
    gw._thread = threading.Thread(target=server.serve_forever, daemon=True)
    gw._thread.start()
    time.sleep(0.1)  # Wait for server to start

    yield gw

    server.shutdown()


def _get(gw, path: str) -> dict:
    """Helper: HTTP GET and parse JSON."""
    url = f"{gw.url}{path}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _post(gw, path: str, body: dict) -> dict:
    """Helper: HTTP POST with JSON body."""
    url = f"{gw.url}{path}"
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ── Unit Tests (no server needed) ────────────────────────────────────────────


class TestGatewayInit:
    def test_create_gateway(self):
        from adelie.gateway import AdelieGateway
        gw = AdelieGateway(port=9999)
        assert gw._port == 9999
        assert not gw.is_running

    def test_url_property(self):
        from adelie.gateway import AdelieGateway
        gw = AdelieGateway(port=8080, host="0.0.0.0")
        assert gw.url == "http://0.0.0.0:8080"


class TestGatewayAuth:
    def test_no_token_allows_all(self):
        from adelie.gateway import AdelieGateway
        gw = AdelieGateway(token="")
        assert gw.check_auth({}) is True

    def test_valid_token(self):
        from adelie.gateway import AdelieGateway
        gw = AdelieGateway(token="secret123")
        assert gw.check_auth({"Authorization": "Bearer secret123"}) is True

    def test_invalid_token(self):
        from adelie.gateway import AdelieGateway
        gw = AdelieGateway(token="secret123")
        assert gw.check_auth({"Authorization": "Bearer wrong"}) is False
        assert gw.check_auth({}) is False


class TestGatewayHandlers:
    def test_handle_status_with_orchestrator(self, mock_orchestrator):
        from adelie.gateway import AdelieGateway
        gw = AdelieGateway(orchestrator=mock_orchestrator)
        result = gw.handle_status()
        assert result["running"] is True
        assert result["loop_iteration"] == 5
        assert result["phase"] == "mid"

    def test_handle_status_no_orchestrator(self):
        from adelie.gateway import AdelieGateway
        gw = AdelieGateway(orchestrator=None)
        result = gw.handle_status()
        assert result["status"] == "no_orchestrator"

    def test_handle_control_pause(self, mock_orchestrator):
        from adelie.gateway import AdelieGateway
        gw = AdelieGateway(orchestrator=mock_orchestrator)
        result = gw.handle_control({"action": "pause"})
        assert result["ok"] is True
        mock_orchestrator.pause.assert_called_once()

    def test_handle_control_resume(self, mock_orchestrator):
        from adelie.gateway import AdelieGateway
        gw = AdelieGateway(orchestrator=mock_orchestrator)
        result = gw.handle_control({"action": "resume"})
        assert result["ok"] is True
        mock_orchestrator.resume.assert_called_once()

    def test_handle_control_unknown(self, mock_orchestrator):
        from adelie.gateway import AdelieGateway
        gw = AdelieGateway(orchestrator=mock_orchestrator)
        result = gw.handle_control({"action": "explode"})
        assert "error" in result

    def test_handle_control_no_orchestrator(self):
        from adelie.gateway import AdelieGateway
        gw = AdelieGateway(orchestrator=None)
        result = gw.handle_control({"action": "pause"})
        assert "error" in result


# ── Integration Tests (actual HTTP) ──────────────────────────────────────────


class TestGatewayHTTP:
    def test_health_endpoint(self, gateway):
        result = _get(gateway, "/api/health")
        assert result["ok"] is True

    def test_status_endpoint(self, gateway):
        result = _get(gateway, "/api/status")
        assert "loop_iteration" in result
        assert result["phase"] == "mid"

    def test_tools_endpoint(self, gateway):
        result = _get(gateway, "/api/tools")
        assert "tools" in result
        assert "count" in result

    def test_control_pause(self, gateway):
        result = _post(gateway, "/api/control", {"action": "pause"})
        assert result["ok"] is True

    def test_not_found(self, gateway):
        try:
            _get(gateway, "/api/nonexistent")
        except urllib.error.HTTPError as e:
            assert e.code == 404

    def test_post_not_found(self, gateway):
        try:
            _post(gateway, "/api/nonexistent", {})
        except urllib.error.HTTPError as e:
            assert e.code == 404


class TestGatewayHTTPAuth:
    def test_auth_required(self, mock_orchestrator):
        from adelie.gateway import AdelieGateway
        from http.server import HTTPServer
        from adelie.gateway import _make_handler

        gw = AdelieGateway(orchestrator=mock_orchestrator, port=0, token="mysecret")
        handler = _make_handler(gw)
        server = HTTPServer(("127.0.0.1", 0), handler)
        gw._server = server
        gw._port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        time.sleep(0.1)

        try:
            # Without token → 401
            try:
                _get(gw, "/api/status")
                assert False, "Should have raised"
            except urllib.error.HTTPError as e:
                assert e.code == 401

            # With valid token → 200
            url = f"{gw.url}/api/status"
            req = urllib.request.Request(url)
            req.add_header("Authorization", "Bearer mysecret")
            with urllib.request.urlopen(req, timeout=5) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                assert "loop_iteration" in result
        finally:
            server.shutdown()
