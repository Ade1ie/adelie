"""tests/test_a2a.py — Tests for the A2A protocol."""
from __future__ import annotations

import json
import threading
import time
import urllib.request
import urllib.error

import pytest


# ── Type Tests ───────────────────────────────────────────────────────────────


class TestTaskState:
    def test_enum_values(self):
        from adelie.a2a.types import TaskState
        assert TaskState.SUBMITTED == "submitted"
        assert TaskState.WORKING == "working"
        assert TaskState.COMPLETED == "completed"
        assert TaskState.FAILED == "failed"
        assert TaskState.CANCELLED == "cancelled"


class TestEventType:
    def test_enum_values(self):
        from adelie.a2a.types import EventType
        assert EventType.TEXT_CONTENT == "text-content"
        assert EventType.STATE_CHANGE == "state-change"


class TestA2ATask:
    def test_create_task(self):
        from adelie.a2a.types import A2ATask, TaskState
        task = A2ATask(prompt="hello")
        assert task.prompt == "hello"
        assert task.state == TaskState.SUBMITTED
        assert not task.is_terminal

    def test_transition(self):
        from adelie.a2a.types import A2ATask, TaskState
        task = A2ATask(prompt="test")
        task.transition(TaskState.WORKING)
        assert task.state == TaskState.WORKING
        assert task.updated_at != ""

    def test_is_terminal(self):
        from adelie.a2a.types import A2ATask, TaskState
        task = A2ATask(prompt="test")
        assert not task.is_terminal
        task.transition(TaskState.COMPLETED)
        assert task.is_terminal

    def test_add_event(self):
        from adelie.a2a.types import A2ATask, EventType
        task = A2ATask(prompt="test")
        event = task.add_event(EventType.TEXT_CONTENT, {"text": "hi"})
        assert len(task.events) == 1
        assert event.event_type == EventType.TEXT_CONTENT
        assert event.data["text"] == "hi"

    def test_to_dict(self):
        from adelie.a2a.types import A2ATask
        task = A2ATask(prompt="test", task_id="abc123")
        d = task.to_dict()
        assert d["task_id"] == "abc123"
        assert d["prompt"] == "test"
        assert d["state"] == "submitted"
        assert d["event_count"] == 0


class TestA2AEvent:
    def test_create_event(self):
        from adelie.a2a.types import A2AEvent, EventType
        event = A2AEvent(event_type=EventType.THOUGHT, task_id="xyz")
        assert event.event_type == EventType.THOUGHT
        assert event.task_id == "xyz"


# ── Persistence Tests ────────────────────────────────────────────────────────


class TestTaskStore:
    def test_save_and_load(self, tmp_path):
        from adelie.a2a.persistence import TaskStore
        from adelie.a2a.types import A2ATask
        store = TaskStore(store_dir=tmp_path / "tasks")
        task = A2ATask(task_id="test1", prompt="hello")
        store.save(task)

        loaded = store.load("test1")
        assert loaded is not None
        assert loaded.task_id == "test1"
        assert loaded.prompt == "hello"

    def test_load_nonexistent(self, tmp_path):
        from adelie.a2a.persistence import TaskStore
        store = TaskStore(store_dir=tmp_path / "tasks")
        assert store.load("nope") is None

    def test_delete(self, tmp_path):
        from adelie.a2a.persistence import TaskStore
        from adelie.a2a.types import A2ATask
        store = TaskStore(store_dir=tmp_path / "tasks")
        store.save(A2ATask(task_id="del1", prompt="bye"))
        assert store.delete("del1")
        assert store.load("del1") is None

    def test_delete_nonexistent(self, tmp_path):
        from adelie.a2a.persistence import TaskStore
        store = TaskStore(store_dir=tmp_path / "tasks")
        assert not store.delete("nope")

    def test_list_tasks(self, tmp_path):
        from adelie.a2a.persistence import TaskStore
        from adelie.a2a.types import A2ATask
        store = TaskStore(store_dir=tmp_path / "tasks")
        store.save(A2ATask(task_id="aaa111", prompt="first"))
        store.save(A2ATask(task_id="bbb222", prompt="second"))
        tasks = store.list_tasks()
        assert len(tasks) == 2

    def test_load_from_disk(self, tmp_path):
        from adelie.a2a.persistence import TaskStore
        from adelie.a2a.types import A2ATask
        store1 = TaskStore(store_dir=tmp_path / "tasks")
        store1.save(A2ATask(task_id="disk1", prompt="persisted"))

        # New store instance (empty cache)
        store2 = TaskStore(store_dir=tmp_path / "tasks")
        loaded = store2.load("disk1")
        assert loaded is not None
        assert loaded.prompt == "persisted"


