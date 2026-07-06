from __future__ import annotations

import json
from typing import Any

from doc_chunk.llm.client import LLMClient

from agent_platform.models import AgentInvokeError, AgentInvokeResult
from tender_insights.brief.prompts import SINGLE_SYSTEM_PROMPT, build_single_prompt

_DEFAULT_MAX_CHARS = 500


def invoke_brief_single(llm_client: LLMClient, input: dict[str, Any]) -> AgentInvokeResult:
    """Local handler：短文档一次性提取招标基础概要。"""
    if "markdown" not in input:
        raise AgentInvokeError("brief_single input missing field: markdown")

    markdown = str(input["markdown"])
    max_chars = int(input.get("max_chars") or _DEFAULT_MAX_CHARS)
    raw = llm_client.complete(
        [
            {"role": "system", "content": SINGLE_SYSTEM_PROMPT.format(max_chars=max_chars)},
            {"role": "user", "content": build_single_prompt(markdown=markdown, max_chars=max_chars)},
        ],
        response_format="json",
        timeout=120.0,
    )
    try:
        structured = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AgentInvokeError(f"brief_single local handler invalid JSON: {exc}") from exc
    if not isinstance(structured, dict):
        raise AgentInvokeError("brief_single local handler expected JSON object")

    return AgentInvokeResult(
        call_type="brief_single",
        status="completed",
        structured_output=structured,
        text_output=None,
        raw_response={"status": "completed", "structuredOutput": structured},
    )
