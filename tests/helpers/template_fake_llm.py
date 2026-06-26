from __future__ import annotations

from doc_chunk.llm.client import FakeLLMClient
from doc_chunk.llm.completion import LLMCompletionResult


class TemplateFakeLLM(FakeLLMClient):
    def __init__(self, *, plan_json: str, extract_json: str) -> None:
        super().__init__()
        self._plan_json = plan_json
        self._extract_json = extract_json

    def complete_with_meta(
        self,
        messages: list[dict[str, str]],
        *,
        response_format: str = "text",
        timeout: float | None = None,
    ) -> LLMCompletionResult:
        user = " ".join(str(m.get("content", "")) for m in messages if m.get("role") == "user")
        if "模版正文分片" in user:
            text = self._extract_json
        elif "分片摘要" in user or "shard" in user.lower():
            text = self._plan_json
        else:
            text = self._extract_json
        self.calls.append({"messages": messages, "response_format": response_format, "timeout": timeout})
        return LLMCompletionResult(text=text)

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
