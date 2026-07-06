from __future__ import annotations

from typing import Any

from doc_chunk.llm.client import LLMClient

from agent_platform.models import AgentInvokeError, AgentInvokeResult

_SYSTEM_PROMPT = (
    "你是文档摘要助手。根据用户提供的文档块生成1-3句中文摘要，突出核心信息，避免臆测。"
)


def invoke_chunk_describe(llm_client: LLMClient, input: dict[str, Any]) -> AgentInvokeResult:
    """Local handler：分块摘要生成（纯文本）。"""
    for key in ("title", "markdown"):
        if key not in input:
            raise AgentInvokeError(f"chunk_describe input missing field: {key}")

    title = str(input["title"])
    markdown = str(input["markdown"])
    user_content = (
        "请基于以下文档块生成1-3句中文摘要，突出核心信息，避免臆测。\n"
        f"标题: {title}\n"
        "正文:\n"
        f"{markdown[:4000]}"
    )
    text = llm_client.complete(
        [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        response_format="text",
        timeout=60.0,
    ).strip()

    return AgentInvokeResult(
        call_type="chunk_describe",
        status="completed",
        structured_output=None,
        text_output=text,
        raw_response={"status": "completed", "output": text},
    )
