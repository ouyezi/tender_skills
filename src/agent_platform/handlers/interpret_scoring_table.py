from __future__ import annotations

import json
from typing import Any

from doc_chunk.llm.client import LLMClient

from agent_platform.models import AgentInvokeError, AgentInvokeResult
from tender_insights.interpret.prompts import SYSTEM_PROMPT, build_segment_prompt


def _section_path_list(section_path: str) -> list[str]:
    """将 agent 合同中的 section_path 字符串还原为列表。"""
    text = str(section_path or "").strip()
    if not text or text == "(root)":
        return []
    return [part.strip() for part in text.split(" > ") if part.strip()]


def invoke_interpret_scoring_table(llm_client: LLMClient, input: dict[str, Any]) -> AgentInvokeResult:
    """Local handler：评分表专项分段解读。"""
    for key in ("segment_id", "section_path", "markdown"):
        if key not in input:
            raise AgentInvokeError(f"interpret_scoring_table input missing field: {key}")

    segment_id = str(input["segment_id"])
    section_path = str(input["section_path"])
    markdown = str(input["markdown"])

    # 评分表路径强制启用分段附录（含 scoring-table-only 提示）。
    user_content = build_segment_prompt(
        segment_id,
        _section_path_list(section_path),
        markdown,
        keyword_match_enabled=True,
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
        raise AgentInvokeError(
            f"interpret_scoring_table local handler invalid JSON: {exc}"
        ) from exc
    if not isinstance(structured, dict):
        raise AgentInvokeError("interpret_scoring_table local handler expected JSON object")

    return AgentInvokeResult(
        call_type="interpret_scoring_table",
        status="completed",
        structured_output=structured,
        text_output=None,
        raw_response={"status": "completed", "structuredOutput": structured},
    )
