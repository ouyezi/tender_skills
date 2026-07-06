from __future__ import annotations

import json
from typing import Any

from doc_chunk.llm.client import LLMClient

from agent_platform.models import AgentInvokeError, AgentInvokeResult
from tender_insights.legal.prompts import SYSTEM_PROMPT, build_user_prompt


def _section_path_list(section_path: str) -> list[str]:
    """将 agent 合同中的 section_path 字符串还原为列表。"""
    text = str(section_path or "").strip()
    if not text or text == "(root)":
        return []
    return [part.strip() for part in text.split(" > ") if part.strip()]


def invoke_legal_section_review(llm_client: LLMClient, input: dict[str, Any]) -> AgentInvokeResult:
    """Local handler：法务章节审核。"""
    for key in ("section_title", "section_path", "markdown"):
        if key not in input:
            raise AgentInvokeError(f"legal_section_review input missing field: {key}")

    section_title = str(input["section_title"])
    section_path = str(input["section_path"])
    markdown = str(input["markdown"])
    user_content = build_user_prompt(
        section_title,
        _section_path_list(section_path),
        markdown,
    )
    raw = llm_client.complete(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        response_format="json",
        timeout=120.0,
    )
    try:
        structured = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AgentInvokeError(f"legal_section_review local handler invalid JSON: {exc}") from exc
    if not isinstance(structured, dict):
        raise AgentInvokeError("legal_section_review local handler expected JSON object")

    return AgentInvokeResult(
        call_type="legal_section_review",
        status="completed",
        structured_output=structured,
        text_output=None,
        raw_response={"status": "completed", "structuredOutput": structured},
    )
