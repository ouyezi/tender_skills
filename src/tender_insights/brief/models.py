from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class TenderBriefFields(BaseModel):
    issuer_company: str = Field(description="招标发起企业全称")
    procurement_subject: str = Field(description="本次招标标的/采购完整核心内容")
    budget_info: str = Field(description="项目总预算、招标控制价、预估金额")
    qualification_requirements: str = Field(description="投标人硬性准入资质、资格基本要求")
    key_timelines: str = Field(description="项目工期、交付、开标核心时间节点")


class TenderBriefLLMResponse(BaseModel):
    fields: TenderBriefFields
    summary_text: str


class TenderBriefPartialFacts(BaseModel):
    issuer_company: list[str] = Field(default_factory=list)
    procurement_subject: list[str] = Field(default_factory=list)
    budget_info: list[str] = Field(default_factory=list)
    qualification_requirements: list[str] = Field(default_factory=list)
    key_timelines: list[str] = Field(default_factory=list)


class TenderBriefFile(TenderBriefLLMResponse):
    schema_version: Literal["1.0"] = "1.0"
    source_workspace: str
    generated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    segment_count: int = 1
    ocr_image_count: int = 0
    summary_char_count: int = 0
