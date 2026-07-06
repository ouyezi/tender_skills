from __future__ import annotations

import json
from typing import Any

from doc_chunk.llm.client import LLMClient

from agent_platform.models import AgentInvokeError, AgentInvokeResult

_SYSTEM_PROMPT = (
    "你是文档分块分类助手。根据用户提供的标题与正文，输出 JSON："
    "knowledge_type, chapter_type, confidence, rationale。"
)


def invoke_chunk_classify(llm_client: LLMClient, input: dict[str, Any]) -> AgentInvokeResult:
    """Local handler：分块知识分类（structured JSON）。"""
    for key in ("title", "markdown"):
        if key not in input:
            raise AgentInvokeError(f"chunk_classify input missing field: {key}")

    title = str(input["title"])
    markdown = str(input["markdown"])
    user_content = (
        "请将以下文本分类为 scheme/product/qualification/other 或自定义标签。\n"
        "返回JSON：knowledge_type, chapter_type, confidence, rationale。\n"
        f"{title}\n{markdown[:3000]}"
    )
    raw = llm_client.complete(
        [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        response_format="json",
        timeout=60.0,
    )
    try:
        structured = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AgentInvokeError(f"chunk_classify local handler invalid JSON: {exc}") from exc
    if not isinstance(structured, dict):
        raise AgentInvokeError("chunk_classify local handler expected JSON object")

    return AgentInvokeResult(
        call_type="chunk_classify",
        status="completed",
        structured_output=structured,
        text_output=None,
        raw_response={"status": "completed", "structuredOutput": structured},
    )
