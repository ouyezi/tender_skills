from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class TemplateRef(BaseModel):
    template_id: str
    file: str
    type: str


class SourceRef(BaseModel):
    section_path: list[str] = Field(default_factory=list)
    char_start: int | None = None
    char_end: int | None = None
    excerpt: str | None = None


class BidOutlineNode(BaseModel):
    id: str
    title: str
    level: int
    order: int
    mandatory: bool = True
    number: str | None = None
    summary: str = ""
    writing_spec: str = ""
    template_ref: TemplateRef | None = None
    scoring_refs: list[str] = Field(default_factory=list)
    disqualification_refs: list[str] = Field(default_factory=list)
    bid_risk_refs: list[str] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(default_factory=list)
    children: list[BidOutlineNode] = Field(default_factory=list)


class BidOutlineFile(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    source_workspace: str
    generated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    accepted_at: str | None = None
    interpretation_schema: str
    mode: Literal["step", "auto"]
    status: Literal["running", "paused", "awaiting_accept", "accepted", "failed"]
    step_index: int = 0
    step_total: int = 0
    overview_snapshot: dict
    brief_snapshot: dict | None = None
    root: BidOutlineNode


class BidOutlinePlanLLMResponse(BaseModel):
    needs_optimization: bool
    refinement_plan: str = ""

    @model_validator(mode="after")
    def refinement_plan_required_when_optimizing(self) -> BidOutlinePlanLLMResponse:
        if self.needs_optimization and not self.refinement_plan.strip():
            raise ValueError("refinement_plan required when needs_optimization is true")
        return self


class BidOutlineLLMResponse(BaseModel):
    outline: BidOutlineNode
    changes_summary: str = ""

    @model_validator(mode="after")
    def outline_root_is_bid_root(self) -> BidOutlineLLMResponse:
        if self.outline.id != "bid-root":
            raise ValueError("outline root id must be bid-root")
        return self


class GenCatalogSession(BaseModel):
    mode: Literal["step", "auto"]
    status: Literal["running", "paused", "awaiting_accept", "failed"]
    step_index: int = 0
    step_total: int = 0
    current_node_id: str | None = None
    current_node_title: str | None = None
    node_queue: list[str] = Field(default_factory=list)
    completed_steps: list[str] = Field(default_factory=list)
    last_plan: dict | None = None
    job_id: str | None = None
    error: str | None = None
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
