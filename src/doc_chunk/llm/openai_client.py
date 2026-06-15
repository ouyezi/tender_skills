from __future__ import annotations

import os

from openai import OpenAI

from doc_chunk.errors import LLMUnavailableError
from doc_chunk.llm.client import LLMClient


class OpenAILLMClient:
    def __init__(self, *, model: str, api_key: str, base_url: str | None = None) -> None:
        self.model = model
        if base_url:
            self._client = OpenAI(api_key=api_key, base_url=base_url)
        else:
            self._client = OpenAI(api_key=api_key)

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        response_format: str = "text",
        timeout: float = 60.0,
    ) -> str:
        kwargs: dict[str, object] = {
            "model": self.model,
            "messages": messages,
            "timeout": timeout,
        }
        if response_format == "json":
            kwargs["response_format"] = {"type": "json_object"}

        response = self._client.chat.completions.create(**kwargs)
        message = response.choices[0].message.content
        return message or ""


def create_llm_client_from_env() -> LLMClient:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise LLMUnavailableError("OPENAI_API_KEY is required for LLM operations")

    model = os.getenv("DOC_CHUNK_LLM_MODEL", "gpt-4o-mini")
    base_url = os.getenv("OPENAI_API_BASE")
    return OpenAILLMClient(model=model, api_key=api_key, base_url=base_url)
