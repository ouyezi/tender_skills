from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from doc_chunk.llm.openai_client import OpenAILLMClient
from doc_chunk.llm.stream_logging import collect_chat_completion_stream
from doc_chunk.llm.usage import serialize_usage


def _chunk(text: str, *, usage: object | None = None, finish_reason: str | None = None) -> SimpleNamespace:
    choice = SimpleNamespace(delta=SimpleNamespace(content=text))
    if finish_reason:
        choice.finish_reason = finish_reason
    return SimpleNamespace(choices=[choice], usage=usage)


def test_collect_chat_completion_stream_joins_chunks(caplog: pytest.LogCaptureFixture) -> None:
    stream = [_chunk('{"a":'), _chunk("1}")]
    with caplog.at_level("INFO", logger="doc_chunk.llm"):
        result = collect_chat_completion_stream(
            stream,
            model="qwen3.7-max",
            response_format="json",
        )
    assert result.text == '{"a":1}'
    assert any("llm_stream_start" in r.message for r in caplog.records)
    assert any("llm_stream_chunk" in r.message for r in caplog.records)
    assert any("llm_stream_done" in r.message for r in caplog.records)


def test_collect_chat_completion_stream_captures_usage() -> None:
    usage = SimpleNamespace(
        prompt_tokens=100,
        completion_tokens=20,
        total_tokens=120,
        prompt_tokens_details=SimpleNamespace(cached_tokens=80),
    )
    stream = [_chunk('{"ok":'), _chunk("true}"), SimpleNamespace(choices=[], usage=usage)]
    result = collect_chat_completion_stream(
        stream,
        model="qwen3.7-max",
        response_format="json",
    )
    assert result.text == '{"ok":true}'
    assert result.usage is not None
    assert result.usage["prompt_tokens"] == 100
    assert result.usage["prompt_tokens_details"]["cached_tokens"] == 80


def test_serialize_usage_from_model_dump() -> None:
    usage = SimpleNamespace(
        model_dump=lambda exclude_none=True: {
            "prompt_tokens": 1,
            "completion_tokens": 2,
            "total_tokens": 3,
            "prompt_tokens_details": {"cached_tokens": 1},
        }
    )
    data = serialize_usage(usage)
    assert data is not None
    assert data["prompt_tokens_details"]["cached_tokens"] == 1


def test_openai_client_uses_stream_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_STREAM", "1")
    client = OpenAILLMClient(model="qwen3.7-max", api_key="sk-test", base_url="http://example")
    mock_create = MagicMock(return_value=iter([_chunk('{"ok":true}')]))
    client._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=mock_create)))

    out = client.complete([{"role": "user", "content": "hi"}], response_format="json")

    assert out == '{"ok":true}'
    assert mock_create.call_args.kwargs["stream"] is True
    assert mock_create.call_args.kwargs["stream_options"] == {"include_usage": True}


def test_openai_client_complete_with_meta(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_STREAM", "0")
    client = OpenAILLMClient(model="qwen3.7-max", api_key="sk-test", base_url="http://example")
    usage = SimpleNamespace(
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        prompt_tokens_details=SimpleNamespace(cached_tokens=3),
    )
    mock_create = MagicMock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok":true}'), finish_reason="stop")],
            usage=usage,
        )
    )
    client._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=mock_create)))

    result = client.complete_with_meta([{"role": "user", "content": "hi"}], response_format="json")

    assert result.text == '{"ok":true}'
    assert result.model == "qwen3.7-max"
    assert result.usage is not None
    assert result.usage["prompt_tokens_details"]["cached_tokens"] == 3
    assert result.finish_reason == "stop"
    assert result.stream is False
    assert result.duration_ms is not None


def test_openai_client_can_disable_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_STREAM", "0")
    client = OpenAILLMClient(model="qwen3.7-max", api_key="sk-test", base_url="http://example")
    mock_create = MagicMock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok":true}'))]
        )
    )
    client._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=mock_create)))

    out = client.complete([{"role": "user", "content": "hi"}], response_format="json")

    assert out == '{"ok":true}'
    assert "stream" not in mock_create.call_args.kwargs
