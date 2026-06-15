from __future__ import annotations

from typing import Literal, Protocol


class LLMClient(Protocol):
    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        response_format: Literal["text", "json"] = "text",
        timeout: float = 60.0,
    ) -> str: ...


class FakeLLMClient:
    def __init__(self, responses: list[str] | None = None, *, default_response: str = "") -> None:
        self._responses = list(responses or [])
        self.default_response = default_response
        self.calls: list[dict[str, object]] = []

    def push_response(self, response: str) -> None:
        self._responses.append(response)

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        response_format: Literal["text", "json"] = "text",
        timeout: float = 60.0,
    ) -> str:
        self.calls.append(
            {
                "messages": messages,
                "response_format": response_format,
                "timeout": timeout,
            }
        )
        if self._responses:
            return self._responses.pop(0)
        return self.default_response
