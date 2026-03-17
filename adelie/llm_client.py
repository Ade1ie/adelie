"""
adelie/llm_client.py

Unified LLM client with multi-model fallback support.
Tries models in order; skips models in cooldown after retryable failures.
"""

from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import requests
from rich.console import Console

from adelie.config import (
    FALLBACK_COOLDOWN_SECONDS,
    FALLBACK_MODELS,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    LLM_PROVIDER,
    OLLAMA_API_KEY,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
)

console = Console()

# ── Token usage tracking ─────────────────────────────────────────────────────
_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "calls": 0}

# Per-agent usage tracking (agent_name -> {prompt_tokens, completion_tokens, total_tokens, calls, time})
_agent_usage: dict[str, dict] = {}
_agent_usage_lock = threading.Lock()

# Thread-local storage for current agent name (safe for parallel execution)
_thread_local = threading.local()


def set_current_agent(agent_name: str) -> None:
    """Tag subsequent LLM calls with this agent name for per-agent tracking."""
    _thread_local.current_agent = agent_name


def clear_current_agent() -> None:
    """Clear the agent tag."""
    _thread_local.current_agent = None


def _get_current_agent() -> str:
    """Get current agent name from thread-local storage."""
    return getattr(_thread_local, "current_agent", None) or "unknown"


def reset_usage() -> None:
    """Reset token counters (call at start of each loop)."""
    _usage["prompt_tokens"] = 0
    _usage["completion_tokens"] = 0
    _usage["total_tokens"] = 0
    _usage["calls"] = 0
    with _agent_usage_lock:
        _agent_usage.clear()


def get_usage() -> dict:
    """Return current accumulated token usage."""
    return dict(_usage)


def get_agent_usage() -> dict[str, dict]:
    """Return per-agent token usage for the current cycle."""
    with _agent_usage_lock:
        return {k: dict(v) for k, v in _agent_usage.items()}


def _record_usage(prompt: int, completion: int) -> None:
    _usage["prompt_tokens"] += prompt
    _usage["completion_tokens"] += completion
    _usage["total_tokens"] += prompt + completion
    _usage["calls"] += 1

    # Also record per-agent
    agent = _get_current_agent()
    with _agent_usage_lock:
        if agent not in _agent_usage:
            _agent_usage[agent] = {
                "prompt_tokens": 0, "completion_tokens": 0,
                "total_tokens": 0, "calls": 0,
            }
        _agent_usage[agent]["prompt_tokens"] += prompt
        _agent_usage[agent]["completion_tokens"] += completion
        _agent_usage[agent]["total_tokens"] += prompt + completion
        _agent_usage[agent]["calls"] += 1


# ── Error Classification ─────────────────────────────────────────────────────


def classify_error(error: Exception) -> str:
    """
    Classify an LLM error into a category for fallback decisions.

    Returns one of:
      - "rate_limit"    : 429, RESOURCE_EXHAUSTED — retryable, use fallback
      - "server_error"  : 500, 503 — retryable, use fallback
      - "auth"          : 401, 403, PERMISSION_DENIED — NOT retryable
      - "model_not_found": 404 — NOT retryable on same model
      - "connection"    : network issues, timeout — retryable, use fallback
      - "unknown"       : anything else
    """
    if isinstance(error, (ConnectionError, requests.ConnectionError)):
        return "connection"
    if isinstance(error, requests.exceptions.Timeout):
        return "connection"

    err_str = str(error)

    # Rate limit
    if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
        return "rate_limit"

    # Auth errors — no point in fallback to same provider
    if "401" in err_str or "403" in err_str or "PERMISSION_DENIED" in err_str:
        return "auth"

    # Model not found
    if "404" in err_str and ("not found" in err_str.lower() or "model" in err_str.lower()):
        return "model_not_found"

    # Server errors
    if "500" in err_str or "503" in err_str or "INTERNAL" in err_str:
        return "server_error"

    # Connection-like messages
    if "timeout" in err_str.lower() or "connection" in err_str.lower():
        return "connection"

    return "unknown"


# Categories where fallback to next model makes sense
_FALLBACK_CATEGORIES = {"rate_limit", "server_error", "connection", "unknown"}


# ── Provider Health / Cooldown ───────────────────────────────────────────────


@dataclass
class _ModelHealth:
    """Tracks cooldown state for a single (provider, model) pair."""

    last_failure_time: float = 0.0
    last_failure_category: str = ""
    consecutive_failures: int = 0


# Module-level cooldown state  —  key: "provider:model"
_health: dict[str, _ModelHealth] = {}


def _health_key(provider: str, model: str) -> str:
    return f"{provider}:{model}"


