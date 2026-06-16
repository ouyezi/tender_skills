from __future__ import annotations

import os

from openai import OpenAI

from doc_chunk.errors import LLMUnavailableError
from doc_chunk.llm.client import LLMClient

# Preset profiles — aligned with tender_knowledge (LLM_PROVIDER=qwen|openai).
_LLM_PRESETS: dict[str, dict[str, str]] = {
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
    },
}


def resolve_llm_settings_from_env() -> tuple[str, str, str]:
    """Return (api_key, model, base_url) from environment."""
    api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise LLMUnavailableError("LLM_API_KEY or OPENAI_API_KEY is required for LLM operations")

    provider = (os.getenv("LLM_PROVIDER") or "qwen").lower()
    preset = _LLM_PRESETS.get(provider, _LLM_PRESETS["qwen"])

    model = (
        os.getenv("LLM_MODEL")
        or os.getenv("DOC_CHUNK_LLM_MODEL")
        or preset["model"]
    )
    base_url = (
        os.getenv("LLM_BASE_URL")
        or os.getenv("OPENAI_API_BASE")
        or preset["base_url"]
    )
    return api_key, model, base_url


class OpenAILLMClient:
    def __init__(self, *, model: str, api_key: str, base_url: str | None = None) -> None:
        self.model = model
        self.base_url = base_url
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
    api_key, model, base_url = resolve_llm_settings_from_env()
    return OpenAILLMClient(model=model, api_key=api_key, base_url=base_url)
