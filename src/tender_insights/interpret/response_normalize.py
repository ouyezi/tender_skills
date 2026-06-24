from __future__ import annotations

from typing import Any

_CONFIDENCE_LABELS = {"high": 0.9, "medium": 0.7, "low": 0.5}
_DEFAULT_CONFIDENCE = 0.8


def _coerce_confidence(value: Any, *, default: float = _DEFAULT_CONFIDENCE) -> float:
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(max(0.0, min(1.0, value)))
    if isinstance(value, str):
        label = value.strip().lower()
        if label in _CONFIDENCE_LABELS:
            return _CONFIDENCE_LABELS[label]
        try:
            return float(max(0.0, min(1.0, float(label))))
        except ValueError:
            return default
    return default


def _coerce_weight(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, (int, float)):
        if float(value).is_integer():
            return str(int(value))
        return str(value)
    return str(value)


def _coerce_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item is not None and str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


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


def _normalize_structure_orders(nodes: list[Any]) -> None:
    for node in nodes:
        if not isinstance(node, dict):
            continue
        order = node.get("order")
        if isinstance(order, float):
            node["order"] = int(order)
        elif isinstance(order, str):
            try:
                node["order"] = int(float(order.strip()))
            except ValueError:
                node["order"] = 1
        elif order is None:
            node["order"] = 1
        children = node.get("children")
        if isinstance(children, list):
            _normalize_structure_orders(children)


def _coerce_directory_requirements(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _fallback_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return "（未提供）"


def _normalize_base_fields(item: dict[str, Any], *, default_section_path: list[str]) -> None:
    item["section_path"] = _coerce_string_list(item.get("section_path")) or list(default_section_path)
    item["confidence"] = _coerce_confidence(item.get("confidence"))
    item["source_excerpt"] = _fallback_text(
        item.get("source_excerpt"),
        item.get("criteria"),
        item.get("summary"),
        item.get("trigger_condition"),
        item.get("title"),
    )


def _normalize_disqualification_item(item: dict[str, Any], *, default_section_path: list[str]) -> None:
    if not isinstance(item, dict):
        return
    _normalize_base_fields(item, default_section_path=default_section_path)
    item["summary"] = _fallback_text(item.get("summary"), item.get("trigger_condition"), item.get("title"))
    item["trigger_condition"] = _fallback_text(item.get("trigger_condition"), item.get("summary"), item.get("title"))


def _normalize_scoring_child(item: dict[str, Any]) -> None:
    if not isinstance(item, dict):
        return
    item["source_excerpt"] = _fallback_text(item.get("source_excerpt"), item.get("criteria"), item.get("title"))
    item["criteria"] = _fallback_text(item.get("criteria"), item.get("title"))


def _normalize_scoring_item(item: dict[str, Any], *, default_section_path: list[str]) -> None:
    if not isinstance(item, dict):
        return
    _normalize_base_fields(item, default_section_path=default_section_path)
    item["summary"] = _fallback_text(item.get("summary"), item.get("criteria"), item.get("title"))
    item["criteria"] = _fallback_text(item.get("criteria"), item.get("summary"), item.get("title"))
    item["weight"] = _coerce_weight(item.get("weight"))
    for child in item.get("children", []):
        _normalize_scoring_child(child)


def _normalize_bid_risk_item(item: dict[str, Any], *, default_section_path: list[str]) -> None:
    if not isinstance(item, dict):
        return
    _normalize_base_fields(item, default_section_path=default_section_path)
    item["summary"] = _fallback_text(item.get("summary"), item.get("risk_category"), item.get("title"))
    severity = item.get("severity")
    if isinstance(severity, str):
        item["severity"] = severity.strip().lower()


def _normalize_directory_item(
    item: dict[str, Any],
    *,
    default_section_path: list[str],
    index: int = 0,
) -> None:
    if not isinstance(item, dict):
        return
    sections = _coerce_string_list(item.get("required_sections"))
    if not str(item.get("title") or "").strip():
        item["title"] = sections[0] if sections else f"目录要求 {index + 1}"
    if not str(item.get("id") or "").strip():
        item["id"] = f"dir-{index + 1:03d}"
    _normalize_base_fields(item, default_section_path=default_section_path)
    item["required_sections"] = sections
    if "structure" in item:
        item["structure"] = _coerce_structure(item.get("structure"))
        _normalize_structure_orders(item["structure"])
    if "inferred" not in item:
        item["inferred"] = False
    if "mandatory" not in item:
        item["mandatory"] = True


def normalize_interpretation_llm_data(
    data: dict[str, Any],
    *,
    section_path: list[str] | None = None,
) -> dict[str, Any]:
    """Coerce common LLM shape mistakes before Pydantic validation."""
    default_section_path = list(section_path or [])
    for item in data.get("disqualification_items", []):
        _normalize_disqualification_item(item, default_section_path=default_section_path)
    for item in data.get("scoring_items", []):
        _normalize_scoring_item(item, default_section_path=default_section_path)
    for item in data.get("bid_risk_items", []):
        _normalize_bid_risk_item(item, default_section_path=default_section_path)
    directory_requirements = _coerce_directory_requirements(data.get("directory_requirements"))
    data["directory_requirements"] = directory_requirements
    for index, item in enumerate(directory_requirements):
        _normalize_directory_item(item, default_section_path=default_section_path, index=index)
    return data
