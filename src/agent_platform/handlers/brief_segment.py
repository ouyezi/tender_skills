from __future__ import annotations

import json
from typing import Any

from doc_chunk.llm.client import LLMClient

from agent_platform.models import AgentInvokeError, AgentInvokeResult
from tender_insights.brief.prompts import EXTRACT_SYSTEM_PROMPT, build_extract_prompt


def invoke_brief_segment(llm_client: LLMClient, input: dict[str, Any]) -> AgentInvokeResult:
    """Local handler：长文档分片事实提取。"""
    for key in ("segment_index", "segment_total", "markdown"):
        if key not in input:
            raise AgentInvokeError(f"brief_segment input missing field: {key}")

    segment_index = int(input["segment_index"])
    segment_total = int(input["segment_total"])
    markdown = str(input["markdown"])
    raw = llm_client.complete(
        [
            {"role": "system", "content": EXTRACT_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": build_extract_prompt(
                    segment_index=segment_index,
                    segment_total=segment_total,
                    markdown=markdown,
                ),
            },
        ],
        response_format="json",
        timeout=120.0,
    )
    try:
        structured = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AgentInvokeError(f"brief_segment local handler invalid JSON: {exc}") from exc
    if not isinstance(structured, dict):
        raise AgentInvokeError("brief_segment local handler expected JSON object")

    return AgentInvokeResult(
        call_type="brief_segment",
        status="completed",
        structured_output=structured,
        text_output=None,
        raw_response={"status": "completed", "structuredOutput": structured},
    )
