from __future__ import annotations

import json
from typing import Any

from doc_chunk.llm.client import LLMClient

from agent_platform.models import AgentInvokeError, AgentInvokeResult
from tender_insights.interpret.prompts import OVERVIEW_SYSTEM_PROMPT, build_overview_prompt


def invoke_interpret_overview(llm_client: LLMClient, input: dict[str, Any]) -> AgentInvokeResult:
    """Local handler：解读概要合成。"""
    if "items_json" not in input:
        raise AgentInvokeError("interpret_overview input missing field: items_json")

    items_json = str(input["items_json"])
    user_content = build_overview_prompt(items_json)
    raw = llm_client.complete(
        [
            {"role": "system", "content": OVERVIEW_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        response_format="json",
        timeout=120.0,
    )
    try:
        structured = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AgentInvokeError(f"interpret_overview local handler invalid JSON: {exc}") from exc
    if not isinstance(structured, dict):
        raise AgentInvokeError("interpret_overview local handler expected JSON object")

    return AgentInvokeResult(
        call_type="interpret_overview",
        status="completed",
        structured_output=structured,
        text_output=None,
        raw_response={"status": "completed", "structuredOutput": structured},
    )
