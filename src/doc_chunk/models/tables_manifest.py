from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SliceStatus = Literal["ok", "failed", "missing"]


class TableManifestEntry(BaseModel):
    table_ref: str
    slice_ref: str | None = None
    slice_status: SliceStatus = "missing"
    slice_byte_size: int | None = None
    source_block_index: int
    layout_type: str
    row_count: int
    col_count: int
    char_start: int
    char_end: int
    markdown_preview: str | None = None


class TablesManifest(BaseModel):
    schema_version: Literal["1.0", "1.1"] = "1.0"
    tables: list[TableManifestEntry] = Field(default_factory=list)
