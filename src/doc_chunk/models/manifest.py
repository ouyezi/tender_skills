from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SourceInfo(BaseModel):
    path: str
    file_name: str
    file_type: Literal["docx", "doc", "docm", "pdf"]
    title: str | None = None


class StageStatus(BaseModel):
    status: Literal["success", "partial_success", "failed", "skipped"] = "success"
    started_at: str | None = None
    finished_at: str | None = None
    warnings: list[str] = Field(default_factory=list)


class Manifest(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    status: Literal["success", "partial_success", "failed"] = "success"
    source: SourceInfo
    stages: dict[str, StageStatus] = Field(default_factory=dict)
    outputs: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
