from pathlib import Path

import pytest

from doc_chunk.errors import WorkspaceError
from doc_chunk.workspace.layout import OutputWorkspace
from doc_chunk.workspace.manifest_io import load_manifest, save_manifest
from doc_chunk.models.manifest import Manifest, SourceInfo


def test_create_workspace_dirs(tmp_path: Path):
    ws = OutputWorkspace.create(tmp_path / "out", overwrite=False)
    assert ws.content_path.name == "content.md"
    assert ws.images_dir.is_dir()
    assert ws.manifest_path.parent == ws.root


def test_reject_existing_without_overwrite(tmp_path: Path):
    root = tmp_path / "out"
    root.mkdir()
    with pytest.raises(WorkspaceError):
        OutputWorkspace.create(root, overwrite=False)


def test_save_and_load_manifest(tmp_path: Path):
    ws = OutputWorkspace.create(tmp_path / "out", overwrite=False)
    manifest = Manifest(
        source=SourceInfo(path="/a.docx", file_name="a.docx", file_type="docx"),
    )
    save_manifest(ws, manifest)
    loaded = load_manifest(ws.manifest_path)
    assert loaded.source.file_name == "a.docx"
