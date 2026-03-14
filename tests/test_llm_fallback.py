"""tests/test_llm_fallback.py — Tests for model fallback and error classification."""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest
import requests


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_rate_limit_error():
    return RuntimeError("429 RESOURCE_EXHAUSTED: Quota exceeded")


def _make_auth_error():
    return RuntimeError("403 PERMISSION_DENIED: Invalid API key")


def _make_server_error():
    return RuntimeError("503 Service Unavailable")


def _make_connection_error():
    return ConnectionError("Cannot connect to Ollama at http://localhost:11434")


def _make_model_not_found_error():
    return RuntimeError("404 Model not found: gemini-2.0-ultra")


# ── Error Classification ────────────────────────────────────────────────────


class TestClassifyError:
    def test_rate_limit_429(self):
        from adelie.llm_client import classify_error
        assert classify_error(_make_rate_limit_error()) == "rate_limit"

    def test_auth_403(self):
        from adelie.llm_client import classify_error
        assert classify_error(_make_auth_error()) == "auth"

    def test_server_error_503(self):
        from adelie.llm_client import classify_error
        assert classify_error(_make_server_error()) == "server_error"

    def test_connection_error(self):
        from adelie.llm_client import classify_error
        assert classify_error(_make_connection_error()) == "connection"

    def test_model_not_found(self):
        from adelie.llm_client import classify_error
        assert classify_error(_make_model_not_found_error()) == "model_not_found"

    def test_unknown_error(self):
        from adelie.llm_client import classify_error
        assert classify_error(RuntimeError("something weird happened")) == "unknown"


# ── Fallback Chain Builder ──────────────────────────────────────────────────


class TestBuildFallbackChain:
    def test_empty_fallback_uses_default_gemini(self, monkeypatch):
        import adelie.llm_client as lc
        monkeypatch.setattr(lc, "FALLBACK_MODELS", "")
        monkeypatch.setattr(lc, "LLM_PROVIDER", "gemini")
        monkeypatch.setattr(lc, "GEMINI_MODEL", "gemini-2.0-flash")
        chain = lc._build_fallback_chain()
        assert chain == [("gemini", "gemini-2.0-flash")]

    def test_empty_fallback_uses_default_ollama(self, monkeypatch):
        import adelie.llm_client as lc
        monkeypatch.setattr(lc, "FALLBACK_MODELS", "")
        monkeypatch.setattr(lc, "LLM_PROVIDER", "ollama")
        monkeypatch.setattr(lc, "OLLAMA_MODEL", "llama3.2")
        chain = lc._build_fallback_chain()
        assert chain == [("ollama", "llama3.2")]

    def test_multi_model_chain(self, monkeypatch):
        import adelie.llm_client as lc
        monkeypatch.setattr(
            lc, "FALLBACK_MODELS",
            "gemini:gemini-2.5-flash, gemini:gemini-2.0-flash, ollama:llama3.2"
        )
        chain = lc._build_fallback_chain()
        assert chain == [
            ("gemini", "gemini-2.5-flash"),
            ("gemini", "gemini-2.0-flash"),
            ("ollama", "llama3.2"),
        ]

    def test_deduplicates_models(self, monkeypatch):
        import adelie.llm_client as lc
        monkeypatch.setattr(
            lc, "FALLBACK_MODELS",
            "gemini:gemini-2.0-flash, gemini:gemini-2.0-flash"
        )
        chain = lc._build_fallback_chain()
        assert len(chain) == 1

    def test_bare_model_name_uses_default_provider(self, monkeypatch):
        import adelie.llm_client as lc
        monkeypatch.setattr(lc, "FALLBACK_MODELS", "my-custom-model")
        monkeypatch.setattr(lc, "LLM_PROVIDER", "gemini")
        chain = lc._build_fallback_chain()
        assert chain == [("gemini", "my-custom-model")]


# ── Cooldown Tracking ───────────────────────────────────────────────────────


