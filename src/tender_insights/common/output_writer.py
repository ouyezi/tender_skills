from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from doc_chunk.models.manifest import StageStatus
from doc_chunk.workspace.layout import OutputWorkspace
from doc_chunk.workspace.manifest_io import load_manifest, save_manifest


def write_json_artifact(
    workspace: OutputWorkspace,
    filename: str,
    payload: dict[str, Any],
    *,
    stage_name: str,
    output_key: str,
) -> Path:
    path = workspace.root / filename
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if workspace.manifest_path.exists():
        manifest = load_manifest(workspace.manifest_path)
        manifest.stages[stage_name] = StageStatus(status="success")
        manifest.outputs[output_key] = filename
        save_manifest(workspace, manifest)
    return path
