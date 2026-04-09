"""
adelie/production_bridge.py

Production CI/CD Bridge — connects the AI harness loop to external
production environments (GitHub Actions, Sentry, Datadog, custom MCP tools).

Collects signals from external services, determines a HealthVerdict
(healthy/degraded/critical), and feeds this back into the orchestrator
to trigger automatic ERROR rollback + hotfix generation when needed.

Integration points:
  - orchestrator.py — polls at cycle start, critical → ERROR + hotfix
  - expert_ai.py — injects health context into Expert prompt
  - hooks.py — emits PRODUCTION_ALERT events
  - mcp_manager.py — discovers MCP servers tagged for production

Usage:
  bridge = get_production_bridge()
  signals = bridge.poll_all()
  verdict = bridge.get_verdict()
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from rich.console import Console

console = Console()
logger = logging.getLogger("adelie.production")


# ── Module-level singleton ───────────────────────────────────────────────────

_bridge_instance: Optional["ProductionBridge"] = None


def get_production_bridge() -> ProductionBridge:
    """Get or create the module-level ProductionBridge singleton."""
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = ProductionBridge()
    return _bridge_instance


def reset_production_bridge() -> None:
    """Reset the singleton (for tests)."""
    global _bridge_instance
    _bridge_instance = None


# ── Data Models ──────────────────────────────────────────────────────────────


class HealthVerdict(str, Enum):
    """Production environment health status."""
    HEALTHY = "healthy"      # All services normal
    DEGRADED = "degraded"    # Warnings exist (perf issues, flaky tests)
    CRITICAL = "critical"    # Immediate action required (CI failure, error spike)


@dataclass
class ProductionSignal:
    """A single signal collected from an external service."""
    source: str         # "github_actions", "sentry", "datadog", "custom_mcp"
    signal_type: str    # "ci_failure", "error_spike", "latency_alert", etc.
    severity: str       # "info", "warn", "critical"
    title: str          # Human-readable title
    details: str        # Detailed message / error logs
    timestamp: str = ""  # ISO format
    metadata: dict = field(default_factory=dict)  # Source-specific data

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat(timespec="seconds")


# ── Adapter Base ─────────────────────────────────────────────────────────────


class ProductionAdapter:
    """
    Base class for external service adapters.
    Subclasses implement poll() to collect signals from their service.
    """
    name: str = "base"

    def poll(self) -> list[ProductionSignal]:
        """Collect recent signals from this service."""
        raise NotImplementedError

    def is_available(self) -> bool:
        """Check if this adapter can connect to its service."""
        return False

    def get_display_name(self) -> str:
        return self.name


# ── GitHub Actions Adapter ───────────────────────────────────────────────────


class GitHubActionsAdapter(ProductionAdapter):
    """
    Polls GitHub Actions for workflow run statuses.

    Priority: MCP server (if available) → REST API (if GITHUB_TOKEN set) → disabled.
    """
    name = "github_actions"

    def __init__(
        self,
        token: str = "",
        repo: str = "",
        mcp_manager: Any = None,
    ):
        self._token = token
        self._repo = repo  # "owner/repo"
        self._mcp_manager = mcp_manager

    def is_available(self) -> bool:
        # Available if we have a token + repo, or an MCP server
        if self._token and self._repo:
            return True
        if self._mcp_manager and self._has_mcp_github():
            return True
        return False

    def poll(self) -> list[ProductionSignal]:
        """Poll GitHub Actions for recent workflow run failures."""
        signals: list[ProductionSignal] = []

        # Try MCP first
        if self._mcp_manager and self._has_mcp_github():
            return self._poll_via_mcp()

        # Fallback to REST API
        if self._token and self._repo:
            return self._poll_via_api()

        return signals

    def _has_mcp_github(self) -> bool:
        """Check if a GitHub MCP server is connected."""
        try:
            tools = self._mcp_manager.get_all_tools()
            return any("github" in t.server_name.lower() for t in tools)
        except Exception:
            return False

    def _poll_via_mcp(self) -> list[ProductionSignal]:
        """Poll via MCP GitHub server."""
        signals: list[ProductionSignal] = []
        try:
            # Try calling the GitHub MCP server's list_runs or similar tool
            result = self._mcp_manager.call_tool_by_qualified_name(
                "mcp_github_list_workflow_runs",
                {"repo": self._repo, "per_page": 5},
            )
            if isinstance(result, dict) and "error" not in result:
                runs = result.get("content", [])
                for run_data in runs:
                    text = run_data.get("text", "") if isinstance(run_data, dict) else str(run_data)
                    if "failure" in text.lower() or "failed" in text.lower():
                        signals.append(ProductionSignal(
                            source="github_actions",
                            signal_type="ci_failure",
                            severity="critical",
                            title="CI Workflow Failed (via MCP)",
                            details=text[:500],
                            metadata={"via": "mcp"},
                        ))
        except Exception as e:
            logger.debug(f"GitHub MCP poll failed: {e}")
        return signals

    def _poll_via_api(self) -> list[ProductionSignal]:
        """Poll via GitHub REST API."""
        signals: list[ProductionSignal] = []
        try:
            url = f"https://api.github.com/repos/{self._repo}/actions/runs?per_page=5&status=completed"
            req = urllib.request.Request(url, headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "adelie-ai",
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            for run in data.get("workflow_runs", []):
                conclusion = run.get("conclusion", "")
                if conclusion == "failure":
                    signals.append(ProductionSignal(
                        source="github_actions",
                        signal_type="ci_failure",
                        severity="critical",
                        title=f"CI Failed: {run.get('name', 'unknown')}",
                        details=(
                            f"Workflow: {run.get('name', '')}\n"
                            f"Branch: {run.get('head_branch', '')}\n"
                            f"Commit: {run.get('head_sha', '')[:8]}\n"
                            f"URL: {run.get('html_url', '')}"
                        ),
                        metadata={
                            "run_id": run.get("id"),
                            "workflow_name": run.get("name", ""),
                            "branch": run.get("head_branch", ""),
                            "commit_sha": run.get("head_sha", ""),
                            "html_url": run.get("html_url", ""),
                        },
                    ))
                elif conclusion == "success":
                    signals.append(ProductionSignal(
                        source="github_actions",
                        signal_type="ci_success",
                        severity="info",
                        title=f"CI Passed: {run.get('name', '')}",
                        details="",
                        metadata={"run_id": run.get("id")},
                    ))
        except urllib.error.HTTPError as e:
            logger.warning(f"GitHub API error: {e.code} {e.reason}")
        except Exception as e:
            logger.debug(f"GitHub API poll failed: {e}")

        return signals


# ── Sentry Adapter ───────────────────────────────────────────────────────────


class SentryAdapter(ProductionAdapter):
    """
    Polls Sentry for recent error issues and spikes.

    Priority: MCP server → REST API (SENTRY_AUTH_TOKEN) → disabled.
    """
    name = "sentry"

    def __init__(
        self,
        auth_token: str = "",
        org: str = "",
        project: str = "",
        mcp_manager: Any = None,
        error_threshold: int = 10,
    ):
        self._auth_token = auth_token
        self._org = org
        self._project = project
        self._mcp_manager = mcp_manager
        self._error_threshold = error_threshold  # Errors/5min for critical

    def is_available(self) -> bool:
        if self._auth_token and self._org and self._project:
            return True
        if self._mcp_manager and self._has_mcp_sentry():
            return True
        return False

    def poll(self) -> list[ProductionSignal]:
        signals: list[ProductionSignal] = []

        if self._mcp_manager and self._has_mcp_sentry():
            return self._poll_via_mcp()

        if self._auth_token and self._org and self._project:
            return self._poll_via_api()

        return signals

    def _has_mcp_sentry(self) -> bool:
        try:
            tools = self._mcp_manager.get_all_tools()
            return any("sentry" in t.server_name.lower() for t in tools)
        except Exception:
            return False

    def _poll_via_mcp(self) -> list[ProductionSignal]:
        signals: list[ProductionSignal] = []
        try:
            result = self._mcp_manager.call_tool_by_qualified_name(
                "mcp_sentry_get_recent_issues",
                {"project": self._project, "limit": 5},
            )
            if isinstance(result, dict) and "error" not in result:
                content = result.get("content", [])
                for item in content:
                    text = item.get("text", "") if isinstance(item, dict) else str(item)
                    signals.append(ProductionSignal(
                        source="sentry",
                        signal_type="error_spike",
                        severity="warn",
                        title="Sentry Issue (via MCP)",
                        details=text[:500],
                        metadata={"via": "mcp"},
                    ))
        except Exception as e:
            logger.debug(f"Sentry MCP poll failed: {e}")
        return signals

    def _poll_via_api(self) -> list[ProductionSignal]:
        signals: list[ProductionSignal] = []
        try:
            url = (
                f"https://sentry.io/api/0/projects/{self._org}/{self._project}"
                f"/issues/?query=is:unresolved&sort=date&limit=5"
            )
            req = urllib.request.Request(url, headers={
                "Authorization": f"Bearer {self._auth_token}",
                "Content-Type": "application/json",
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                issues = json.loads(resp.read().decode("utf-8"))

            for issue in issues:
                count = int(issue.get("count", "0"))
                title = issue.get("title", "Unknown error")

                if count >= self._error_threshold:
                    severity = "critical"
                    signal_type = "error_spike"
                elif count >= self._error_threshold // 2:
                    severity = "warn"
                    signal_type = "error_increase"
                else:
                    severity = "info"
                    signal_type = "new_error"

                signals.append(ProductionSignal(
                    source="sentry",
                    signal_type=signal_type,
                    severity=severity,
                    title=f"Sentry: {title}",
                    details=(
                        f"Count: {count}\n"
                        f"First seen: {issue.get('firstSeen', '')}\n"
                        f"Last seen: {issue.get('lastSeen', '')}\n"
                        f"URL: {issue.get('permalink', '')}"
                    ),
                    metadata={
                        "issue_id": issue.get("id"),
                        "count": count,
                        "permalink": issue.get("permalink", ""),
                    },
                ))
        except urllib.error.HTTPError as e:
            logger.warning(f"Sentry API error: {e.code} {e.reason}")
        except Exception as e:
            logger.debug(f"Sentry API poll failed: {e}")

        return signals


# ── Custom MCP Adapter ───────────────────────────────────────────────────────


class CustomMcpAdapter(ProductionAdapter):
    """
    Discovers and polls MCP servers tagged for production monitoring.

    Looks for MCP tools that match production-related patterns
    (e.g., tools containing "monitor", "health", "status", "alert").
    """
    name = "custom_mcp"

    _PRODUCTION_PATTERNS = ["monitor", "health", "status", "alert", "check", "diagnose"]

    def __init__(self, mcp_manager: Any = None):
        self._mcp_manager = mcp_manager

    def is_available(self) -> bool:
        if not self._mcp_manager:
            return False
        return len(self._find_production_tools()) > 0

    def poll(self) -> list[ProductionSignal]:
        signals: list[ProductionSignal] = []
        if not self._mcp_manager:
            return signals

        for tool in self._find_production_tools():
            try:
                result = self._mcp_manager.call_tool_by_qualified_name(
                    tool.qualified_name, {},
                )
                if isinstance(result, dict) and "error" not in result:
                    text = ""
                    content = result.get("content", [])
                    for item in content:
                        if isinstance(item, dict):
                            text += item.get("text", "")
                        else:
                            text += str(item)

                    if text:
                        severity = "info"
                        if any(w in text.lower() for w in ["error", "fail", "critical", "down"]):
                            severity = "critical"
                        elif any(w in text.lower() for w in ["warn", "slow", "degraded"]):
                            severity = "warn"

                        signals.append(ProductionSignal(
                            source="custom_mcp",
                            signal_type="mcp_check",
                            severity=severity,
                            title=f"MCP: {tool.name}",
                            details=text[:500],
                            metadata={
                                "server": tool.server_name,
                                "tool": tool.name,
                            },
                        ))
            except Exception as e:
                logger.debug(f"Custom MCP tool {tool.name} failed: {e}")

        return signals

    def _find_production_tools(self) -> list:
        """Find MCP tools that look production-related."""
        try:
            all_tools = self._mcp_manager.get_all_tools()
            return [
                t for t in all_tools
                if any(p in t.name.lower() for p in self._PRODUCTION_PATTERNS)
                or any(p in t.description.lower() for p in self._PRODUCTION_PATTERNS)
            ]
        except Exception:
            return []


# ── Signal Collector ─────────────────────────────────────────────────────────


class SignalCollector:
    """
    Collects signals from all registered adapters and determines
    the production HealthVerdict.
    """

    def __init__(self, poll_interval: int = 60):
        self._adapters: list[ProductionAdapter] = []
        self._recent_signals: deque[ProductionSignal] = deque(maxlen=50)
        self._last_poll: float = 0
        self.poll_interval = poll_interval  # seconds

    def register_adapter(self, adapter: ProductionAdapter) -> None:
        """Register an adapter if it's available."""
        if adapter.is_available():
            self._adapters.append(adapter)
            logger.info(f"Production adapter registered: {adapter.name}")

    @property
    def adapter_count(self) -> int:
        return len(self._adapters)

    @property
    def adapter_names(self) -> list[str]:
        return [a.name for a in self._adapters]

    def poll_all(self, force: bool = False) -> list[ProductionSignal]:
        """
        Collect signals from all adapters (rate-limited).

        Args:
            force: If True, ignore rate limiting.

        Returns:
            List of new signals collected in this poll.
        """
        now = time.time()
        if not force and (now - self._last_poll) < self.poll_interval:
            return []  # Too soon

        if not self._adapters:
            return []

        new_signals: list[ProductionSignal] = []

        for adapter in self._adapters:
            try:
                signals = adapter.poll()
                new_signals.extend(signals)
            except Exception as e:
                logger.warning(f"Adapter {adapter.name} poll failed: {e}")

        self._recent_signals.extend(new_signals)
        self._last_poll = now

        if new_signals:
            critical_count = sum(1 for s in new_signals if s.severity == "critical")
            warn_count = sum(1 for s in new_signals if s.severity == "warn")
            if critical_count or warn_count:
                console.print(
                    f"[dim]📡 Production Bridge: {len(new_signals)} signal(s) "
                    f"({critical_count} critical, {warn_count} warn)[/dim]"
                )

        return new_signals

    def get_verdict(self) -> HealthVerdict:
        """Determine production health based on recent signals."""
        if not self._recent_signals:
            return HealthVerdict.HEALTHY

        # Check for any critical signals in recent history
        critical = [s for s in self._recent_signals if s.severity == "critical"]
        warnings = [s for s in self._recent_signals if s.severity == "warn"]

        if critical:
            return HealthVerdict.CRITICAL
        if warnings:
            return HealthVerdict.DEGRADED
        return HealthVerdict.HEALTHY

    def get_critical_signals(self) -> list[ProductionSignal]:
        """Get only critical signals from recent history."""
        return [s for s in self._recent_signals if s.severity == "critical"]

    def get_context_summary(self) -> str:
        """
        Generate a context summary for injection into Expert AI prompt.
        Returns empty string if healthy.
        """
        verdict = self.get_verdict()
        if verdict == HealthVerdict.HEALTHY and not self._recent_signals:
            return ""

        lines = [
            "## Production Health",
            f"Status: **{verdict.value.upper()}**",
            f"Active adapters: {', '.join(self.adapter_names) or 'none'}",
        ]

        # Group signals by severity
        critical = [s for s in self._recent_signals if s.severity == "critical"]
        warnings = [s for s in self._recent_signals if s.severity == "warn"]
        info = [s for s in self._recent_signals if s.severity == "info"]

        if critical:
            lines.append("\n### ⛔ Critical Alerts")
            for s in critical[:5]:
                lines.append(f"- [{s.source}] {s.title}")
                if s.details:
                    # Include first 2 lines of details
                    detail_lines = s.details.strip().splitlines()[:2]
                    for dl in detail_lines:
                        lines.append(f"  {dl}")

        if warnings:
            lines.append("\n### ⚠️ Warnings")
            for s in warnings[:5]:
                lines.append(f"- [{s.source}] {s.title}")

        if info and not critical and not warnings:
            lines.append("\n### ℹ️ Info")
            for s in info[:3]:
                lines.append(f"- [{s.source}] {s.title}")

        if verdict == HealthVerdict.CRITICAL:
            lines.append(
                "\n**URGENT**: Address critical production issues before new features."
            )
        elif verdict == HealthVerdict.DEGRADED:
            lines.append(
                "\n**NOTE**: Consider addressing production warnings in upcoming work."
            )

        return "\n".join(lines)

    def clear_signals(self) -> None:
        """Clear all collected signals (e.g., after resolution)."""
        self._recent_signals.clear()

    def acknowledge_critical(self) -> int:
        """
        Downgrade critical signals to 'warn' (acknowledged but not resolved).
        Returns count of acknowledged signals.
        """
        count = 0
        updated: deque[ProductionSignal] = deque(maxlen=50)
        for s in self._recent_signals:
            if s.severity == "critical":
                s.severity = "warn"
                count += 1
            updated.append(s)
        self._recent_signals = updated
        return count


