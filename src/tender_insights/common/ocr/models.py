from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class OcrCacheEntry(BaseModel):
    image_ref: str
    text: str = ""
    status: Literal["success", "skipped", "failed"] = "success"
    model: str = ""
    skipped_reason: str | None = None


class OcrCacheFile(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    entries: dict[str, OcrCacheEntry] = Field(default_factory=dict)
