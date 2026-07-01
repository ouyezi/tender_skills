from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class SessionRecord(BaseModel):
    id: str
    title: str
    workspace_path: str
    source_type: Literal["upload", "open"]
    status: Literal["pending", "running", "success", "failed"]
    created_at: str
    opened_at: str
    error: str | None = None


class JobState(BaseModel):
    job_id: str
    session_id: str
    stage: Literal["extract", "outline", "tree", "chunk", "done", "failed"]
    message: str
    status: Literal["running", "done", "failed"]
    error: str | None = None


class OpenWorkspaceRequest(BaseModel):
    path: str


class UploadResponse(BaseModel):
    session_id: str
    job_id: str


class OutlineTreeNode(BaseModel):
    node_id: str
    title: str
    level: int
    needs_review: bool = False
    children: list[OutlineTreeNode] = Field(default_factory=list)


class OutlineTreeResponse(BaseModel):
    strategy: str
    nodes: list[OutlineTreeNode]


class SectionResponse(BaseModel):
    node_id: str
    title: str
    level: int
    section_path: list[str]
    needs_review: bool
    char_start: int
    char_end: int
    markdown: str


class DocumentAssetItemResponse(BaseModel):
    asset_type: Literal["image", "table"]
    ref: str
    source_block_index: int | None = None
    char_start: int | None = None
    char_end: int | None = None
    preview: str | None = None
    outline_node_id: str | None = None
    meta: dict = Field(default_factory=dict)


class DocumentAssetsResponse(BaseModel):
    images: list[DocumentAssetItemResponse] = Field(default_factory=list)
    tables: list[DocumentAssetItemResponse] = Field(default_factory=list)


class InterpretSessionRecord(BaseModel):
    id: str
    title: str
    workspace_path: str
    source_files: list[str]
    status: Literal["pending", "running", "success", "failed"]
    created_at: str
    opened_at: str
    error: str | None = None


class InterpretJobState(BaseModel):
    job_id: str
    session_id: str
    job_kind: Literal["interpret", "brief", "template", "gen_catalog"] = "interpret"
    stage: Literal[
        "pipeline_1",
        "pipeline_2",
        "merge",
        "brief",
        "interpret",
        "template",
        "template_plan",
        "template_extract",
        "template_merge",
        "gen_catalog",
        "gen_catalog_accept",
        "done",
        "failed",
    ]
    message: str
    status: Literal["running", "done", "failed"]
    error: str | None = None
    progress_percent: int = Field(default=0, ge=0, le=100)
    step_current: int = Field(default=0, ge=0)
    step_total: int = Field(default=0, ge=0)
    segment_current: int = Field(default=0, ge=0)
    segment_total: int = Field(default=0, ge=0)
    detail: str = ""
    dual_file: bool = False
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class InterpretUploadResponse(BaseModel):
    session_id: str
    job_id: str


class InterpretResultResponse(BaseModel):
    interpretation: dict
    templates: dict
    source_files: list[str]
