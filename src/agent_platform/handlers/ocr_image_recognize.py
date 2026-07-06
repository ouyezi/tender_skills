from __future__ import annotations

from typing import Any, Protocol

from agent_platform.models import AgentInvokeError, AgentInvokeResult


class SupportsImageUrlOcr(Protocol):
    """OCR 客户端最小协议。"""

    def recognize_image_url(self, image_url: str) -> str:
        """按图片 URL / data URI 识别文字。"""
        ...


def invoke_ocr_image_recognize(
    ocr_client: SupportsImageUrlOcr,
    input: dict[str, Any],
) -> AgentInvokeResult:
    """Local handler：图片 OCR 识别（纯文本）。"""
    if "image_url" not in input:
        raise AgentInvokeError("ocr_image_recognize input missing field: image_url")

    image_url = str(input["image_url"] or "").strip()
    if not image_url:
        raise AgentInvokeError("ocr_image_recognize image_url is empty")

    text = (ocr_client.recognize_image_url(image_url) or "").strip()
    return AgentInvokeResult(
        call_type="ocr_image_recognize",
        status="completed",
        structured_output=None,
        text_output=text,
        raw_response={"status": "completed", "output": text},
    )
