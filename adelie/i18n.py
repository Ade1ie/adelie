"""
adelie/i18n.py

Minimal internationalization for Adelie CLI messages.
Supports Korean (ko) and English (en).
"""

from __future__ import annotations

import os

_MESSAGES: dict[str, dict[str, str]] = {
    # ── General ──────────────────────────────────────────────────────────
    "init.title":               {"ko": "Adelie — 워크스페이스 초기화",           "en": "Adelie — Initializing workspace"},
    "init.dir":                 {"ko": "디렉터리",                              "en": "Directory"},
    "init.detected":            {"ko": "기존 프로젝트 감지",                     "en": "Detected existing project"},
    "init.name":                {"ko": "이름",                                  "en": "Name"},
    "init.languages":           {"ko": "언어",                                  "en": "Languages"},
    "init.frameworks":          {"ko": "프레임워크",                             "en": "Frameworks"},
    "init.phase_mid":           {"ko": "Phase → 중기 (기존 코드 감지)",          "en": "Phase → mid (existing code detected)"},
    "init.created_ws":          {"ko": ".adelie/ 워크스페이스 구조 생성",         "en": "Created .adelie/ workspace structure"},
    "init.created_env":         {"ko": ".adelie/.env 생성 (LLM 설정)",          "en": "Created .adelie/.env (LLM settings)"},
    "init.created_specs":       {"ko": ".adelie/specs/ 생성 (스펙 파일 위치)",   "en": "Created .adelie/specs/ (spec files)"},
    "init.registered":          {"ko": "글로벌 워크스페이스 목록에 등록",          "en": "Registered in global workspace list"},
    "init.done":                {"ko": "워크스페이스 초기화 완료!",               "en": "Workspace initialized!"},
    "init.already_exists":      {"ko": ".adelie/ 가 이미 존재합니다",            "en": ".adelie/ already exists"},
    "init.use_force":           {"ko": "--force 로 재초기화 가능",               "en": "Use --force to reinitialize"},
    "init.specs_hint":          {"ko": "스펙 파일: .adelie/specs/ 에 MD/PDF/DOCX 파일을 넣으면 자동 인식됩니다",
                                 "en": "Spec files: Drop MD/PDF/DOCX into .adelie/specs/ for auto-detection"},

    # ── Config ───────────────────────────────────────────────────────────
    "config.title":             {"ko": "Adelie 설정",                           "en": "Adelie Configuration"},
    "config.provider_invalid":  {"ko": "Provider 는 'gemini' 또는 'ollama' 이어야 합니다",
                                 "en": "Provider must be 'gemini' or 'ollama'"},
    "config.lang_invalid":      {"ko": "언어는 'ko' 또는 'en' 이어야 합니다",
                                 "en": "Language must be 'ko' or 'en'"},

    # ── Run ──────────────────────────────────────────────────────────────
    "run.resuming":             {"ko": "워크스페이스 #{n} 재개",                 "en": "Resuming workspace #{n}"},
    "run.ws_not_found":         {"ko": "워크스페이스 #{n} 을 찾을 수 없습니다. 'adelie ws' 로 확인하세요.",
                                 "en": "Workspace #{n} not found. Use 'adelie ws' to list."},

    # ── Status ───────────────────────────────────────────────────────────
    "status.title":             {"ko": "Adelie 상태",                           "en": "Adelie Status"},
    "status.gemini_ok":         {"ko": "Gemini API 키 설정됨",                  "en": "Gemini API key configured"},
    "status.gemini_missing":    {"ko": "GEMINI_API_KEY 미설정",                "en": "GEMINI_API_KEY not set"},
    "status.ollama_ok":         {"ko": "Ollama 연결됨 — {n}개 모델 사용 가능",  "en": "Ollama connected — {n} model(s) available"},
    "status.ollama_fail":       {"ko": "Ollama 에 연결할 수 없습니다 ({url})",  "en": "Cannot connect to Ollama at {url}"},

    # ── Phase ────────────────────────────────────────────────────────────
    "phase.title":              {"ko": "Adelie — 프로젝트 Phase",               "en": "Adelie — Project Phase"},
    "phase.current":            {"ko": "현재",                                  "en": "current"},
    "phase.goal":               {"ko": "목표",                                  "en": "Goal"},
    "phase.transition":         {"ko": "전환 조건",                              "en": "Transition"},
    "phase.invalid":            {"ko": "유효하지 않은 phase 입니다. 선택 가능: {v}",
                                 "en": "Invalid phase. Choose from: {v}"},
    "phase.set_ok":             {"ko": "Phase 설정 → {label}",                  "en": "Phase set → {label}"},

    # ── KB ───────────────────────────────────────────────────────────────
    "kb.title":                 {"ko": "Knowledge Base",                        "en": "Knowledge Base"},
    "kb.cleared":               {"ko": "{n}개 오류 파일 삭제됨",                 "en": "Cleared {n} error file(s)"},
    "kb.reset_warn":            {"ko": "모든 Knowledge Base 파일이 삭제됩니다!", "en": "This will delete ALL Knowledge Base files!"},
    "kb.reset_done":            {"ko": "워크스페이스 리셋 완료",                 "en": "Workspace reset complete"},

    # ── Feedback ─────────────────────────────────────────────────────────
    "feedback.title":           {"ko": "대기 중인 피드백",                       "en": "Pending Feedback"},
    "feedback.none":            {"ko": "대기 중인 피드백 없음",                  "en": "No pending feedback"},
    "feedback.provide":         {"ko": "메시지를 입력하세요: adelie feedback \"내용\"",
                                 "en": "Provide a message: adelie feedback \"your message\""},

    # ── Goal ─────────────────────────────────────────────────────────────
    "goal.saved":               {"ko": "프로젝트 목표 저장됨!",                  "en": "Project goal saved!"},
    "goal.not_set":             {"ko": "프로젝트 목표가 설정되지 않았습니다.",     "en": "No project goal set yet."},

    # ── Workspace ────────────────────────────────────────────────────────
    "ws.title":                 {"ko": "Adelie 워크스페이스",                    "en": "Adelie Workspaces"},
    "ws.none":                  {"ko": "등록된 워크스페이스가 없습니다.",          "en": "No workspaces registered yet."},
    "ws.removed":               {"ko": "워크스페이스 #{n} 레지스트리에서 삭제",    "en": "Workspace #{n} removed from registry"},
    "ws.delete_data":           {"ko": ".adelie 데이터도 삭제하시겠습니까? (y/N): ",
                                 "en": "Also delete .adelie data? (y/N): "},

    # ── Errors ───────────────────────────────────────────────────────────
    "err.api_key":              {"ko": "GEMINI_API_KEY 가 설정되지 않았습니다.",
                                 "en": "GEMINI_API_KEY is not set."},
    "err.ollama_connect":       {"ko": "Ollama 에 연결할 수 없습니다 ({url})",
                                 "en": "Cannot connect to Ollama at {url}"},
    "err.adelie_not_found":     {"ko": ".adelie/ 를 찾을 수 없습니다 ({path})",
                                 "en": ".adelie/ not found in {path}"},

    # ── Common labels ────────────────────────────────────────────────────
    "ok":                       {"ko": "OK",        "en": "OK"},
    "error":                    {"ko": "오류",       "en": "ERROR"},
    "warning":                  {"ko": "주의",       "en": "WARNING"},
    "cancelled":                {"ko": "취소됨.",     "en": "Cancelled."},
}


def _get_lang() -> str:
    """Get the current language from the environment or config."""
    return os.getenv("ADELIE_LANGUAGE", "ko")


def t(key: str, **kwargs) -> str:
    """
    Get a translated message by key.

    Usage:
        t("init.done")
        t("status.ollama_ok", n=3)
        t("phase.invalid", v="initial, mid, late")
    """
    lang = _get_lang()
    entry = _MESSAGES.get(key)
    if not entry:
        return key
    msg = entry.get(lang, entry.get("en", key))
    if kwargs:
        try:
            msg = msg.format(**kwargs)
        except (KeyError, IndexError):
            pass
    return msg
