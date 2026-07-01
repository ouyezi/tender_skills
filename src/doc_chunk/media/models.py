from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class DocumentAssetEntry(BaseModel):
    asset_type: Literal["image", "table"]
    ref: str
    source_block_index: int | None = None
    char_start: int | None = None
    char_end: int | None = None
    preview: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class DocumentAssetsFile(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    images: list[DocumentAssetEntry] = Field(default_factory=list)
    tables: list[DocumentAssetEntry] = Field(default_factory=list)
