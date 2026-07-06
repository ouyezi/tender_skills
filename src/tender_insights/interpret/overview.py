from __future__ import annotations

import json

from agent_platform.client import AgentClient
from agent_platform.factory import create_agent_client_from_env
from doc_chunk.llm.client import LLMClient
from pydantic import BaseModel

from tender_insights.common.agent_extractor import extract_json_via_agent
from tender_insights.interpret.llm_logging import log_llm_prompt
from tender_insights.interpret.models import (
    BidRiskItem,
    DirectoryRequirement,
    DisqualificationItem,
    InterpretationOverview,
    ScoringItem,
)
from tender_insights.interpret.prompts import OVERVIEW_SYSTEM_PROMPT, build_overview_prompt


class OverviewLLMResponse(BaseModel):
    summary: str
    disqualification_summary: str
    scoring_summary: str
    bid_risk_summary: str
    directory_summary: str


def build_overview(
    client: LLMClient | AgentClient,
    *,
    dq: list[DisqualificationItem],
    sc: list[ScoringItem],
    br: list[BidRiskItem],
    dr: list[DirectoryRequirement],
    max_retries: int = 2,
    workspace: str | None = None,
    agent_client: AgentClient | None = None,
) -> InterpretationOverview:
    """调用 interpret_overview agent 生成五段概要。"""
    resolved = agent_client
    if resolved is None:
        if isinstance(client, AgentClient):
            resolved = client
        else:
            resolved = create_agent_client_from_env(llm_client=client)

    payload = {
        "disqualification_items": [
            i.model_dump(include={"title", "summary", "trigger_condition"}) for i in dq
        ],
        "scoring_items": [
            {
                **i.model_dump(include={"title", "summary", "max_score", "weight", "criteria"}),
                "children": [
                    c.model_dump(include={"title", "max_score", "score_range", "criteria"})
                    for c in i.children
                ],
            }
            for i in sc
        ],
        "bid_risk_items": [
            i.model_dump(include={"title", "summary", "severity", "risk_category"}) for i in br
        ],
        "directory_requirements": [
            i.model_dump(include={"title", "required_sections", "mandatory", "inferred"})
            for i in dr
        ],
    }
    items_json = json.dumps(payload, ensure_ascii=False)
    messages = [
        {"role": "system", "content": OVERVIEW_SYSTEM_PROMPT},
        {"role": "user", "content": build_overview_prompt(items_json)},
    ]
    log_llm_prompt(
        call_type="interpret_overview",
        messages=messages,
        workspace=workspace,
        segment_id="overview",
    )
    resp = extract_json_via_agent(
        resolved,
        "interpret_overview",
        {"items_json": items_json},
        OverviewLLMResponse,
        max_retries=max_retries,
        log_context={"call_type": "interpret_overview", "segment_id": "overview"},
    )
    return InterpretationOverview(**resp.model_dump())