class TestCooldown:
    def setup_method(self):
        from adelie.llm_client import reset_health
        reset_health()

    def test_not_in_cooldown_initially(self):
        from adelie.llm_client import _is_in_cooldown
        assert _is_in_cooldown("gemini", "gemini-2.0-flash") is False

    def test_in_cooldown_after_failure(self, monkeypatch):
        import adelie.llm_client as lc
        monkeypatch.setattr(lc, "FALLBACK_COOLDOWN_SECONDS", 60)
        lc._record_failure("gemini", "gemini-2.0-flash", "rate_limit")
        assert lc._is_in_cooldown("gemini", "gemini-2.0-flash") is True

    def test_cooldown_clears_on_success(self, monkeypatch):
        import adelie.llm_client as lc
        monkeypatch.setattr(lc, "FALLBACK_COOLDOWN_SECONDS", 60)
        lc._record_failure("gemini", "gemini-2.0-flash", "rate_limit")
        assert lc._is_in_cooldown("gemini", "gemini-2.0-flash") is True
        lc._record_success("gemini", "gemini-2.0-flash")
        assert lc._is_in_cooldown("gemini", "gemini-2.0-flash") is False

    def test_cooldown_expires(self, monkeypatch):
        import adelie.llm_client as lc
        monkeypatch.setattr(lc, "FALLBACK_COOLDOWN_SECONDS", 1)
        lc._record_failure("gemini", "gemini-2.0-flash", "rate_limit")
        assert lc._is_in_cooldown("gemini", "gemini-2.0-flash") is True
        time.sleep(1.1)
        assert lc._is_in_cooldown("gemini", "gemini-2.0-flash") is False


# ── generate() with Fallback ────────────────────────────────────────────────


