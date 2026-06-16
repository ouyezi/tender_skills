from __future__ import annotations

from pathlib import Path

import pytest
from doc_chunk.workspace.layout import OutputWorkspace

from tender_insights.common.workspace_resolver import resolve_workspace
from tender_insights.errors import WorkspaceResolveError


def test_resolve_existing_workspace(sample_workspace: Path) -> None:
    ws = resolve_workspace(sample_workspace)
    assert isinstance(ws, OutputWorkspace)
    assert ws.content_path.exists()


def test_resolve_raw_file_creates_workspace(sample_docx: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    ws = resolve_workspace(sample_docx, output_dir=out, overwrite=True)
    assert ws.content_path.exists()
    assert ws.manifest_path.exists()


def test_resolve_raw_file_requires_output_dir(sample_docx: Path) -> None:
    with pytest.raises(WorkspaceResolveError, match="output_dir"):
        resolve_workspace(sample_docx)
