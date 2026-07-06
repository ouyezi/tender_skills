from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from agent_platform.client import AgentClient
from agent_platform.models import AgentInvokeError

T = TypeVar("T", bound=BaseModel)


def invoke_json_model(
    agent_client: AgentClient,
    call_type: str,
    input: dict[str, Any],
    model_type: type[T],
    *,
    max_retries: int = 2,
    normalize: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> T:
    """调用 agent 并将 structured_output 校验为 pydantic 模型（同 input 盲重试）。"""
    last_error: Exception | None = None
    for _ in range(max_retries + 1):
        try:
            result = agent_client.invoke(call_type, input)
        except AgentInvokeError as exc:
            last_error = exc
            continue

        payload = result.structured_output
        if not isinstance(payload, dict):
            last_error = AgentInvokeError(f"{call_type} missing structured output")
            continue

        data = payload
        if normalize is not None:
            data = normalize(data)

        try:
            return model_type.model_validate(data)
        except ValidationError as exc:
            last_error = exc
            continue

    raise AgentInvokeError(
        f"{call_type} JSON extraction failed after retries: {last_error}"
    )


def invoke_text(
    agent_client: AgentClient,
    call_type: str,
    input: dict[str, Any],
    *,
    max_retries: int = 0,
) -> str:
    """调用 agent 并返回 text_output（同 input 盲重试）。"""
    last_error: Exception | None = None
    for _ in range(max_retries + 1):
        try:
            result = agent_client.invoke(call_type, input)
        except AgentInvokeError as exc:
            last_error = exc
            continue
        text = (result.text_output or "").strip()
        if text:
            return text
        last_error = AgentInvokeError(f"{call_type} returned empty text_output")

    raise AgentInvokeError(f"{call_type} text extraction failed after retries: {last_error}")
