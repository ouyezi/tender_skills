from __future__ import annotations

import json
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from doc_chunk.llm.client import LLMClient
from tender_insights.errors import LLMExtractionError

T = TypeVar("T", bound=BaseModel)


def extract_json_model(
    client: LLMClient,
    messages: list[dict[str, str]],
    model_type: type[T],
    *,
    max_retries: int = 2,
) -> T:
    last_error: Exception | None = None
    for _ in range(max_retries + 1):
        raw = client.complete(messages, response_format="json")
        try:
            data = json.loads(raw)
            return model_type.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as exc:
            last_error = exc
            messages = messages + [
                {"role": "user", "content": f"Previous JSON invalid: {exc}. Return valid JSON only."},
            ]
    raise LLMExtractionError(f"LLM JSON extraction failed after retries: {last_error}")
