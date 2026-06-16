from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from tender_insights.interpret.models import Severity


class LegalRiskItem(BaseModel):
    id: str
    description: str
    clause_excerpt: str
    risk_type: str
    severity: Severity
    section_path: list[str]
    char_start: int | None = None
    char_end: int | None = None
    confidence: float = Field(ge=0.0, le=1.0)


class PendingConfirmation(BaseModel):
    id: str
    description: str
    confirm_with: str
    suggested_question: str
    section_path: list[str]
    char_start: int | None = None
    char_end: int | None = None
    confidence: float = Field(ge=0.0, le=1.0)


class LegalReviewLLMResponse(BaseModel):
    risk_items: list[LegalRiskItem] = Field(default_factory=list)
    pending_confirmations: list[PendingConfirmation] = Field(default_factory=list)


class LegalReviewFile(LegalReviewLLMResponse):
    schema_version: Literal["1.0"] = "1.0"
    source_workspace: str
    analyzed_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
