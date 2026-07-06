from __future__ import annotations

import json
from typing import Any

from doc_chunk.llm.client import LLMClient

from agent_platform.models import AgentInvokeError, AgentInvokeResult
from tender_insights.gen_catalog.prompts import GEN_CATALOG_NODE_SYSTEM


def invoke_gen_catalog_node_plan(llm_client: LLMClient, input: dict[str, Any]) -> AgentInvokeResult:
    """Local handler：目录节点优化评估。"""
    if "context_json" not in input:
        raise AgentInvokeError("gen_catalog_node_plan input missing field: context_json")

    context_json = str(input["context_json"])
    raw = llm_client.complete(
        [
            {"role": "system", "content": GEN_CATALOG_NODE_SYSTEM},
            {"role": "user", "content": context_json},
        ],
        response_format="json",
        timeout=120.0,
    )
    try:
        structured = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AgentInvokeError(f"gen_catalog_node_plan local handler invalid JSON: {exc}") from exc
    if not isinstance(structured, dict):
        raise AgentInvokeError("gen_catalog_node_plan local handler expected JSON object")

    return AgentInvokeResult(
        call_type="gen_catalog_node_plan",
        status="completed",
        structured_output=structured,
        text_output=None,
        raw_response={"status": "completed", "structuredOutput": structured},
    )
