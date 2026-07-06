from __future__ import annotations

import json
from typing import Any

from doc_chunk.llm.client import LLMClient

from agent_platform.models import AgentInvokeError, AgentInvokeResult
from tender_insights.template.prompts import TEMPLATE_PLAN_SYSTEM, build_plan_user_prompt


def invoke_template_plan(llm_client: LLMClient, input: dict[str, Any]) -> AgentInvokeResult:
    """Local handler：模板提取计划。"""
    for key in ("doc_title", "shard_summaries_json"):
        if key not in input:
            raise AgentInvokeError(f"template_plan input missing field: {key}")

    doc_title = str(input["doc_title"])
    try:
        shard_summaries = json.loads(str(input["shard_summaries_json"]))
    except json.JSONDecodeError as exc:
        raise AgentInvokeError(f"template_plan shard_summaries_json invalid JSON: {exc}") from exc
    if not isinstance(shard_summaries, list):
        raise AgentInvokeError("template_plan shard_summaries_json must be a JSON array")

    raw = llm_client.complete(
        [
            {"role": "system", "content": TEMPLATE_PLAN_SYSTEM},
            {
                "role": "user",
                "content": build_plan_user_prompt(
                    doc_title=doc_title,
                    shard_summaries=shard_summaries,
                ),
            },
        ],
        response_format="json",
        timeout=120.0,
    )
    try:
        structured = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AgentInvokeError(f"template_plan local handler invalid JSON: {exc}") from exc
    if not isinstance(structured, dict):
        raise AgentInvokeError("template_plan local handler expected JSON object")

    return AgentInvokeResult(
        call_type="template_plan",
        status="completed",
        structured_output=structured,
        text_output=None,
        raw_response={"status": "completed", "structuredOutput": structured},
    )
