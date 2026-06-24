from __future__ import annotations

import json
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from doc_chunk.llm.client import LLMClient
from tender_insights.errors import LLMExtractionError
from tender_insights.interpret.llm_logging import log_llm_attempt, log_llm_response
from tender_insights.interpret.response_normalize import normalize_interpretation_llm_data

T = TypeVar("T", bound=BaseModel)


def extract_json_model(
    client: LLMClient,
    messages: list[dict[str, str]],
    model_type: type[T],
    *,
    max_retries: int = 2,
    normalize_context: dict[str, Any] | None = None,
    log_context: dict[str, Any] | None = None,
) -> T:
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        completion = client.complete_with_meta(messages, response_format="json")
        raw = completion.text
        try:
            data = json.loads(raw)
            if model_type.__name__ == "InterpretationLLMResponse":
                data = normalize_interpretation_llm_data(
                    data,
                    section_path=(normalize_context or {}).get("section_path"),
                )
            validated = model_type.model_validate(data)
            if log_context:
                parsed = validated.model_dump_json()
                log_llm_attempt(
                    call_type=log_context["call_type"],
                    segment_id=log_context.get("segment_id"),
                    attempt=attempt,
                    success=True,
                    response_raw=raw,
                    response_parsed=parsed,
                    usage=completion.usage,
                    model=completion.model,
                    finish_reason=completion.finish_reason,
                    stream=completion.stream,
                    duration_ms=completion.duration_ms,
                )
                log_llm_response(
                    call_type=log_context["call_type"],
                    segment_id=log_context.get("segment_id"),
                    response=parsed,
                )
            return validated
        except (json.JSONDecodeError, ValidationError) as exc:
            last_error = exc
            if log_context:
                log_llm_attempt(
                    call_type=log_context["call_type"],
                    segment_id=log_context.get("segment_id"),
                    attempt=attempt,
                    success=False,
                    response_raw=raw,
                    validation_error=str(exc),
                    usage=completion.usage,
                    model=completion.model,
                    finish_reason=completion.finish_reason,
                    stream=completion.stream,
                    duration_ms=completion.duration_ms,
                )
            messages = messages + [
                {"role": "user", "content": f"Previous JSON invalid: {exc}. Return valid JSON only."},
            ]
    raise LLMExtractionError(f"LLM JSON extraction failed after retries: {last_error}")
