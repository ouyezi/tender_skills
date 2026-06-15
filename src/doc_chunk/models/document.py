from __future__ import annotations

from pydantic import BaseModel, Field


class ExtractResult(BaseModel):
    image_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class PipelineResult(BaseModel):
    status: str
    manifests: list = Field(default_factory=list)
    errors: list[dict] = Field(default_factory=list)
