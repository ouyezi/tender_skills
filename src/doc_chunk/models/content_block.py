from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ContentBlockRecord(BaseModel):
    block_index: int
    block_type: Literal["paragraph", "table", "image", "heading"]
    char_start: int
    char_end: int
    text_preview: str | None = None
    image_ref: str | None = None
    table_ref: str | None = None


class ContentBlocksFile(BaseModel):
    schema_version: Literal["1.0", "1.1"] = "1.1"
    blocks: list[ContentBlockRecord] = Field(default_factory=list)
