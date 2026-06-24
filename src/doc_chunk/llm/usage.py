from __future__ import annotations

from typing import Any


def _serialize_value(value: object) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(exclude_none=True)  # type: ignore[union-attr]
    if isinstance(value, dict):
        return {str(key): _serialize_value(item) for key, item in value.items()}
    if isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "__dict__"):
        return {
            key: _serialize_value(item)
            for key, item in vars(value).items()
            if item is not None and not key.startswith("_")
        }
    return value


def serialize_usage(usage: object | None) -> dict[str, Any] | None:
    if usage is None:
        return None
    if isinstance(usage, dict):
        return {str(key): _serialize_value(item) for key, item in usage.items()}
    if hasattr(usage, "model_dump"):
        return usage.model_dump(exclude_none=True)  # type: ignore[union-attr]
    data: dict[str, Any] = {}
    for key in (
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "prompt_tokens_details",
        "completion_tokens_details",
    ):
        if hasattr(usage, key):
            value = getattr(usage, key)
            if value is not None:
                data[key] = _serialize_value(value)
    return data or None
