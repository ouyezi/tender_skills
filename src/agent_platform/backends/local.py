from __future__ import annotations

from typing import Any, Callable, Protocol

from doc_chunk.llm.client import LLMClient

from agent_platform.handlers.chunk_classify import invoke_chunk_classify
from agent_platform.handlers.chunk_describe import invoke_chunk_describe
from agent_platform.handlers.ocr_image_recognize import invoke_ocr_image_recognize
from agent_platform.handlers.outline_refine import invoke_outline_refine
from agent_platform.models import AgentInvokeError, AgentInvokeResult


class SupportsImageUrlOcr(Protocol):
    """OCR 客户端最小协议。"""

    def recognize_image_url(self, image_url: str) -> str:
        """按图片 URL / data URI 识别文字。"""
        ...


Handler = Callable[[LLMClient, dict[str, Any]], AgentInvokeResult]

_HANDLERS: dict[str, Handler] = {
    "outline_refine": invoke_outline_refine,
    "chunk_classify": invoke_chunk_classify,
    "chunk_describe": invoke_chunk_describe,
}


class LocalBackend:
    """Local 模式：按 call_type 分发到 prompt + LLM/OCR handler。"""

    def __init__(
        self,
        *,
        llm_client: LLMClient,
        ocr_client: SupportsImageUrlOcr | None = None,
    ) -> None:
        self._llm_client = llm_client
        self._ocr_client = ocr_client

    def invoke(self, call_type: str, input: dict[str, Any]) -> AgentInvokeResult:
        """按 call_type 调用对应 local handler。"""
        if call_type == "ocr_image_recognize":
            if self._ocr_client is None:
                raise AgentInvokeError(
                    "ocr_image_recognize requires ocr_client in local mode"
                )
            return invoke_ocr_image_recognize(self._ocr_client, input)

        handler = _HANDLERS.get(call_type)
        if handler is None:
            raise AgentInvokeError(f"no local handler registered for call_type: {call_type}")
        return handler(self._llm_client, input)
