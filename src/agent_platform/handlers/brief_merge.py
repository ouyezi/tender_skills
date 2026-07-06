from __future__ import annotations

import json
from typing import Any

from doc_chunk.llm.client import LLMClient

from agent_platform.models import AgentInvokeError, AgentInvokeResult
from tender_insights.brief.prompts import MERGE_SYSTEM_PROMPT, build_merge_prompt

_DEFAULT_MAX_CHARS = 500


def invoke_brief_merge(llm_client: LLMClient, input: dict[str, Any]) -> AgentInvokeResult:
    """Local handler：合并分片事实生成最终概要。"""
    if "partials_json" not in input:
        raise AgentInvokeError("brief_merge input missing field: partials_json")

    partials_json = str(input["partials_json"])
    max_chars = int(input.get("max_chars") or _DEFAULT_MAX_CHARS)
    try:
        partials = json.loads(partials_json)
    except json.JSONDecodeError as exc:
        raise AgentInvokeError(f"brief_merge partials_json invalid JSON: {exc}") from exc
    if not isinstance(partials, list):
        raise AgentInvokeError("brief_merge partials_json must be a JSON array")

    raw = llm_client.complete(
        [
            {"role": "system", "content": MERGE_SYSTEM_PROMPT.format(max_chars=max_chars)},
            {
                "role": "user",
                "content": build_merge_prompt(partials=partials, max_chars=max_chars),
            },
        ],
        response_format="json",
        timeout=120.0,
    )
    try:
        structured = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AgentInvokeError(f"brief_merge local handler invalid JSON: {exc}") from exc
    if not isinstance(structured, dict):
        raise AgentInvokeError("brief_merge local handler expected JSON object")

    return AgentInvokeResult(
        call_type="brief_merge",
        status="completed",
        structured_output=structured,
        text_output=None,
        raw_response={"status": "completed", "structuredOutput": structured},
    )
