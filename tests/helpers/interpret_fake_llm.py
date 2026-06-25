from __future__ import annotations

from doc_chunk.llm.client import FakeLLMClient
from doc_chunk.llm.completion import LLMCompletionResult


class InterpretFakeLLM(FakeLLMClient):
    def __init__(self, *, segment_json: str, overview_json: str) -> None:
        super().__init__()
        self._segment_json = segment_json
        self._overview_json = overview_json

    def _response_text(self, messages: list[dict[str, str]]) -> str:
        user_text = " ".join(
            str(m.get("content", "")) for m in messages if m.get("role") == "user"
        )
        if "已提取明细" in user_text:
            return self._overview_json
        return self._segment_json

    def complete_with_meta(
        self,
        messages: list[dict[str, str]],
        *,
        response_format: str = "text",
        timeout: float | None = None,
    ) -> LLMCompletionResult:
        return LLMCompletionResult(text=self._response_text(messages))

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        response_format: str = "text",
        timeout: float | None = None,
    ) -> str:
        return self.complete_with_meta(
            messages,
            response_format=response_format,
            timeout=timeout,
        ).text
