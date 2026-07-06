from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from agent_platform.client import AgentClient
from agent_platform.models import AgentInvokeError
from tender_insights.errors import LLMExtractionError
from tender_insights.interpret.llm_logging import log_llm_attempt, log_llm_response

T = TypeVar("T", bound=BaseModel)


def extract_json_via_agent(
    agent_client: AgentClient,
    call_type: str,
    input: dict[str, Any],
    model_type: type[T],
    *,
    max_retries: int = 2,
    normalize: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    log_context: dict[str, Any] | None = None,
) -> T:
    """通过 AgentClient 提取 JSON 模型（同 input 盲重试，带 interpret 日志）。"""
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            result = agent_client.invoke(call_type, input)
        except AgentInvokeError as exc:
            last_error = exc
            if log_context:
                log_llm_attempt(
                    call_type=log_context["call_type"],
                    segment_id=log_context.get("segment_id"),
                    attempt=attempt,
                    success=False,
                    response_raw=str(exc),
                    validation_error=str(exc),
                )
            continue

        payload = result.structured_output
        if not isinstance(payload, dict):
            last_error = AgentInvokeError(f"{call_type} missing structured output")
            if log_context:
                log_llm_attempt(
                    call_type=log_context["call_type"],
                    segment_id=log_context.get("segment_id"),
                    attempt=attempt,
                    success=False,
                    response_raw="",
                    validation_error=str(last_error),
                    duration_ms=result.duration_ms,
                )
            continue

        data = normalize(payload) if normalize is not None else payload
        response_raw = json.dumps(payload, ensure_ascii=False)
        try:
            validated = model_type.model_validate(data)
            if log_context:
                parsed = validated.model_dump_json()
                log_llm_attempt(
                    call_type=log_context["call_type"],
                    segment_id=log_context.get("segment_id"),
                    attempt=attempt,
                    success=True,
                    response_raw=response_raw,
                    response_parsed=parsed,
                    duration_ms=result.duration_ms,
                )
                log_llm_response(
                    call_type=log_context["call_type"],
                    segment_id=log_context.get("segment_id"),
                    response=parsed,
                )
            return validated
        except ValidationError as exc:
            last_error = exc
            if log_context:
                log_llm_attempt(
                    call_type=log_context["call_type"],
                    segment_id=log_context.get("segment_id"),
                    attempt=attempt,
                    success=False,
                    response_raw=response_raw,
                    validation_error=str(exc),
                    duration_ms=result.duration_ms,
                )
            continue

    raise LLMExtractionError(f"LLM JSON extraction failed after retries: {last_error}")
