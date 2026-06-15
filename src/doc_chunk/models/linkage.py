from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LinkageEntry(BaseModel):
    outline_node_id: str
    document_tree_node_ids: list[str] = Field(default_factory=list)
    chunk_ids: list[str] = Field(default_factory=list)
    primary_chunk_id: str | None = None


class LinkageFile(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    outline_source: Literal["original", "refined"] = "original"
    entries: list[LinkageEntry] = Field(default_factory=list)
