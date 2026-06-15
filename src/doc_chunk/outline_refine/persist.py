from __future__ import annotations

import json
from datetime import datetime, UTC
from pathlib import Path

from doc_chunk.models.outline import OutlineMappingFile, OutlineTree
from doc_chunk.workspace.layout import OutputWorkspace


def persist_refined_artifacts(
    workspace: OutputWorkspace,
    *,
    refined_outline: OutlineTree,
    mapping: OutlineMappingFile,
    summary: str,
) -> None:
    refined_data = refined_outline.model_dump(mode="json")
    refined_data["derived_from"] = "outline.json"
    refined_data["accepted_at"] = datetime.now(UTC).isoformat()

    workspace.outline_refined_path.write_text(
        json.dumps(refined_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    workspace.outline_mapping_path.write_text(
        json.dumps(mapping.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (workspace.root / "outline_refine_summary.md").write_text(summary, encoding="utf-8")


def clear_refined_artifacts(workspace: OutputWorkspace) -> None:
    for path in (
        workspace.outline_refined_path,
        workspace.outline_mapping_path,
        workspace.root / "outline_refine_summary.md",
    ):
        if path.exists():
            path.unlink()
