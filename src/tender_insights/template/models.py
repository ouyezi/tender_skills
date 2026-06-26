from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class TemplateShard(BaseModel):
    shard_id: str
    strategy: Literal["whole_doc", "outline_l1", "outline_child", "heading", "char"]
    section_path: list[str] = Field(default_factory=list)
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    char_count: int = Field(ge=0)


class TemplatePlanFile(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    planned_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    whole_doc_chars: int = 0
    shard_count: int = 0
    shards: list[TemplateShard] = Field(default_factory=list)
    merge_policy: str = "dedupe_by_char_overlap_and_title"
    llm_notes: str | None = None
    priority_sections: list[str] = Field(default_factory=list)


class TemplateHitLLM(BaseModel):
    title: str
    type: Literal["commitment", "authorization", "declaration", "other"]
    type_label: str
    char_start: int
    char_end: int
    confidence: float = Field(ge=0.0, le=1.0)
    source_excerpt: str = ""


class TemplateExtractResponse(BaseModel):
    templates: list[TemplateHitLLM] = Field(default_factory=list)


class TemplatePlanLLMResponse(BaseModel):
    shard_count: int
    priority_sections: list[str] = Field(default_factory=list)
    notes: str = ""


class TemplateEntry(BaseModel):
    id: str
    type: Literal["commitment", "authorization", "declaration", "other"]
    type_label: str
    title: str
    section_path: list[str]
    file: str
    char_start: int | None = None
    char_end: int | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    extraction_method: Literal["llm", "rule"] = "llm"
    shard_id: str | None = None


class TemplatesIndexFile(BaseModel):
    schema_version: Literal["1.0", "1.1"] = "1.1"
    templates: list[TemplateEntry] = Field(default_factory=list)
    analyzed_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    plan_ref: str | None = None
    shard_count: int | None = None
