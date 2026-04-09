"""
adelie/phases.py

Project Lifecycle Phase System — Compatibility Shim.

This module previously contained the hardcoded Phase Enum and PHASE_INFO dict.
It now delegates to harness_manager.py, which dynamically loads phase
definitions from harness.json.

All existing imports (Phase, PHASE_INFO, get_phase_prompt, get_phase_label,
get_all_phases) continue to work unchanged.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from adelie.harness_manager import get_manager


# ── Phase Enum (dynamic) ────────────────────────────────────────────────────
# Built from harness.json on first access; refreshed when harness changes.

class Phase(str, Enum):
    """Project lifecycle phases — from idea to autonomous evolution.

    NOTE: This Enum is statically defined for backward compatibility.
    The HarnessManager can create additional dynamic phases beyond these,
    but the base six are always guaranteed to exist.
    """

    INITIAL   = "initial"      # 초기: 문서화, 정보 수집, 로드맵 설계
    MID       = "mid"          # 중기: 프로덕션 구현, 테스트, 코드 고도화
    MID_1     = "mid_1"        # 중기 1기: 실행, 로드맵 체크, 테스트
    MID_2     = "mid_2"        # 중기 2기: 안정화, 최적화, 배포
    LATE      = "late"         # 후기: 유지보수, 새 기능, 로드맵 확장
    EVOLVE    = "evolve"       # 자율 발전: AI가 스스로 판단하여 발전


# ── PHASE_INFO (bridging property) ──────────────────────────────────────────
# Loads from HarnessManager on first access.

class _PhaseInfoProxy(dict):
    """
    A dict-like proxy that loads its data from HarnessManager on first access.
    This ensures backward compatibility: code doing PHASE_INFO.get("mid", {})
    continues to work, but now reads from harness.json.
    """

    _loaded = False

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            try:
                hm = get_manager()
                data = hm.get_phase_info()
                super().clear()
                super().update(data)
                self._loaded = True
            except Exception:
                # If HarnessManager fails (e.g., during import), fall back to empty
                pass

    def __getitem__(self, key: Any) -> Any:
        self._ensure_loaded()
        return super().__getitem__(key)

    def __contains__(self, key: Any) -> bool:
        self._ensure_loaded()
        return super().__contains__(key)

    def get(self, key: Any, default: Any = None) -> Any:
        self._ensure_loaded()
        return super().get(key, default)

    def items(self):
        self._ensure_loaded()
        return super().items()

    def keys(self):
        self._ensure_loaded()
        return super().keys()

    def values(self):
        self._ensure_loaded()
        return super().values()

    def __iter__(self):
        self._ensure_loaded()
        return super().__iter__()

    def __len__(self):
        self._ensure_loaded()
        return super().__len__()

    def __repr__(self):
        self._ensure_loaded()
        return super().__repr__()

    def reload(self) -> None:
        """Force reload from HarnessManager."""
        self._loaded = False
        self._ensure_loaded()


PHASE_INFO: _PhaseInfoProxy = _PhaseInfoProxy()


# ── Public API (delegates to HarnessManager) ────────────────────────────────


def get_phase_prompt(phase: str, agent: str) -> str:
    """
    Get phase-specific prompt directive for an agent.

    Args:
        phase: Phase string value (e.g., "initial")
        agent: "writer" or "expert"

    Returns:
        Phase-specific instruction string to inject into the agent's prompt.
    """
    try:
        hm = get_manager()
        return hm.get_phase_prompt(phase, agent)
    except Exception:
        # Ultimate fallback — shouldn't happen in practice
        return f"\n## Project Phase\n{phase}\n"


def get_phase_label(phase: str) -> str:
    """Get human-readable label for a phase."""
    try:
        hm = get_manager()
        return hm.get_phase_label(phase)
    except Exception:
        return phase


def get_all_phases() -> list[tuple[str, str]]:
    """Return list of (phase_value, label) tuples."""
    try:
        hm = get_manager()
        return hm.get_all_phases()
    except Exception:
        return [(p.value, p.value) for p in Phase]
