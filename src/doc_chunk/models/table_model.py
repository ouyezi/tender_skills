from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class TableCell(BaseModel):
    text: str
    colspan: int = 1
    rowspan: int = 1
    vmerge: Literal["restart", "continue"] | None = None


class TableGridRow(BaseModel):
    cells: list[TableCell] = Field(default_factory=list)


class TableSidecar(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    block_index: int
    layout_type: Literal["personnel_dual_row", "simple", "key_value", "fallback"]
    grid_width: int
    grid: dict[str, Any]
    logical_rows: list[list[str]] = Field(default_factory=list)
    markdown: str
    llm_text: str
    record_groups: list[list[int]] = Field(default_factory=list)
    records: list[dict[str, str]] = Field(default_factory=list)


class TablesIndexEntry(BaseModel):
    block_index: int
    path: str


class TablesIndex(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    tables: list[TablesIndexEntry] = Field(default_factory=list)
