from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from doc_chunk.errors import WorkspaceError


@dataclass(frozen=True, slots=True)
class OutputWorkspace:
    root: Path
    content_path: Path
    manifest_path: Path
    outline_path: Path
    outline_refined_path: Path
    outline_mapping_path: Path
    images_dir: Path
    chunks_dir: Path
    logs_dir: Path

    @classmethod
    def create(cls, root: Path, *, overwrite: bool) -> OutputWorkspace:
        if root.exists() and not overwrite:
            raise WorkspaceError(f"Output workspace already exists: {root}")
        if root.exists() and overwrite:
            if root.is_dir():
                shutil.rmtree(root)
            else:
                root.unlink()

        images_dir = root / "images"
        chunks_dir = root / "chunks"
        logs_dir = root / "logs"
        tables_dir = root / "tables"
        root.mkdir(parents=True, exist_ok=True)
        images_dir.mkdir(exist_ok=True)
        chunks_dir.mkdir(exist_ok=True)
        logs_dir.mkdir(exist_ok=True)
        tables_dir.mkdir(exist_ok=True)

        return cls(
            root=root,
            content_path=root / "content.md",
            manifest_path=root / "manifest.json",
            outline_path=root / "outline.json",
            outline_refined_path=root / "outline_refined.json",
            outline_mapping_path=root / "outline_mapping.json",
            images_dir=images_dir,
            chunks_dir=chunks_dir,
            logs_dir=logs_dir,
        )

    @classmethod
    def open_existing(cls, root: Path) -> OutputWorkspace:
        if not root.is_dir():
            raise WorkspaceError(f"Workspace not found: {root}")
        return cls(
            root=root,
            content_path=root / "content.md",
            manifest_path=root / "manifest.json",
            outline_path=root / "outline.json",
            outline_refined_path=root / "outline_refined.json",
            outline_mapping_path=root / "outline_mapping.json",
            images_dir=root / "images",
            chunks_dir=root / "chunks",
            logs_dir=root / "logs",
        )

    @property
    def content_blocks_path(self) -> Path:
        return self.root / "content.blocks.json"

    @property
    def document_tree_path(self) -> Path:
        return self.root / "document_tree.json"

    @property
    def linkage_path(self) -> Path:
        return self.root / "linkage.json"

    @property
    def images_manifest_path(self) -> Path:
        return self.images_dir / "manifest.json"

    @property
    def tables_dir(self) -> Path:
        return self.root / "tables"

    @property
    def tables_index_path(self) -> Path:
        return self.tables_dir / "index.json"