def _is_in_cooldown(provider: str, model: str) -> bool:
    """Check whether a model is currently in cooldown."""
    key = _health_key(provider, model)
    h = _health.get(key)
    if h is None or h.last_failure_time == 0.0:
        return False
    elapsed = time.time() - h.last_failure_time
    return elapsed < FALLBACK_COOLDOWN_SECONDS


def _record_failure(provider: str, model: str, category: str) -> None:
    """Mark a model as failed (enters cooldown)."""
    key = _health_key(provider, model)
    h = _health.setdefault(key, _ModelHealth())
    h.last_failure_time = time.time()
    h.last_failure_category = category
    h.consecutive_failures += 1


def _record_success(provider: str, model: str) -> None:
    """Clear cooldown on success."""
    key = _health_key(provider, model)
    h = _health.get(key)
    if h:
        h.last_failure_time = 0.0
        h.last_failure_category = ""
        h.consecutive_failures = 0


def reset_health() -> None:
    """Reset all cooldown state (useful for tests)."""
    _health.clear()


def get_health_status() -> dict:
    """Return a snapshot of all model health states (for debugging)."""
    now = time.time()
    result = {}
    for key, h in _health.items():
        if h.last_failure_time > 0:
            result[key] = {
                "in_cooldown": (now - h.last_failure_time) < FALLBACK_COOLDOWN_SECONDS,
                "seconds_remaining": max(
                    0, FALLBACK_COOLDOWN_SECONDS - (now - h.last_failure_time)
                ),
                "last_failure_category": h.last_failure_category,
                "consecutive_failures": h.consecutive_failures,
            }
    return result


# ── Fallback Chain Builder ───────────────────────────────────────────────────


def _build_fallback_chain() -> List[Tuple[str, str]]:
    """
    Parse FALLBACK_MODELS into an ordered list of (provider, model) tuples.
    If not configured, returns the single default provider.
    """
    raw = FALLBACK_MODELS.strip()
    if not raw:
        # Backward compatible: use single provider
        if LLM_PROVIDER == "ollama":
            return [("ollama", OLLAMA_MODEL)]
        return [("gemini", GEMINI_MODEL)]

    chain: List[Tuple[str, str]] = []
    seen = set()
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        if ":" in entry:
            provider, model = entry.split(":", 1)
        else:
            # Bare model name — assume current provider
            provider = LLM_PROVIDER
            model = entry
        provider = provider.strip().lower()
        model = model.strip()
        key = f"{provider}:{model}"
        if key not in seen:
            seen.add(key)
            chain.append((provider, model))

    if not chain:
        if LLM_PROVIDER == "ollama":
            return [("ollama", OLLAMA_MODEL)]
        return [("gemini", GEMINI_MODEL)]

    return chain


# ── Gemini client (lazy) ─────────────────────────────────────────────────────
_genai_client = None


def _get_gemini_client():
    global _genai_client
    if _genai_client is None:
        from google import genai

        _genai_client = genai.Client(api_key=GEMINI_API_KEY)
    return _genai_client


# ── Provider-specific generators ─────────────────────────────────────────────


def _generate_with_model(
    provider: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    response_schema: dict | None = None,
) -> str:
    """
    Generate text using a specific provider/model.
    No retries here — fallback chain handles retries at a higher level.
    """
    if provider == "ollama":
        return _generate_ollama_model(model, system_prompt, user_prompt, temperature)
    else:
        return _generate_gemini_model(model, system_prompt, user_prompt, temperature, response_schema)


def _generate_gemini_model(
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    response_schema: dict | None = None,
) -> str:
    """Call Gemini API with a specific model (no retry — handled by fallback)."""
    from google.genai import types as genai_types

    client = _get_gemini_client()

    config_kwargs = {
        "temperature": temperature,
        "response_mime_type": "application/json",
    }
    if response_schema:
        config_kwargs["response_schema"] = response_schema

    response = client.models.generate_content(
        model=model,
        contents=[system_prompt, user_prompt],
        config=genai_types.GenerateContentConfig(**config_kwargs),
    )

    # Record usage
    try:
        meta = response.usage_metadata
        _record_usage(
            prompt=getattr(meta, "prompt_token_count", 0) or 0,
            completion=getattr(meta, "candidates_token_count", 0) or 0,
        )
    except Exception:
        _record_usage(
            prompt=len(system_prompt + user_prompt) // 4,
            completion=len(response.text) // 4,
        )

    return response.text.strip()


