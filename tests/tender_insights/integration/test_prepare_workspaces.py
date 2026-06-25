from __future__ import annotations

import json
from pathlib import Path

import pytest

from tender_insights.common.pipeline_runner import prepare_workspaces
from tender_insights.common.workspace_merge import validate_merged_workspace
from tender_insights.errors import WorkspaceResolveError


def test_prepare_workspaces_merge_requires_output_dir(sample_docx: Path) -> None:
    with pytest.raises(WorkspaceResolveError, match="output_dir"):
        prepare_workspaces([sample_docx, sample_docx])


def test_prepare_workspaces_rejects_three_files(sample_docx: Path, tmp_path: Path) -> None:
    with pytest.raises(WorkspaceResolveError, match="at most two"):
        prepare_workspaces(
            [sample_docx, sample_docx, sample_docx],
            output_dir=tmp_path / "out",
        )


def test_prepare_workspaces_merges_two_files(sample_docx: Path, tmp_path: Path) -> None:
    doc2 = tmp_path / "spec.docx"
    doc2.write_bytes(sample_docx.read_bytes())
    ws = prepare_workspaces(
        [sample_docx, doc2],
        output_dir=tmp_path / "merged",
        overwrite=True,
    )
    assert (ws.root / "content.md").exists()
    content = ws.content_path.read_text(encoding="utf-8")
    assert "<!-- source:" in content
    validate_merged_workspace(ws.root)
