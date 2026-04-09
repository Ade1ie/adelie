"""
tests/test_production_bridge.py

Tests for the Production Bridge — CI/CD integration harness.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── Data Model Tests ─────────────────────────────────────────────────────────


class TestProductionSignal:
    def test_auto_timestamp(self):
        from adelie.production_bridge import ProductionSignal
        s = ProductionSignal(
            source="test", signal_type="ci_failure",
            severity="critical", title="Test", details="",
        )
        assert s.timestamp  # Auto-filled

    def test_explicit_timestamp(self):
        from adelie.production_bridge import ProductionSignal
        s = ProductionSignal(
            source="test", signal_type="ci_failure",
            severity="critical", title="Test", details="",
            timestamp="2026-01-01T00:00:00",
        )
        assert s.timestamp == "2026-01-01T00:00:00"

    def test_metadata_default(self):
        from adelie.production_bridge import ProductionSignal
        s = ProductionSignal(
            source="test", signal_type="info",
            severity="info", title="Test", details="",
        )
        assert s.metadata == {}


class TestHealthVerdict:
    def test_values(self):
        from adelie.production_bridge import HealthVerdict
        assert HealthVerdict.HEALTHY == "healthy"
        assert HealthVerdict.DEGRADED == "degraded"
        assert HealthVerdict.CRITICAL == "critical"


# ── Adapter Tests ────────────────────────────────────────────────────────────


class TestGitHubActionsAdapter:
    def test_not_available_without_config(self):
        from adelie.production_bridge import GitHubActionsAdapter
        adapter = GitHubActionsAdapter()
        assert not adapter.is_available()

    def test_available_with_token_and_repo(self):
        from adelie.production_bridge import GitHubActionsAdapter
        adapter = GitHubActionsAdapter(token="ghp_test", repo="owner/repo")
        assert adapter.is_available()

    def test_available_with_mcp(self):
        from adelie.production_bridge import GitHubActionsAdapter
        mock_mgr = MagicMock()
        mock_tool = MagicMock()
        mock_tool.server_name = "github"
        mock_mgr.get_all_tools.return_value = [mock_tool]
        adapter = GitHubActionsAdapter(mcp_manager=mock_mgr)
        assert adapter.is_available()

    def test_poll_empty_without_config(self):
        from adelie.production_bridge import GitHubActionsAdapter
        adapter = GitHubActionsAdapter()
        assert adapter.poll() == []

    def test_poll_via_api_success(self):
        from adelie.production_bridge import GitHubActionsAdapter
        adapter = GitHubActionsAdapter(token="ghp_test", repo="owner/repo")

        # Mock the API response
        mock_response = json.dumps({
            "workflow_runs": [
                {
                    "conclusion": "failure",
                    "name": "CI",
                    "head_branch": "main",
                    "head_sha": "abc12345",
                    "html_url": "https://github.com/owner/repo/actions/runs/1",
                    "id": 1,
                },
                {
                    "conclusion": "success",
                    "name": "Deploy",
                    "id": 2,
                },
            ]
        }).encode("utf-8")

        mock_resp = MagicMock()
        mock_resp.read.return_value = mock_response
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            signals = adapter.poll()

        assert len(signals) == 2
        critical = [s for s in signals if s.severity == "critical"]
        assert len(critical) == 1
        assert "CI" in critical[0].title

    def test_poll_via_api_network_error(self):
        from adelie.production_bridge import GitHubActionsAdapter
        adapter = GitHubActionsAdapter(token="ghp_test", repo="owner/repo")

        with patch("urllib.request.urlopen", side_effect=Exception("timeout")):
            signals = adapter.poll()

        assert signals == []  # Graceful failure


class TestSentryAdapter:
    def test_not_available_without_config(self):
        from adelie.production_bridge import SentryAdapter
        adapter = SentryAdapter()
        assert not adapter.is_available()

    def test_available_with_full_config(self):
        from adelie.production_bridge import SentryAdapter
        adapter = SentryAdapter(
            auth_token="sntrys_test", org="my-org", project="my-proj",
        )
        assert adapter.is_available()

    def test_poll_via_api_error_spike(self):
        from adelie.production_bridge import SentryAdapter
        adapter = SentryAdapter(
            auth_token="sntrys_test", org="my-org", project="my-proj",
            error_threshold=10,
        )

        mock_response = json.dumps([
            {
                "title": "TypeError: Cannot read property 'x' of undefined",
                "count": "25",
                "firstSeen": "2026-01-01T00:00:00Z",
                "lastSeen": "2026-01-01T01:00:00Z",
                "permalink": "https://sentry.io/issues/1",
                "id": "1",
            },
            {
                "title": "TimeoutError: request timeout",
                "count": "3",
                "firstSeen": "2026-01-01T00:00:00Z",
                "lastSeen": "2026-01-01T01:00:00Z",
                "permalink": "https://sentry.io/issues/2",
                "id": "2",
            },
        ]).encode("utf-8")

        mock_resp = MagicMock()
        mock_resp.read.return_value = mock_response
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            signals = adapter.poll()

        assert len(signals) == 2
        critical = [s for s in signals if s.severity == "critical"]
        assert len(critical) == 1  # count=25 >= threshold=10
        assert "TypeError" in critical[0].title


class TestCustomMcpAdapter:
    def test_not_available_without_mcp(self):
        from adelie.production_bridge import CustomMcpAdapter
        adapter = CustomMcpAdapter()
        assert not adapter.is_available()

    def test_finds_production_tools(self):
        from adelie.production_bridge import CustomMcpAdapter
        mock_mgr = MagicMock()
        mock_tool = MagicMock()
        mock_tool.name = "health_check"
        mock_tool.description = "Check service health"
        mock_tool.server_name = "monitor"
        mock_tool.qualified_name = "mcp_monitor_health_check"
        mock_mgr.get_all_tools.return_value = [mock_tool]

        adapter = CustomMcpAdapter(mcp_manager=mock_mgr)
        assert adapter.is_available()

    def test_ignores_non_production_tools(self):
        from adelie.production_bridge import CustomMcpAdapter
        mock_mgr = MagicMock()
        mock_tool = MagicMock()
        mock_tool.name = "format_code"
        mock_tool.description = "Format source code"
        mock_mgr.get_all_tools.return_value = [mock_tool]

        adapter = CustomMcpAdapter(mcp_manager=mock_mgr)
        assert not adapter.is_available()


# ── Signal Collector Tests ───────────────────────────────────────────────────


class TestSignalCollector:
    def test_empty_healthy(self):
        from adelie.production_bridge import SignalCollector, HealthVerdict
        collector = SignalCollector()
        assert collector.get_verdict() == HealthVerdict.HEALTHY

    def test_poll_rate_limiting(self):
        from adelie.production_bridge import SignalCollector
        collector = SignalCollector(poll_interval=60)
        collector._last_poll = time.time()  # Just polled

        # Should return empty due to rate limiting
        result = collector.poll_all()
        assert result == []

    def test_poll_force_bypasses_rate_limit(self):
        from adelie.production_bridge import SignalCollector, ProductionSignal
        collector = SignalCollector(poll_interval=60)
        collector._last_poll = time.time()  # Just polled

        # Add a mock adapter
        mock_adapter = MagicMock()
        mock_adapter.is_available.return_value = True
        mock_adapter.name = "test"
        mock_adapter.poll.return_value = [
            ProductionSignal(
                source="test", signal_type="info",
                severity="info", title="Test", details="",
            )
        ]
        collector._adapters = [mock_adapter]

        result = collector.poll_all(force=True)
        assert len(result) == 1

    def test_verdict_critical(self):
        from adelie.production_bridge import SignalCollector, ProductionSignal, HealthVerdict
        collector = SignalCollector()
        collector._recent_signals.append(ProductionSignal(
            source="github", signal_type="ci_failure",
            severity="critical", title="CI Failed", details="",
        ))
        assert collector.get_verdict() == HealthVerdict.CRITICAL

    def test_verdict_degraded(self):
        from adelie.production_bridge import SignalCollector, ProductionSignal, HealthVerdict
        collector = SignalCollector()
        collector._recent_signals.append(ProductionSignal(
            source="sentry", signal_type="error_increase",
            severity="warn", title="Errors up", details="",
        ))
        assert collector.get_verdict() == HealthVerdict.DEGRADED

    def test_verdict_healthy_with_info_only(self):
        from adelie.production_bridge import SignalCollector, ProductionSignal, HealthVerdict
        collector = SignalCollector()
        collector._recent_signals.append(ProductionSignal(
            source="github", signal_type="ci_success",
            severity="info", title="CI Passed", details="",
        ))
        assert collector.get_verdict() == HealthVerdict.HEALTHY

    def test_context_summary_empty_when_healthy(self):
        from adelie.production_bridge import SignalCollector
        collector = SignalCollector()
        assert collector.get_context_summary() == ""

    def test_context_summary_critical(self):
        from adelie.production_bridge import SignalCollector, ProductionSignal
        collector = SignalCollector()
        collector._recent_signals.append(ProductionSignal(
            source="github_actions", signal_type="ci_failure",
            severity="critical", title="CI Build Failed on main",
            details="Error in test_auth.py: AssertionError",
        ))
        summary = collector.get_context_summary()
        assert "CRITICAL" in summary
        assert "CI Build Failed" in summary
        assert "URGENT" in summary

    def test_context_summary_degraded(self):
        from adelie.production_bridge import SignalCollector, ProductionSignal
        collector = SignalCollector()
        collector._recent_signals.append(ProductionSignal(
            source="sentry", signal_type="warn",
            severity="warn", title="Error rate increasing",
            details="15 new errors",
        ))
        summary = collector.get_context_summary()
        assert "DEGRADED" in summary
        assert "Warnings" in summary

    def test_acknowledge_critical(self):
        from adelie.production_bridge import SignalCollector, ProductionSignal, HealthVerdict
        collector = SignalCollector()
        collector._recent_signals.append(ProductionSignal(
            source="test", signal_type="ci_failure",
            severity="critical", title="CI Failed", details="",
        ))
        assert collector.get_verdict() == HealthVerdict.CRITICAL

        count = collector.acknowledge_critical()
        assert count == 1
        assert collector.get_verdict() == HealthVerdict.DEGRADED  # Downgraded to warn

    def test_clear_signals(self):
        from adelie.production_bridge import SignalCollector, ProductionSignal, HealthVerdict
        collector = SignalCollector()
        collector._recent_signals.append(ProductionSignal(
            source="test", signal_type="ci_failure",
            severity="critical", title="Test", details="",
        ))
        collector.clear_signals()
        assert collector.get_verdict() == HealthVerdict.HEALTHY

    def test_get_critical_signals(self):
        from adelie.production_bridge import SignalCollector, ProductionSignal
        collector = SignalCollector()
        collector._recent_signals.append(ProductionSignal(
            source="a", signal_type="ci_failure",
            severity="critical", title="Critical", details="",
        ))
        collector._recent_signals.append(ProductionSignal(
            source="b", signal_type="warn",
            severity="warn", title="Warning", details="",
        ))
        criticals = collector.get_critical_signals()
        assert len(criticals) == 1
        assert criticals[0].title == "Critical"

    def test_register_unavailable_adapter(self):
        from adelie.production_bridge import SignalCollector
        mock_adapter = MagicMock()
        mock_adapter.is_available.return_value = False
        collector = SignalCollector()
        collector.register_adapter(mock_adapter)
        assert collector.adapter_count == 0

    def test_register_available_adapter(self):
        from adelie.production_bridge import SignalCollector
        mock_adapter = MagicMock()
        mock_adapter.is_available.return_value = True
        mock_adapter.name = "test"
        collector = SignalCollector()
        collector.register_adapter(mock_adapter)
        assert collector.adapter_count == 1
        assert "test" in collector.adapter_names


# ── Production Bridge Tests ──────────────────────────────────────────────────


class TestProductionBridge:
    def test_disabled_by_default(self):
        from adelie.production_bridge import ProductionBridge
        bridge = ProductionBridge()
        assert not bridge.is_enabled

    def test_poll_returns_empty_when_disabled(self):
        from adelie.production_bridge import ProductionBridge
        bridge = ProductionBridge()
        assert bridge.poll_all() == []

    def test_verdict_healthy_when_disabled(self):
        from adelie.production_bridge import ProductionBridge, HealthVerdict
        bridge = ProductionBridge()
        assert bridge.get_verdict() == HealthVerdict.HEALTHY

    def test_context_summary_empty_when_disabled(self):
        from adelie.production_bridge import ProductionBridge
        bridge = ProductionBridge()
        assert bridge.get_context_summary() == ""

    def test_get_stats_uninitalized(self):
        from adelie.production_bridge import ProductionBridge
        bridge = ProductionBridge()
        stats = bridge.get_stats()
        assert stats["initialized"] is False
        assert stats["verdict"] == "healthy"

    @patch.dict("os.environ", {"PRODUCTION_BRIDGE_ENABLED": "true"})
    def test_enabled_via_env(self):
        from adelie.production_bridge import ProductionBridge
        bridge = ProductionBridge()
        assert bridge.is_enabled

    def test_detect_github_repo(self):
        from adelie.production_bridge import ProductionBridge
        bridge = ProductionBridge()
        # This may or may not work depending on the test environment
        # but it should not crash
        repo = bridge._detect_github_repo()
        assert isinstance(repo, str)


# ── Singleton Tests ──────────────────────────────────────────────────────────


class TestSingleton:
    def test_reset(self):
        from adelie.production_bridge import (
            get_production_bridge, reset_production_bridge,
        )
        b1 = get_production_bridge()
        reset_production_bridge()
        b2 = get_production_bridge()
        assert b1 is not b2


# ── Integration: HookEvent ───────────────────────────────────────────────────


class TestHookIntegration:
    def test_production_alert_event_exists(self):
        from adelie.hooks import HookEvent
        assert hasattr(HookEvent, "PRODUCTION_ALERT")
        assert HookEvent.PRODUCTION_ALERT == "production_alert"

    def test_hook_fires_on_production_alert(self):
        from adelie.hooks import HookEvent, HookManager
        manager = HookManager()
        received = []

        def handler(event, ctx):
            received.append(ctx)

        manager.register(HookEvent.PRODUCTION_ALERT, handler, name="test")
        manager.emit(HookEvent.PRODUCTION_ALERT, {
            "verdict": "critical",
            "signal_count": 1,
        })

        assert len(received) == 1
        assert received[0]["verdict"] == "critical"
