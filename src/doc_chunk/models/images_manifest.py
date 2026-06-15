from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ImageManifestEntry(BaseModel):
    image_ref: str
    file_name: str
    content_type: str
    byte_size: int | None = None
    source_block_index: int | None = None
    width: int | None = None
    height: int | None = None


class ImagesManifest(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    images: list[ImageManifestEntry] = Field(default_factory=list)
