from __future__ import annotations

import os

import pytest

from doc_chunk.errors import LLMUnavailableError
from doc_chunk.llm.client import FakeLLMClient
from doc_chunk.llm.openai_client import create_llm_client_from_env


def test_fake_llm_client_returns_queued_response() -> None:
    client = FakeLLMClient(responses=['{"ok":true}'])
    out = client.complete([{"role": "user", "content": "hi"}], response_format="json")
    assert out == '{"ok":true}'
    assert len(client.calls) == 1


def test_create_llm_client_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(LLMUnavailableError):
        create_llm_client_from_env()


def test_create_llm_client_uses_env_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("DOC_CHUNK_LLM_MODEL", "fake-model")
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    client = create_llm_client_from_env()
    assert getattr(client, "model") == "fake-model"
    os.environ.pop("OPENAI_API_KEY", None)
