from __future__ import annotations

import logging
import os
import time

from openai import OpenAI

from doc_chunk.errors import LLMUnavailableError
from doc_chunk.llm.client import LLMClient
from doc_chunk.llm.completion import LLMCompletionResult
from doc_chunk.llm.stream_logging import (
    collect_chat_completion_stream,
    default_llm_timeout,
    stream_enabled,
)
from doc_chunk.llm.usage import serialize_usage

logger = logging.getLogger("doc_chunk.llm")

# Preset profiles — aligned with tender_knowledge (LLM_PROVIDER=qwen|openai).
_LLM_PRESETS: dict[str, dict[str, str]] = {
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen3.7-max",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
    },
}


def resolve_llm_settings_from_env() -> tuple[str, str, str]:
    """Return (api_key, model, base_url) from environment."""
    api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise LLMUnavailableError("LLM_API_KEY or OPENAI_API_KEY is required for LLM operations")

    provider = (os.getenv("LLM_PROVIDER") or "qwen").lower()
    preset = _LLM_PRESETS.get(provider, _LLM_PRESETS["qwen"])

    model = (
        os.getenv("LLM_MODEL")
        or os.getenv("DOC_CHUNK_LLM_MODEL")
        or preset["model"]
    )
    base_url = (
        os.getenv("LLM_BASE_URL")
        or os.getenv("OPENAI_API_BASE")
        or preset["base_url"]
    )
    return api_key, model, base_url


class OpenAILLMClient:
    def __init__(self, *, model: str, api_key: str, base_url: str | None = None) -> None:
        self.model = model
        self.base_url = base_url
        if base_url:
            self._client = OpenAI(api_key=api_key, base_url=base_url)
        else:
            self._client = OpenAI(api_key=api_key)

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        response_format: str = "text",
        timeout: float | None = None,
    ) -> str:
        return self.complete_with_meta(
            messages,
            response_format=response_format,  # type: ignore[arg-type]
            timeout=timeout,
        ).text

    def complete_with_meta(
        self,
        messages: list[dict[str, str]],
        *,
        response_format: str = "text",
        timeout: float | None = None,
    ) -> LLMCompletionResult:
        effective_timeout = default_llm_timeout() if timeout is None else timeout
        kwargs: dict[str, object] = {
            "model": self.model,
            "messages": messages,
            "timeout": effective_timeout,
        }
        if response_format == "json":
            kwargs["response_format"] = {"type": "json_object"}

        use_stream = stream_enabled()
        if use_stream:
            kwargs["stream"] = True
            kwargs["stream_options"] = {"include_usage": True}

        started = time.perf_counter()
        try:
            if use_stream:
                stream = self._client.chat.completions.create(**kwargs)
                collected = collect_chat_completion_stream(
                    stream,
                    model=self.model,
                    response_format=response_format,  # type: ignore[arg-type]
                )
                duration_ms = (time.perf_counter() - started) * 1000
                return LLMCompletionResult(
                    text=collected.text,
                    model=self.model,
                    usage=collected.usage,
                    finish_reason=collected.finish_reason,
                    stream=True,
                    duration_ms=duration_ms,
                )

            response = self._client.chat.completions.create(**kwargs)
            message = response.choices[0].message.content
            finish_reason = getattr(response.choices[0], "finish_reason", None)
            duration_ms = (time.perf_counter() - started) * 1000
            return LLMCompletionResult(
                text=message or "",
                model=self.model,
                usage=serialize_usage(getattr(response, "usage", None)),
                finish_reason=finish_reason,
                stream=False,
                duration_ms=duration_ms,
            )
        except Exception as exc:
            logger.error(
                "llm_request_failed model=%s stream=%s timeout=%s error=%s",
                self.model,
                use_stream,
                effective_timeout,
                exc,
            )
            raise


def create_llm_client_from_env() -> LLMClient:
    api_key, model, base_url = resolve_llm_settings_from_env()
    return OpenAILLMClient(model=model, api_key=api_key, base_url=base_url)
