from __future__ import annotations

import os
from typing import Any

from doc_chunk.llm import openai_client
from doc_chunk.llm.client import LLMClient

from agent_platform.backends.local import LocalBackend
from agent_platform.backends.platform import PlatformBackend
from agent_platform.client import AgentClient


def create_agent_client_from_env(
    *,
    llm_client: LLMClient | None = None,
    ocr_client: Any | None = None,
) -> AgentClient:
    """按 AGENT_INVOKE_MODE 创建 AgentClient（local / platform）。"""
    mode = os.environ.get("AGENT_INVOKE_MODE", "local").strip().lower()
    if mode == "platform":
        base_url = os.environ.get("AGENT_PLATFORM_BASE_URL", "http://localhost:8000")
        return AgentClient(PlatformBackend(base_url=base_url))
    if mode != "local":
        raise ValueError(f"unsupported AGENT_INVOKE_MODE: {mode}")
    client = llm_client or openai_client.create_llm_client_from_env()
    return AgentClient(LocalBackend(llm_client=client, ocr_client=ocr_client))