# ── Production Bridge ────────────────────────────────────────────────────────


class ProductionBridge:
    """
    Main entry point for production CI/CD integration.

    Lazily initializes adapters from environment config and MCP.
    Provides poll_all(), get_verdict(), and get_context_summary()
    for orchestrator consumption.
    """

    def __init__(self):
        self._collector: SignalCollector | None = None
        self._initialized = False

    def _ensure_init(self) -> SignalCollector:
        """Lazy initialization of collector + adapters."""
        if self._collector is not None:
            return self._collector

        # Load config
        try:
            import os
            poll_interval = int(os.getenv("PRODUCTION_POLL_INTERVAL", "60"))
        except Exception:
            poll_interval = 60

        self._collector = SignalCollector(poll_interval=poll_interval)

        # Try to get MCP manager
        mcp_mgr = None
        try:
            from adelie.config import MCP_ENABLED
            if MCP_ENABLED:
                from adelie.tool_registry import get_registry
                registry = get_registry()
                mcp_mgr = getattr(registry, "_mcp_manager", None)
        except Exception:
            pass

        # Register adapters based on available configuration
        import os

        # GitHub Actions
        gh_token = os.getenv("GITHUB_TOKEN", "")
        gh_repo = os.getenv("GITHUB_REPO", "")
        if not gh_repo:
            # Try to detect from .git/config
            gh_repo = self._detect_github_repo()
        gh_adapter = GitHubActionsAdapter(
            token=gh_token, repo=gh_repo, mcp_manager=mcp_mgr,
        )
        self._collector.register_adapter(gh_adapter)

        # Sentry
        sentry_token = os.getenv("SENTRY_AUTH_TOKEN", "")
        sentry_org = os.getenv("SENTRY_ORG", "")
        sentry_project = os.getenv("SENTRY_PROJECT", "")
        sentry_adapter = SentryAdapter(
            auth_token=sentry_token,
            org=sentry_org,
            project=sentry_project,
            mcp_manager=mcp_mgr,
        )
        self._collector.register_adapter(sentry_adapter)

        # Custom MCP
        custom_adapter = CustomMcpAdapter(mcp_manager=mcp_mgr)
        self._collector.register_adapter(custom_adapter)

        self._initialized = True
        adapters = self._collector.adapter_names
        if adapters:
            console.print(
                f"[dim]📡 Production Bridge: {len(adapters)} adapter(s) active "
                f"({', '.join(adapters)})[/dim]"
            )

        return self._collector

    def _detect_github_repo(self) -> str:
        """Try to detect GitHub repo from .git/config or remote."""
        try:
            import subprocess
            result = subprocess.run(
                ["git", "config", "--get", "remote.origin.url"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                url = result.stdout.strip()
                # Parse: git@github.com:owner/repo.git or https://github.com/owner/repo.git
                if "github.com" in url:
                    if url.startswith("git@"):
                        # git@github.com:owner/repo.git
                        path = url.split(":")[-1]
                    else:
                        # https://github.com/owner/repo.git
                        path = "/".join(url.split("/")[-2:])
                    return path.replace(".git", "")
        except Exception:
            pass
        return ""

    # ── Public API ───────────────────────────────────────────────────────

    @property
    def is_enabled(self) -> bool:
        """Check if the production bridge is enabled via config."""
        try:
            import os
            return os.getenv("PRODUCTION_BRIDGE_ENABLED", "false").lower() in ("true", "1", "yes")
        except Exception:
            return False

    @property
    def has_adapters(self) -> bool:
        """Check if any adapters are registered."""
        if self._collector is None:
            return False
        return self._collector.adapter_count > 0

    def poll_all(self, force: bool = False) -> list[ProductionSignal]:
        """Poll all adapters for new signals."""
        if not self.is_enabled:
            return []
        collector = self._ensure_init()
        return collector.poll_all(force=force)

    def get_verdict(self) -> HealthVerdict:
        """Get current production health verdict."""
        if not self.is_enabled:
            return HealthVerdict.HEALTHY
        collector = self._ensure_init()
        return collector.get_verdict()

    def get_context_summary(self) -> str:
        """Get context summary for Expert AI prompt injection."""
        if not self.is_enabled:
            return ""
        collector = self._ensure_init()
        return collector.get_context_summary()

    def get_critical_signals(self) -> list[ProductionSignal]:
        """Get critical signals for hotfix generation."""
        if not self.is_enabled:
            return []
        collector = self._ensure_init()
        return collector.get_critical_signals()

    def acknowledge_critical(self) -> int:
        """Acknowledge critical signals (downgrade to warn)."""
        if self._collector:
            return self._collector.acknowledge_critical()
        return 0

    def clear_signals(self) -> None:
        """Clear all signals."""
        if self._collector:
            self._collector.clear_signals()

    def get_stats(self) -> dict:
        """Get bridge statistics for monitoring."""
        if self._collector is None:
            return {
                "enabled": self.is_enabled,
                "initialized": False,
                "adapters": [],
                "signal_count": 0,
                "verdict": "healthy",
            }
        return {
            "enabled": self.is_enabled,
            "initialized": self._initialized,
            "adapters": self._collector.adapter_names,
            "signal_count": len(self._collector._recent_signals),
            "verdict": self._collector.get_verdict().value,
        }
