from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class Anchor(BaseModel):
    block_index: int | None = None
    page: int | None = None
    char_start: int | None = None
    char_end: int | None = None
    block_start: int | None = None
    block_end: int | None = None


class OutlineNode(BaseModel):
    node_id: str
    title: str
    level: int
    parent_id: str | None
    sort_order: int
    anchor: Anchor = Field(default_factory=Anchor)
    needs_review: bool = False
    source_refs: list[str] = Field(default_factory=list)

    @field_validator("level")
    @classmethod
    def level_in_range(cls, value: int) -> int:
        if not 1 <= value <= 8:
            raise ValueError("level must be between 1 and 8")
        return value


class OutlineTree(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    strategy: Literal["toc", "heading_heuristic", "content_heuristic", "flat_fallback"] = "flat_fallback"
    nodes: list[OutlineNode] = Field(default_factory=list)
    derived_from: str | None = None
    accepted_at: str | None = None


class OutlineMappingEntry(BaseModel):
    refined_node_id: str
    source_node_ids: list[str]
    markdown_range: dict[str, int]
    operation: Literal["merge", "split", "reparent", "rename", "keep"]


class OutlineMappingFile(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    mappings: list[OutlineMappingEntry] = Field(default_factory=list)


class RefinePreview(BaseModel):
    node_count_before: int
    node_count_after: int
    change_summary: str
    warnings: list[str] = Field(default_factory=list)
    title_diff: list[str] = Field(default_factory=list)
    validation_passed: bool
    validation_errors: list[str] = Field(default_factory=list)
