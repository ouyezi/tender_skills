from __future__ import annotations

from typing import Any


def _coerce_structure_dict(node: dict[str, Any], *, order_start: int = 1) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for order, (title, child) in enumerate(node.items(), start=order_start):
        entry: dict[str, Any] = {
            "order": order,
            "title": str(title),
            "mandatory": True,
            "children": [],
        }
        if isinstance(child, dict):
            entry["children"] = _coerce_structure_dict(child, order_start=1)
        result.append(entry)
    return result


def _coerce_structure(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return _coerce_structure_dict(value)
    return []


def normalize_interpretation_llm_data(data: dict[str, Any]) -> dict[str, Any]:
    """Coerce common LLM shape mistakes before Pydantic validation."""
    for item in data.get("directory_requirements", []):
        if not isinstance(item, dict):
            continue
        if "structure" in item:
            item["structure"] = _coerce_structure(item.get("structure"))
    return data