# ── Server Tests ─────────────────────────────────────────────────────────────


@pytest.fixture
def a2a_server(tmp_path):
    from adelie.a2a.server import A2AServer
    from adelie.a2a.persistence import TaskStore
    store = TaskStore(store_dir=tmp_path / "tasks")
    server = A2AServer(port=0, store=store)

    from http.server import HTTPServer
    from adelie.a2a.server import _make_a2a_handler
    handler = _make_a2a_handler(server)
    http_server = HTTPServer(("127.0.0.1", 0), handler)
    server._server = http_server
    server._port = http_server.server_address[1]
    server._thread = threading.Thread(target=http_server.serve_forever, daemon=True)
    server._thread.start()
    time.sleep(0.1)

    yield server

    http_server.shutdown()


def _get(server, path):
    url = f"http://127.0.0.1:{server._port}{path}"
    with urllib.request.urlopen(url, timeout=5) as resp:
        return json.loads(resp.read())


def _post(server, path, body):
    url = f"http://127.0.0.1:{server._port}{path}"
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())


class TestA2AServerUnit:
    def test_create_task(self, tmp_path):
        from adelie.a2a.server import A2AServer
        from adelie.a2a.persistence import TaskStore
        server = A2AServer(store=TaskStore(store_dir=tmp_path / "t"))
        task = server.create_task("hello")
        assert task.prompt == "hello"

    def test_cancel_task(self, tmp_path):
        from adelie.a2a.server import A2AServer
        from adelie.a2a.persistence import TaskStore
        server = A2AServer(store=TaskStore(store_dir=tmp_path / "t"))
        task = server.create_task("test")
        assert server.cancel_task(task.task_id)
        loaded = server.get_task(task.task_id)
        assert loaded.state.value == "cancelled"

    def test_cancel_nonexistent(self, tmp_path):
        from adelie.a2a.server import A2AServer
        from adelie.a2a.persistence import TaskStore
        server = A2AServer(store=TaskStore(store_dir=tmp_path / "t"))
        assert not server.cancel_task("nope")

    def test_task_handler(self, tmp_path):
        from adelie.a2a.server import A2AServer
        from adelie.a2a.persistence import TaskStore
        received = []
        server = A2AServer(store=TaskStore(store_dir=tmp_path / "t"))
        server.on_task(lambda t: received.append(t))
        server.create_task("handled")
        assert len(received) == 1


class TestA2AServerHTTP:
    def test_create_task(self, a2a_server):
        result = _post(a2a_server, "/a2a/tasks", {"prompt": "hello world"})
        assert result["prompt"] == "hello world"
        assert result["state"] == "submitted"

    def test_create_task_no_prompt(self, a2a_server):
        try:
            _post(a2a_server, "/a2a/tasks", {})
            assert False
        except urllib.error.HTTPError as e:
            assert e.code == 400

    def test_list_tasks(self, a2a_server):
        _post(a2a_server, "/a2a/tasks", {"prompt": "a"})
        _post(a2a_server, "/a2a/tasks", {"prompt": "b"})
        result = _get(a2a_server, "/a2a/tasks")
        assert result["count"] == 2

    def test_get_task(self, a2a_server):
        created = _post(a2a_server, "/a2a/tasks", {"prompt": "get me"})
        result = _get(a2a_server, f"/a2a/tasks/{created['task_id']}")
        assert result["prompt"] == "get me"

    def test_get_nonexistent(self, a2a_server):
        try:
            _get(a2a_server, "/a2a/tasks/000000000000")
        except urllib.error.HTTPError as e:
            assert e.code == 404

    def test_cancel_task(self, a2a_server):
        created = _post(a2a_server, "/a2a/tasks", {"prompt": "cancel me"})
        result = _post(a2a_server, f"/a2a/tasks/{created['task_id']}/cancel", {})
        assert result["ok"] is True

    def test_not_found(self, a2a_server):
        try:
            _get(a2a_server, "/a2a/nonexistent")
        except urllib.error.HTTPError as e:
            assert e.code == 404
