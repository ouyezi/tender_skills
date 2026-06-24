from __future__ import annotations

import json

from doc_chunk.llm.client import LLMClient

from pydantic import BaseModel

from tender_insights.common.llm_extractor import extract_json_model
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
    client: LLMClient,
    *,
    dq: list[DisqualificationItem],
    sc: list[ScoringItem],
    br: list[BidRiskItem],
    dr: list[DirectoryRequirement],
    max_retries: int = 2,
) -> InterpretationOverview:
    payload = {
        "disqualification_items": [
            i.model_dump(include={"title", "summary", "trigger_condition"}) for i in dq
        ],
        "scoring_items": [
            i.model_dump(include={"title", "summary", "max_score", "weight", "criteria"}) for i in sc
        ],
        "bid_risk_items": [
            i.model_dump(include={"title", "summary", "severity", "risk_category"}) for i in br
        ],
        "directory_requirements": [
            i.model_dump(include={"title", "required_sections", "mandatory"}) for i in dr
        ],
    }
    messages = [
        {"role": "system", "content": OVERVIEW_SYSTEM_PROMPT},
        {"role": "user", "content": build_overview_prompt(json.dumps(payload, ensure_ascii=False))},
    ]
    resp = extract_json_model(client, messages, OverviewLLMResponse, max_retries=max_retries)
    return InterpretationOverview(**resp.model_dump())
