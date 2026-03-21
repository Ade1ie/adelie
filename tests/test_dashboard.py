"""
tests/test_dashboard.py

Tests for the Adelie dashboard server components:
  - EventBus pub/sub and queue overflow handling
  - LogBuffer deque-based ring buffer
  - DashboardState thread safety and agent debouncing
  - ThreadingDashboardHTTPServer concurrent request support
"""

import json
import queue
import threading
import time
import urllib.request
import urllib.error

import pytest


# ── EventBus Tests ───────────────────────────────────────────────────────────

class TestEventBus:
    def test_subscribe_and_publish(self):
        from adelie.dashboard import EventBus
        bus = EventBus()
        q = bus.subscribe()
        bus.publish("test", {"msg": "hello"})
        payload = q.get_nowait()
        assert "event: test" in payload
        assert "hello" in payload

    def test_multiple_subscribers(self):
        from adelie.dashboard import EventBus
        bus = EventBus()
        q1 = bus.subscribe()
        q2 = bus.subscribe()
        bus.publish("x", {"v": 1})
        assert not q1.empty()
        assert not q2.empty()
        p1 = q1.get_nowait()
        p2 = q2.get_nowait()
        assert p1 == p2

    def test_unsubscribe(self):
        from adelie.dashboard import EventBus
        bus = EventBus()
        q = bus.subscribe()
        assert bus.client_count == 1
        bus.unsubscribe(q)
        assert bus.client_count == 0

    def test_unsubscribe_nonexistent(self):
        from adelie.dashboard import EventBus
        bus = EventBus()
        q: queue.Queue = queue.Queue()
        bus.unsubscribe(q)  # should not raise

    def test_full_queue_drops_client(self):
        from adelie.dashboard import EventBus
        bus = EventBus()
        q = bus.subscribe()
        # Fill the queue to max (500)
        for i in range(500):
            bus.publish("fill", {"i": i})
        assert bus.client_count == 1
        # Next publish should drop the full client
        bus.publish("overflow", {"drop": True})
        assert bus.client_count == 0

    def test_publish_json_format(self):
        from adelie.dashboard import EventBus
        bus = EventBus()
        q = bus.subscribe()
        bus.publish("metrics", {"tokens": 1000, "time": 3.5})
        payload = q.get_nowait()
        # Parse SSE format
        lines = payload.strip().split("\n")
        assert lines[0] == "event: metrics"
        data_line = lines[1][len("data: "):]
        parsed = json.loads(data_line)
        assert parsed["tokens"] == 1000
        assert parsed["time"] == 3.5

    def test_thread_safe_publish(self):
        from adelie.dashboard import EventBus
        bus = EventBus()
        q = bus.subscribe()
        errors = []

        def publisher(n):
            try:
                for i in range(100):
                    bus.publish("t", {"n": n, "i": i})
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=publisher, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        # Should have received many events (some may be dropped if queue full)
        count = 0
        while not q.empty():
            q.get_nowait()
            count += 1
        assert count > 0


# ── LogBuffer Tests ──────────────────────────────────────────────────────────

class TestLogBuffer:
    def test_append_and_get(self):
        from adelie.dashboard import LogBuffer
        buf = LogBuffer(maxlen=10)
        buf.append({"msg": "test"})
        result = buf.get_all()
        assert len(result) == 1
        assert result[0]["msg"] == "test"

    def test_ring_buffer_overflow(self):
        from adelie.dashboard import LogBuffer
        buf = LogBuffer(maxlen=5)
        for i in range(10):
            buf.append({"i": i})
        result = buf.get_all()
        assert len(result) == 5
        # Should keep the last 5 entries
        assert result[0]["i"] == 5
        assert result[4]["i"] == 9

    def test_get_all_returns_copy(self):
        from adelie.dashboard import LogBuffer
        buf = LogBuffer(maxlen=10)
        buf.append({"msg": "a"})
        r1 = buf.get_all()
        r1.append({"msg": "extra"})
        r2 = buf.get_all()
        assert len(r2) == 1  # original buffer unchanged

    def test_thread_safe_append(self):
        from adelie.dashboard import LogBuffer
        buf = LogBuffer(maxlen=200)
        errors = []

        def writer(start):
            try:
                for i in range(100):
                    buf.append({"v": start + i})
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i * 100,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        result = buf.get_all()
        assert len(result) == 200  # maxlen capped


# ── DashboardState Tests ─────────────────────────────────────────────────────

