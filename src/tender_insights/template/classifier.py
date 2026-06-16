from __future__ import annotations

from typing import Literal

TemplateType = Literal["commitment", "authorization", "declaration", "other"]


def classify_template(title: str, markdown: str) -> tuple[TemplateType, str, float]:
    text = f"{title}\n{markdown[:500]}"
    if "承诺书" in text or "承诺" in text:
        return "commitment", "承诺书", 0.95
    if "授权" in text:
        return "authorization", "授权书", 0.95
    if "声明" in text:
        return "declaration", "声明函", 0.95
    return "other", "其他", 0.6
