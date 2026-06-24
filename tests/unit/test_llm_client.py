from __future__ import annotations

import pytest

from doc_chunk.errors import LLMUnavailableError
from doc_chunk.llm.client import FakeLLMClient
from doc_chunk.llm.openai_client import create_llm_client_from_env, resolve_llm_settings_from_env


def test_fake_llm_client_returns_queued_response() -> None:
    client = FakeLLMClient(responses=['{"ok":true}'])
    out = client.complete([{"role": "user", "content": "hi"}], response_format="json")
    assert out == '{"ok":true}'
    assert len(client.calls) == 1


def test_create_llm_client_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(LLMUnavailableError):
        create_llm_client_from_env()


def test_create_llm_client_uses_llm_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_MODEL", "qwen3.6-plus")
    monkeypatch.delenv("DOC_CHUNK_LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    client = create_llm_client_from_env()
    assert client.model == "qwen3.6-plus"


def test_resolve_llm_settings_defaults_to_qwen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_PROVIDER", "qwen")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("DOC_CHUNK_LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    _, model, base_url = resolve_llm_settings_from_env()
    assert model == "qwen3.7-max"
    assert base_url == "https://dashscope.aliyuncs.com/compatible-mode/v1"


def test_openai_provider_preset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    _, model, base_url = resolve_llm_settings_from_env()
    assert model == "gpt-4o-mini"
    assert base_url == "https://api.openai.com/v1"


def test_legacy_openai_api_key_still_works(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-legacy")
    monkeypatch.setenv("DOC_CHUNK_LLM_MODEL", "legacy-model")
    client = create_llm_client_from_env()
    assert client.model == "legacy-model"
