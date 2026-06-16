from __future__ import annotations

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
