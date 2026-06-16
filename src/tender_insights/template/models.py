from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


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


class TemplatesIndexFile(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    templates: list[TemplateEntry] = Field(default_factory=list)
    analyzed_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
