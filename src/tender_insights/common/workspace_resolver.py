from __future__ import annotations

from pathlib import Path

from doc_chunk.workspace.layout import OutputWorkspace

from tender_insights.common.pipeline_runner import prepare_workspaces
from tender_insights.errors import WorkspaceResolveError


def _is_workspace(path: Path) -> bool:
    return path.is_dir() and (path / "manifest.json").is_file() and (path / "content.md").is_file()


def resolve_workspace(
    path: Path,
    *,
    output_dir: Path | None = None,
    overwrite: bool = False,
) -> OutputWorkspace:
    path = Path(path)
    if _is_workspace(path):
        return OutputWorkspace.open_existing(path)

    if not path.is_file():
        raise WorkspaceResolveError(f"Path is neither workspace nor file: {path}")

    if output_dir is None:
        raise WorkspaceResolveError("output_dir is required when input is a raw document file")

    return prepare_workspaces([path], output_dir=output_dir, overwrite=overwrite)
