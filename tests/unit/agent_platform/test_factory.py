from __future__ import annotations

import pytest

from agent_platform.backends.local import LocalBackend
from agent_platform.backends.platform import PlatformBackend
from agent_platform.factory import create_agent_client_from_env
from doc_chunk.llm.client import FakeLLMClient


def test_factory_defaults_to_local_backend(monkeypatch):
    monkeypatch.delenv("AGENT_INVOKE_MODE", raising=False)
    fake = FakeLLMClient(default_response="{}")
    client = create_agent_client_from_env(llm_client=fake)
    backend = client._backend  # noqa: SLF001 - test inspects wiring
    assert isinstance(backend, LocalBackend)


def test_factory_platform_mode(monkeypatch):
    monkeypatch.setenv("AGENT_INVOKE_MODE", "platform")
    monkeypatch.setenv("AGENT_PLATFORM_BASE_URL", "http://127.0.0.1:8000")
    client = create_agent_client_from_env()
    backend = client._backend  # noqa: SLF001
    assert isinstance(backend, PlatformBackend)
    assert backend._base_url == "http://127.0.0.1:8000"  # noqa: SLF001


def test_factory_rejects_unknown_mode(monkeypatch):
    monkeypatch.setenv("AGENT_INVOKE_MODE", "hybrid")
    with pytest.raises(ValueError, match="unsupported AGENT_INVOKE_MODE"):
        create_agent_client_from_env(llm_client=FakeLLMClient())
