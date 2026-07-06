from __future__ import annotations

import json
from typing import Any

from doc_chunk.llm.client import LLMClient

from agent_platform.models import AgentInvokeError, AgentInvokeResult
from tender_insights.template.prompts import TEMPLATE_EXTRACT_SYSTEM


def invoke_template_extract(llm_client: LLMClient, input: dict[str, Any]) -> AgentInvokeResult:
    """Local handler：模板正文提取。"""
    for key in ("shard_id", "section_path", "strategy", "char_count", "markdown"):
        if key not in input:
            raise AgentInvokeError(f"template_extract input missing field: {key}")

    shard_id = str(input["shard_id"])
    section_path = str(input["section_path"])
    strategy = str(input["strategy"])
    char_count = int(input["char_count"])
    markdown = str(input["markdown"])

    user_content = (
        f"模版正文分片编号: {shard_id}\n"
        f"章节路径: {section_path}\n"
        f"分片策略: {strategy}\n"
        f"本分片约 {char_count} 字。\n"
        "请识别本片段内所有投标提交模版，在 markdown 字段输出完整模版正文。\n\n"
        f"正文:\n{markdown}"
    )
    raw = llm_client.complete(
        [
            {"role": "system", "content": TEMPLATE_EXTRACT_SYSTEM},
            {"role": "user", "content": user_content},
        ],
        response_format="json",
        timeout=120.0,
    )
    try:
        structured = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AgentInvokeError(f"template_extract local handler invalid JSON: {exc}") from exc
    if not isinstance(structured, dict):
        raise AgentInvokeError("template_extract local handler expected JSON object")

    return AgentInvokeResult(
        call_type="template_extract",
        status="completed",
        structured_output=structured,
        text_output=None,
        raw_response={"status": "completed", "structuredOutput": structured},
    )