def _generate_ollama_model(
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
) -> str:
    """Call Ollama via its OpenAI-compatible chat completions API."""
    url = f"{OLLAMA_BASE_URL}/v1/chat/completions"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "stream": False,
    }

    headers = {}
    if OLLAMA_API_KEY:
        headers["Authorization"] = f"Bearer {OLLAMA_API_KEY}"

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=120)
        resp.raise_for_status()
    except requests.ConnectionError:
        raise ConnectionError(
            f"Cannot connect to Ollama at {OLLAMA_BASE_URL}. "
            "Is Ollama running? Start it with: ollama serve"
        )
    except requests.HTTPError as e:
        raise RuntimeError(f"Ollama API error: {e} — {resp.text}")

    data = resp.json()
    raw = data["choices"][0]["message"]["content"].strip()

    # Record token usage from Ollama response
    usage = data.get("usage", {})
    if usage:
        _record_usage(
            prompt=usage.get("prompt_tokens", 0),
            completion=usage.get("completion_tokens", 0),
        )
    else:
        _record_usage(
            prompt=len(system_prompt + user_prompt) // 4,
            completion=len(raw) // 4,
        )

    # Ollama models sometimes wrap JSON in markdown fences — strip them
    raw = _strip_markdown_fences(raw)
    return raw


# ── Public API ───────────────────────────────────────────────────────────────


def generate(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.3,
    response_schema: dict | None = None,
) -> str:
    """
    Generate text from the configured LLM provider(s) with automatic fallback.

    Tries each model in the fallback chain in order. Models in cooldown
    are skipped (unless it's the last remaining candidate). Non-retryable
    errors (auth) are raised immediately.

    Args:
        system_prompt: System-level instructions.
        user_prompt:   User-level prompt content.
        temperature:   Sampling temperature (0.0–1.0).
        response_schema: Optional JSON schema dict to enforce structured output (Gemini only).

    Returns:
        Raw text response from the model.

    Raises:
        Exception on API errors (after all fallbacks exhausted).
    """
    chain = _build_fallback_chain()
    last_error: Optional[Exception] = None
    attempts: List[dict] = []

    for i, (provider, model) in enumerate(chain):
        is_last = i == len(chain) - 1

        # Skip models in cooldown (unless it's the last candidate)
        if not is_last and _is_in_cooldown(provider, model):
            console.print(
                f"[dim]⏭  Skipping {provider}:{model} (in cooldown)[/dim]"
            )
            attempts.append({
                "provider": provider,
                "model": model,
                "status": "skipped_cooldown",
            })
            continue

        try:
            result = _generate_with_model(
                provider, model, system_prompt, user_prompt, temperature, response_schema
            )
            # Success — clear any cooldown
            _record_success(provider, model)

            # Log if we fell back from primary
            if i > 0 or attempts:
                console.print(
                    f"[green]✅ Fallback succeeded with {provider}:{model} "
                    f"(attempt {i + 1}/{len(chain)})[/green]"
                )

            return result

        except Exception as e:
            category = classify_error(e)
            last_error = e

            attempts.append({
                "provider": provider,
                "model": model,
                "status": "failed",
                "category": category,
                "error": str(e)[:200],
            })

            # Auth errors: no point trying other models on same provider,
            # but DO try models on different providers
            if category == "auth":
                console.print(
                    f"[red]🔑 Auth error on {provider}:{model}: {e}[/red]"
                )
                # If no other providers in chain, raise immediately
                remaining_providers = {
                    p for j, (p, m) in enumerate(chain) if j > i
                }
                if not remaining_providers or remaining_providers == {provider}:
                    raise
                # Otherwise continue to next (different) provider
                _record_failure(provider, model, category)
                continue

            # Retryable errors: record cooldown and try next model
            if category in _FALLBACK_CATEGORIES:
                _record_failure(provider, model, category)
                if not is_last:
                    console.print(
                        f"[yellow]⚡ {provider}:{model} failed ({category}), "
                        f"trying next model…[/yellow]"
                    )
                    continue

            # Last model or non-retryable: raise
            if is_last:
                if len(attempts) > 1:
                    summary = " → ".join(
                        f"{a['provider']}:{a['model']}({a['status']})"
                        for a in attempts
                    )
                    console.print(
                        f"[red]❌ All models failed: {summary}[/red]"
                    )
                raise

    # Should not reach here, but just in case
    if last_error:
        raise last_error
    raise RuntimeError("No models configured in fallback chain")


# ── Helpers ──────────────────────────────────────────────────────────────────


def _strip_markdown_fences(text: str) -> str:
    """Remove ```json ... ``` or ``` ... ``` wrappers if present."""
    pattern = r"^```(?:json)?\s*\n?(.*?)\n?\s*```$"
    match = re.match(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text


# ── Provider info ────────────────────────────────────────────────────────────


def get_provider_info() -> str:
    """Return a human-readable string describing the active LLM provider(s)."""
    chain = _build_fallback_chain()
    if len(chain) == 1:
        provider, model = chain[0]
        if provider == "ollama":
            return f"Ollama ({model}) @ {OLLAMA_BASE_URL}"
        return f"Gemini ({model})"

    parts = [f"{p}:{m}" for p, m in chain]
    return f"Fallback chain: {' → '.join(parts)}"
