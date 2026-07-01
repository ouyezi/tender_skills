from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from viewer.config import ViewerSettings
from viewer.models import InterpretSessionRecord
from viewer.services.interpret_inputs import resolve_interpret_input_paths


def test_resolve_interpret_input_paths_from_upload_dir(tmp_path: Path) -> None:
    settings = ViewerSettings(data_dir=tmp_path)
    session_id = "sess-1"
    upload_dir = settings.interpret_uploads_dir / session_id
    upload_dir.mkdir(parents=True)
    source = upload_dir / "bid.docx"
    source.write_bytes(b"x")
    session = InterpretSessionRecord(
        id=session_id,
        title="bid.docx",
        workspace_path=str(tmp_path / "ws"),
        source_files=["bid.docx"],
        status="success",
        created_at=datetime.now(UTC).isoformat(),
        opened_at=datetime.now(UTC).isoformat(),
    )
    paths = resolve_interpret_input_paths(session, settings)
    assert paths == [source.resolve()]


def test_resolve_interpret_input_paths_from_viewer_upload_dir(tmp_path: Path) -> None:
    settings = ViewerSettings(data_dir=tmp_path)
    session_id = "sess-2"
    upload_dir = settings.data_dir / "uploads" / session_id
    upload_dir.mkdir(parents=True)
    source = upload_dir / "bid.docx"
    source.write_bytes(b"x")
    session = InterpretSessionRecord(
        id=session_id,
        title="bid.docx",
        workspace_path=str(tmp_path / "ws"),
        source_files=["bid.docx"],
        status="success",
        created_at=datetime.now(UTC).isoformat(),
        opened_at=datetime.now(UTC).isoformat(),
    )
    paths = resolve_interpret_input_paths(session, settings)
    assert paths == [source.resolve()]


def test_resolve_interpret_input_paths_missing_raises(tmp_path: Path) -> None:
    settings = ViewerSettings(data_dir=tmp_path)
    session = InterpretSessionRecord(
        id="missing",
        title="x",
        workspace_path=str(tmp_path / "ws"),
        source_files=[],
        status="failed",
        created_at=datetime.now(UTC).isoformat(),
        opened_at=datetime.now(UTC).isoformat(),
    )
    with pytest.raises(FileNotFoundError):
        resolve_interpret_input_paths(session, settings)
