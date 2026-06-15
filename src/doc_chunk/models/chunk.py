from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChunkMetadata(BaseModel):
    description: str | None = None
    knowledge_type: str | None = None
    chapter_type: str | None = None
    product_category_hints: list[str] = Field(default_factory=list)
    chapter_taxonomy_hints: list[str] = Field(default_factory=list)
    classification_confidence: float | None = None
    classification_source: Literal["rule", "llm", "hybrid"] | None = None
    classification_rationale: str | None = None
    suggested_candidate_type: str | None = None
    suggested_knowledge_type: str | None = None
    generated_at: str | None = None


class ChunkBlock(BaseModel):
    type: Literal["paragraph", "table", "image"]
    text: str | None = None
    image_ref: str | None = None


class ContentChunk(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    chunk_id: str
    title: str
    section_path: list[str] = Field(default_factory=list)
    heading_level: int | None = None
    markdown: str = ""
    blocks: list[ChunkBlock] = Field(default_factory=list)
    source_file: str = ""
    source_ranges: list[dict[str, Any]] = Field(default_factory=list)
    token_estimate: int = 0
    image_refs: list[str] = Field(default_factory=list)
    previous_chunk_id: str | None = None
    next_chunk_id: str | None = None
    outline_source: Literal["original", "refined"] = "original"
    refined_node_id: str | None = None
    original_node_ids: list[str] = Field(default_factory=list)
    status: Literal["success", "partial"] = "success"
    metadata: ChunkMetadata = Field(default_factory=ChunkMetadata)


class ChunkIndexEntry(BaseModel):
    chunk_id: str
    title: str
    section_path: list[str] = Field(default_factory=list)
    heading_level: int | None = None
    token_estimate: int = 0
    refined_node_id: str | None = None
    original_node_ids: list[str] = Field(default_factory=list)
    primary_outline_node_id: str | None = None
    document_tree_node_id: str | None = None
    path: str


class ChunkIndex(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    outline_source: Literal["original", "refined"] = "original"
    chunks: list[ChunkIndexEntry] = Field(default_factory=list)
