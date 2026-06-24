from __future__ import annotations

import logging
import os
import sys
from typing import Any, Literal

from doc_chunk.llm.completion import StreamCollectResult

logger = logging.getLogger("doc_chunk.llm")


def _env_bool(key: str, default: bool) -> bool:
    raw = os.environ.get(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def stream_enabled() -> bool:
    return _env_bool("LLM_STREAM", True)


def stream_log_enabled() -> bool:
    return _env_bool("LLM_LOG_STREAM", True)


def default_llm_timeout() -> float:
    raw = os.environ.get("LLM_TIMEOUT")
    if raw is None:
        return 300.0
    return float(raw)


def log_stream_chunk(text: str) -> None:
    if not text:
        return
    if stream_log_enabled():
        logger.info("llm_stream_chunk %s", text)
        for handler in logger.handlers:
            handler.flush()
        if not logger.handlers:
            sys.stderr.flush()


def collect_chat_completion_stream(
    stream: object,
    *,
    model: str,
    response_format: Literal["text", "json"],
) -> StreamCollectResult:
    from doc_chunk.llm.usage import serialize_usage

    if stream_log_enabled():
        logger.info(
            "llm_stream_start model=%s response_format=%s",
            model,
            response_format,
        )
    parts: list[str] = []
    usage: dict[str, Any] | None = None
    finish_reason: str | None = None
    try:
        for chunk in stream:
            choices = getattr(chunk, "choices", None) or []
            if choices:
                choice = choices[0]
                delta = getattr(choice.delta, "content", None)
                if delta:
                    parts.append(delta)
                    log_stream_chunk(delta)
                reason = getattr(choice, "finish_reason", None)
                if reason:
                    finish_reason = reason
            chunk_usage = getattr(chunk, "usage", None)
            if chunk_usage is not None:
                usage = serialize_usage(chunk_usage)
    except Exception as exc:
        logger.error("llm_stream_failed model=%s error=%s", model, exc)
        raise
    text = "".join(parts)
    if stream_log_enabled():
        logger.info(
            "llm_stream_done model=%s chars=%d usage=%s",
            model,
            len(text),
            usage,
        )
    return StreamCollectResult(text=text, usage=usage, finish_reason=finish_reason)