class TestDashboardState:
    def test_initial_state(self):
        from adelie.dashboard import DashboardState
        ds = DashboardState()
        snap = ds.get_snapshot()
        assert snap["phase"] == "initial"
        assert snap["cycle"] == 0
        assert snap["goal"] == ""

    def test_update_cycle(self):
        from adelie.dashboard import DashboardState
        ds = DashboardState()
        q = ds.events.subscribe()
        ds.update_cycle(1, "mid", "normal")
        snap = ds.get_snapshot()
        assert snap["cycle"] == 1
        assert snap["phase"] == "mid"

    def test_update_agent_publishes_event(self):
        from adelie.dashboard import DashboardState
        ds = DashboardState()
        q = ds.events.subscribe()
        ds.update_agent("Coder", {"state": "running", "detail": "coding"})
        payload = q.get_nowait()
        assert "Coder" in payload
        assert "running" in payload

    def test_agent_debounce_same_state(self):
        from adelie.dashboard import DashboardState
        ds = DashboardState()
        q = ds.events.subscribe()
        # First update should publish
        ds.update_agent("Coder", {"state": "running", "detail": "step1"})
        assert not q.empty()
        q.get_nowait()
        # Immediate same-state update should be debounced
        ds.update_agent("Coder", {"state": "running", "detail": "step2"})
        assert q.empty()  # debounced!

    def test_agent_state_change_not_debounced(self):
        from adelie.dashboard import DashboardState
        ds = DashboardState()
        q = ds.events.subscribe()
        ds.update_agent("Coder", {"state": "running", "detail": "coding"})
        q.get_nowait()
        # Different state should NOT be debounced
        ds.update_agent("Coder", {"state": "done", "detail": "finished"})
        assert not q.empty()

    def test_add_log(self):
        from adelie.dashboard import DashboardState
        ds = DashboardState()
        ds.add_log("info", "Test message")
        logs = ds.logs.get_all()
        assert len(logs) == 1
        assert logs[0]["message"] == "Test message"

    def test_update_metrics(self):
        from adelie.dashboard import DashboardState
        ds = DashboardState()
        q = ds.events.subscribe()
        ds.update_metrics({"total_tokens": 500, "cycle_time": 2.5})
        snap = ds.get_snapshot()
        assert snap["metrics"]["total_tokens"] == 500

    def test_snapshot_thread_safety(self):
        from adelie.dashboard import DashboardState
        ds = DashboardState()
        errors = []

        def updater():
            try:
                for i in range(100):
                    ds.update_agent(f"Agent{i%5}", {"state": "running"})
                    ds.add_log("info", f"msg {i}")
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for _ in range(100):
                    ds.get_snapshot()
                    ds.logs.get_all()
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=updater),
            threading.Thread(target=reader),
            threading.Thread(target=updater),
            threading.Thread(target=reader),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors


# ── ThreadingHTTPServer Tests ────────────────────────────────────────────────

class TestThreadingServer:
    def test_server_start_stop(self):
        from adelie.dashboard import DashboardServer, DashboardState
        ds = DashboardState()
        server = DashboardServer(state=ds, port=15042)
        assert server.start()
        time.sleep(0.3)
        # Server should respond
        try:
            r = urllib.request.urlopen("http://localhost:15042/api/state", timeout=2)
            data = json.loads(r.read())
            assert "phase" in data
        finally:
            server.stop()

    def test_concurrent_api_requests(self):
        from adelie.dashboard import DashboardServer, DashboardState
        ds = DashboardState()
        ds.goal = "test goal"
        server = DashboardServer(state=ds, port=15043)
        assert server.start()
        time.sleep(0.3)

        results = []
        errors = []

        def fetch_state():
            try:
                r = urllib.request.urlopen("http://localhost:15043/api/state", timeout=2)
                data = json.loads(r.read())
                results.append(data)
            except Exception as e:
                errors.append(e)

        try:
            threads = [threading.Thread(target=fetch_state) for _ in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=5)

            assert not errors
            assert len(results) == 5
            for r in results:
                assert r["goal"] == "test goal"
        finally:
            server.stop()

    def test_html_page_served(self):
        from adelie.dashboard import DashboardServer, DashboardState
        ds = DashboardState()
        server = DashboardServer(state=ds, port=15044)
        assert server.start()
        time.sleep(0.3)
        try:
            r = urllib.request.urlopen("http://localhost:15044/", timeout=2)
            html = r.read().decode("utf-8")
            assert "Adelie Dashboard" in html
            assert "requestAnimationFrame" in html
        finally:
            server.stop()

    def test_logs_api(self):
        from adelie.dashboard import DashboardServer, DashboardState
        ds = DashboardState()
        ds.add_log("info", "test log entry")
        server = DashboardServer(state=ds, port=15045)
        assert server.start()
        time.sleep(0.3)
        try:
            r = urllib.request.urlopen("http://localhost:15045/api/logs", timeout=2)
            data = json.loads(r.read())
            assert len(data["logs"]) == 1
            assert data["logs"][0]["message"] == "test log entry"
        finally:
            server.stop()
