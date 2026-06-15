from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class DocumentTreeNode(BaseModel):
    node_id: str
    parent_id: str | None
    outline_node_id: str | None = None
    node_type: Literal["heading", "paragraph", "table", "image", "other"]
    title: str | None = None
    level: int | None = None
    sort_order: int
    source_block_index: int
    text: str | None = None
    image_ref: str | None = None
    needs_review: bool = False


class DocumentTreeFile(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    nodes: list[DocumentTreeNode] = Field(default_factory=list)
