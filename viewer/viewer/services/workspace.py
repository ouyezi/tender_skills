from __future__ import annotations

from pathlib import Path

from doc_chunk.workspace.layout import OutputWorkspace


def validate_workspace(path: Path) -> Path:
    workspace = OutputWorkspace.open_existing(path.resolve())
    if not workspace.content_path.exists():
        raise ValueError(f"content.md not found in {path}")
    if not workspace.outline_path.exists():
        raise ValueError(f"outline.json not found in {path}")
    return workspace.root
