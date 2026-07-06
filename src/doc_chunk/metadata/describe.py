from __future__ import annotations

from agent_platform.client import AgentClient
from agent_platform.factory import create_agent_client_from_env
from agent_platform.models import AgentInvokeError
from doc_chunk.llm.client import LLMClient


def describe_chunk(
    *,
    title: str,
    markdown: str,
    llm_client: LLMClient | None = None,
    agent_client: AgentClient | None = None,
) -> str | None:
    """通过 chunk_describe agent 生成分块摘要。"""
    client = agent_client
    if client is None and llm_client is not None:
        client = create_agent_client_from_env(llm_client=llm_client)
    if client is None:
        return None

    try:
        result = client.invoke(
            "chunk_describe",
            {"title": title, "markdown": markdown},
        )
    except AgentInvokeError:
        return None
    text = (result.text_output or "").strip()
    return text or None