class TestGenerateWithFallback:
    def setup_method(self):
        from adelie.llm_client import reset_health
        reset_health()

    def test_single_provider_works(self, monkeypatch):
        """When fallback is not configured, single provider works normally."""
        import adelie.llm_client as lc
        monkeypatch.setattr(lc, "FALLBACK_MODELS", "")
        monkeypatch.setattr(lc, "LLM_PROVIDER", "gemini")
        monkeypatch.setattr(lc, "GEMINI_MODEL", "gemini-2.0-flash")

        with patch.object(lc, "_generate_with_model", return_value='{"result": "ok"}') as mock:
            result = lc.generate("sys", "user")
            assert result == '{"result": "ok"}'
            mock.assert_called_once_with("gemini", "gemini-2.0-flash", "sys", "user", 0.3)

    def test_fallback_on_rate_limit(self, monkeypatch):
        """Primary rate-limited → falls back to secondary."""
        import adelie.llm_client as lc
        monkeypatch.setattr(lc, "FALLBACK_MODELS", "gemini:model-a,ollama:model-b")
        monkeypatch.setattr(lc, "FALLBACK_COOLDOWN_SECONDS", 60)

        def side_effect(provider, model, sys, usr, temp):
            if provider == "gemini" and model == "model-a":
                raise _make_rate_limit_error()
            return '{"ok": true}'

        with patch.object(lc, "_generate_with_model", side_effect=side_effect):
            result = lc.generate("sys", "user")
            assert result == '{"ok": true}'

    def test_fallback_on_connection_error(self, monkeypatch):
        """Primary connection error → falls back to secondary."""
        import adelie.llm_client as lc
        monkeypatch.setattr(lc, "FALLBACK_MODELS", "ollama:local,gemini:cloud")
        monkeypatch.setattr(lc, "FALLBACK_COOLDOWN_SECONDS", 60)

        def side_effect(provider, model, sys, usr, temp):
            if provider == "ollama":
                raise _make_connection_error()
            return '{"ok": true}'

        with patch.object(lc, "_generate_with_model", side_effect=side_effect):
            result = lc.generate("sys", "user")
            assert result == '{"ok": true}'

    def test_cooldown_skips_model(self, monkeypatch):
        """Models in cooldown are skipped, next model used instead."""
        import adelie.llm_client as lc
        monkeypatch.setattr(lc, "FALLBACK_MODELS", "gemini:model-a,gemini:model-b,ollama:model-c")
        monkeypatch.setattr(lc, "FALLBACK_COOLDOWN_SECONDS", 60)

        # Put model-a in cooldown
        lc._record_failure("gemini", "model-a", "rate_limit")

        call_log = []

        def side_effect(provider, model, sys, usr, temp):
            call_log.append((provider, model))
            return '{"ok": true}'

        with patch.object(lc, "_generate_with_model", side_effect=side_effect):
            lc.generate("sys", "user")

        # model-a should be skipped, model-b used directly
        assert ("gemini", "model-a") not in call_log
        assert call_log[0] == ("gemini", "model-b")

    def test_all_models_fail_raises_last(self, monkeypatch):
        """When all models fail, the last error is raised."""
        import adelie.llm_client as lc
        monkeypatch.setattr(lc, "FALLBACK_MODELS", "gemini:model-a,ollama:model-b")
        monkeypatch.setattr(lc, "FALLBACK_COOLDOWN_SECONDS", 60)

        def side_effect(provider, model, sys, usr, temp):
            if model == "model-a":
                raise _make_rate_limit_error()
            raise _make_server_error()

        with patch.object(lc, "_generate_with_model", side_effect=side_effect):
            with pytest.raises(RuntimeError, match="503"):
                lc.generate("sys", "user")

    def test_auth_error_skips_to_different_provider(self, monkeypatch):
        """Auth error on provider A → tries provider B (different provider)."""
        import adelie.llm_client as lc
        monkeypatch.setattr(lc, "FALLBACK_MODELS", "gemini:model-a,ollama:model-b")
        monkeypatch.setattr(lc, "FALLBACK_COOLDOWN_SECONDS", 60)

        def side_effect(provider, model, sys, usr, temp):
            if provider == "gemini":
                raise _make_auth_error()
            return '{"ok": true}'

        with patch.object(lc, "_generate_with_model", side_effect=side_effect):
            result = lc.generate("sys", "user")
            assert result == '{"ok": true}'

    def test_auth_error_raises_if_only_same_provider(self, monkeypatch):
        """Auth error when all remaining are same provider → raises immediately."""
        import adelie.llm_client as lc
        monkeypatch.setattr(lc, "FALLBACK_MODELS", "gemini:model-a,gemini:model-b")
        monkeypatch.setattr(lc, "FALLBACK_COOLDOWN_SECONDS", 60)

        def side_effect(provider, model, sys, usr, temp):
            raise _make_auth_error()

        with patch.object(lc, "_generate_with_model", side_effect=side_effect):
            with pytest.raises(RuntimeError, match="403"):
                lc.generate("sys", "user")

    def test_last_candidate_always_tried_even_in_cooldown(self, monkeypatch):
        """The last candidate is tried even if in cooldown (last resort)."""
        import adelie.llm_client as lc
        monkeypatch.setattr(lc, "FALLBACK_MODELS", "gemini:model-a")
        monkeypatch.setattr(lc, "FALLBACK_COOLDOWN_SECONDS", 60)

        # Put the only model in cooldown
        lc._record_failure("gemini", "model-a", "rate_limit")

        with patch.object(lc, "_generate_with_model", return_value='{"ok": true}'):
            # Should still try it because it's the only (= last) candidate
            result = lc.generate("sys", "user")
            assert result == '{"ok": true}'


# ── get_provider_info ────────────────────────────────────────────────────────


class TestProviderInfo:
    def test_single_gemini(self, monkeypatch):
        import adelie.llm_client as lc
        monkeypatch.setattr(lc, "FALLBACK_MODELS", "")
        monkeypatch.setattr(lc, "LLM_PROVIDER", "gemini")
        monkeypatch.setattr(lc, "GEMINI_MODEL", "gemini-2.5-flash")
        assert "Gemini" in lc.get_provider_info()

    def test_single_ollama(self, monkeypatch):
        import adelie.llm_client as lc
        monkeypatch.setattr(lc, "FALLBACK_MODELS", "")
        monkeypatch.setattr(lc, "LLM_PROVIDER", "ollama")
        monkeypatch.setattr(lc, "OLLAMA_MODEL", "llama3.2")
        assert "Ollama" in lc.get_provider_info()

    def test_multi_model_chain(self, monkeypatch):
        import adelie.llm_client as lc
        monkeypatch.setattr(lc, "FALLBACK_MODELS", "gemini:a,ollama:b")
        info = lc.get_provider_info()
        assert "Fallback chain" in info
        assert "gemini:a" in info
        assert "ollama:b" in info
