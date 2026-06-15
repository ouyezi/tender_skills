from __future__ import annotations

import json
from pathlib import Path

from doc_chunk.models.manifest import Manifest
from doc_chunk.workspace.layout import OutputWorkspace


def load_manifest(path: Path) -> Manifest:
    data = json.loads(path.read_text(encoding="utf-8"))
    return Manifest.model_validate(data)


def save_manifest(workspace: OutputWorkspace, manifest: Manifest) -> Path:
    workspace.manifest_path.write_text(
        json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return workspace.manifest_path
