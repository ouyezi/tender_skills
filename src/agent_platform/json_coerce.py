from __future__ import annotations

import json
import re
from typing import Any

_JSON_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def parse_json_object(text: str) -> dict[str, Any] | None:
    stripped = (text or "").strip()
    if not stripped:
        return None
    candidates = [stripped]
    candidates.extend(m.group(1).strip() for m in _JSON_FENCE.finditer(stripped) if m.group(1).strip())
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        candidates.append(stripped[start : end + 1])
    for candidate in candidates:
        try:
            obj = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def coerce_structured_output(resp: dict[str, Any]) -> dict[str, Any] | None:
    structured = resp.get("structuredOutput")
    if isinstance(structured, dict):
        return structured
    return parse_json_object(str(resp.get("output") or ""))
