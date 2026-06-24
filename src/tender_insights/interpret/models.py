from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class Severity(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class DirectoryStructureNode(BaseModel):
    order: int
    number: str | None = None
    title: str
    mandatory: bool = True
    children: list["DirectoryStructureNode"] = Field(default_factory=list)


class DisqualificationItem(BaseModel):
    id: str
    title: str
    summary: str
    trigger_condition: str
    source_excerpt: str
    section_path: list[str]
    char_start: int | None = None
    char_end: int | None = None
    confidence: float = Field(ge=0.0, le=1.0)


class ScoringItem(BaseModel):
    id: str
    title: str
    summary: str
    max_score: float | None = None
    weight: str | None = None
    criteria: str
    source_excerpt: str
    section_path: list[str]
    char_start: int | None = None
    char_end: int | None = None
    confidence: float = Field(ge=0.0, le=1.0)


class BidRiskItem(BaseModel):
    id: str
    title: str
    summary: str
    severity: Severity
    risk_category: str
    source_excerpt: str
    section_path: list[str]
    char_start: int | None = None
    char_end: int | None = None
    confidence: float = Field(ge=0.0, le=1.0)


class DirectoryRequirement(BaseModel):
    id: str
    title: str
    required_sections: list[str]
    mandatory: bool
    structure: list[DirectoryStructureNode] = Field(default_factory=list)
    source_excerpt: str
    section_path: list[str]
    char_start: int | None = None
    char_end: int | None = None
    confidence: float = Field(ge=0.0, le=1.0)


class InterpretationOverview(BaseModel):
    summary: str
    disqualification_summary: str
    scoring_summary: str
    bid_risk_summary: str
    directory_summary: str


class DirectoryOutlineNode(BaseModel):
    id: str
    title: str
    level: int
    order: int
    mandatory: bool = True
    number: str | None = None


class DirectoryOutline(BaseModel):
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    nodes: list[DirectoryOutlineNode] = Field(default_factory=list)


class InterpretationLLMResponse(BaseModel):
    disqualification_items: list[DisqualificationItem] = Field(default_factory=list)
    scoring_items: list[ScoringItem] = Field(default_factory=list)
    bid_risk_items: list[BidRiskItem] = Field(default_factory=list)
    directory_requirements: list[DirectoryRequirement] = Field(default_factory=list)


class InterpretationFile(InterpretationLLMResponse):
    schema_version: Literal["1.0", "1.1"] = "1.1"
    source_workspace: str
    analyzed_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    overview: InterpretationOverview
    directory_outline: DirectoryOutline = Field(default_factory=DirectoryOutline)
    segment_count: int = 0
    ocr_image_count: int = 0


DirectoryStructureNode.model_rebuild()
