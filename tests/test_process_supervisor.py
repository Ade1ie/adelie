"""tests/test_process_supervisor.py — Tests for process supervisor."""
from __future__ import annotations

import time
import pytest
from adelie.process_supervisor import ProcessSupervisor, ProcessStatus


class TestProcessSupervisor:
    def test_spawn_and_complete(self):
        supervisor = ProcessSupervisor()
        proc = supervisor.spawn("test_echo", "echo hello", timeout=10)
        assert proc is not None
        assert proc.name == "test_echo"
        # Wait for it to finish
        time.sleep(0.5)
        changed = supervisor.check_all()
        assert len(changed) >= 1
        assert changed[0].status == ProcessStatus.COMPLETED
        assert changed[0].exit_code == 0

    def test_spawn_respects_max_concurrent(self):
        supervisor = ProcessSupervisor(max_concurrent=1)
        p1 = supervisor.spawn("long1", "sleep 10", timeout=30)
        assert p1 is not None
        p2 = supervisor.spawn("long2", "sleep 10", timeout=30)
        assert p2 is None  # Should be rejected
        supervisor.shutdown()

    def test_timeout_kills_process(self):
        supervisor = ProcessSupervisor()
        proc = supervisor.spawn("sleeper", "sleep 60", timeout=1)
        assert proc is not None
        time.sleep(1.5)
        changed = supervisor.check_all()
        assert any(p.status == ProcessStatus.TIMEOUT for p in changed)

    def test_shutdown_kills_all(self):
        supervisor = ProcessSupervisor()
        supervisor.spawn("s1", "sleep 60", timeout=300)
        supervisor.spawn("s2", "sleep 60", timeout=300)
        killed = supervisor.shutdown()
        assert killed == 2
        assert supervisor.active_count == 0

    def test_get_status(self):
        supervisor = ProcessSupervisor()
        supervisor.spawn("test", "echo hi", timeout=10)
        time.sleep(0.3)
        supervisor.check_all()
        status = supervisor.get_status()
        assert "active_count" in status
        assert "total_spawned" in status

    def test_failed_command(self):
        supervisor = ProcessSupervisor()
        proc = supervisor.spawn("bad", "exit 1", timeout=10)
        assert proc is not None
        time.sleep(0.5)
        changed = supervisor.check_all()
        assert len(changed) >= 1
        assert changed[0].status == ProcessStatus.FAILED
        assert changed[0].exit_code == 1


class TestNoOutputTimeout:
    def test_no_output_timeout_kills_silent_process(self):
        """Process producing no output should be killed after no_output_timeout."""
        supervisor = ProcessSupervisor()
        # sleep produces no output
        proc = supervisor.spawn("silent", "sleep 60", timeout=300, no_output_timeout=1)
        assert proc is not None
        time.sleep(1.5)
        changed = supervisor.check_all()
        assert any(p.status == ProcessStatus.NO_OUTPUT_TIMEOUT for p in changed)
        supervisor.shutdown()

    def test_no_output_timeout_disabled_by_default(self):
        """With no_output_timeout=0, the process should not be killed for silence."""
        supervisor = ProcessSupervisor()
        proc = supervisor.spawn("silent", "sleep 60", timeout=300, no_output_timeout=0)
        assert proc is not None
        assert not proc.no_output_timed_out
        time.sleep(0.5)
        changed = supervisor.check_all()
        assert not any(p.status == ProcessStatus.NO_OUTPUT_TIMEOUT for p in changed)
        supervisor.shutdown()


class TestCancelScope:
    def test_cancel_scope_kills_group(self):
        """cancel_scope should kill all processes with matching scope_key."""
        supervisor = ProcessSupervisor()
        supervisor.spawn("build1", "sleep 60", timeout=300, scope_key="build")
        supervisor.spawn("build2", "sleep 60", timeout=300, scope_key="build")
        supervisor.spawn("test1", "sleep 60", timeout=300, scope_key="test")

        killed = supervisor.cancel_scope("build")
        assert killed == 2
        # test1 should still be running
        assert supervisor.active_count == 1
        supervisor.shutdown()

    def test_cancel_scope_empty_key_noop(self):
        """Empty scope key should not kill anything."""
        supervisor = ProcessSupervisor()
        supervisor.spawn("p1", "sleep 60", timeout=300, scope_key="build")
        killed = supervisor.cancel_scope("")
        assert killed == 0
        assert supervisor.active_count == 1
        supervisor.shutdown()

    def test_cancel_scope_nonexistent_key(self):
        """Non-existent scope key should not kill anything."""
        supervisor = ProcessSupervisor()
        supervisor.spawn("p1", "sleep 60", timeout=300, scope_key="build")
        killed = supervisor.cancel_scope("deploy")
        assert killed == 0
        assert supervisor.active_count == 1
        supervisor.shutdown()
