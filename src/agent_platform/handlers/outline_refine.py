from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from doc_chunk.llm.client import LLMClient

from agent_platform.models import AgentInvokeError, AgentInvokeResult

_PROMPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "doc_chunk"
    / "llm"
    / "prompts"
    / "outline_refine.txt"
)


def _load_system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def invoke_outline_refine(llm_client: LLMClient, input: dict[str, Any]) -> AgentInvokeResult:
    for key in ("instruction", "original_outline", "current_outline"):
        if key not in input:
            raise AgentInvokeError(f"outline_refine input missing field: {key}")

    user_content = {
        "instruction": input["instruction"],
        "original_outline": input["original_outline"],
        "current_outline": input["current_outline"],
    }
    raw = llm_client.complete(
        [
            {"role": "system", "content": _load_system_prompt()},
            {"role": "user", "content": json.dumps(user_content, ensure_ascii=False)},
        ],
        response_format="json",
        timeout=60.0,
    )
    try:
        structured = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AgentInvokeError(f"outline_refine local handler invalid JSON: {exc}") from exc
    if not isinstance(structured, dict):
        raise AgentInvokeError("outline_refine local handler expected JSON object")

    return AgentInvokeResult(
        call_type="outline_refine",
        status="completed",
        structured_output=structured,
        text_output=None,
        raw_response={"status": "completed", "structuredOutput": structured},
    )
