from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from viewer.config import ViewerSettings
from viewer.deps import get_interpret_session_store, get_session_store
from viewer.main import create_app
from viewer.models import InterpretSessionRecord, SessionRecord
from viewer.services.interpret_session_store import InterpretSessionStore
from viewer.services.session_store import SessionStore
from viewer.services.session_sync import (
    list_merged_interpret_sessions,
    list_merged_viewer_sessions,
    mirror_interpret_session,
    mirror_viewer_session,
    resolve_interpret_session,
    resolve_viewer_session,
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def test_mirror_viewer_session_creates_interpret_record(tmp_path: Path) -> None:
    settings = ViewerSettings(data_dir=tmp_path)
    viewer_store = SessionStore(settings.sessions_file)
    interpret_store = InterpretSessionStore(settings.interpret_sessions_file)
    upload_dir = settings.data_dir / "uploads" / "viewer-1"
    upload_dir.mkdir(parents=True)
    (upload_dir / "bid.docx").write_bytes(b"x")

    record = SessionRecord(
        id="viewer-1",
        title="bid.docx",
        workspace_path=str(tmp_path / "ws"),
        source_type="upload",
        status="running",
        created_at=_now(),
        opened_at=_now(),
    )
    mirror_viewer_session(record, interpret_store, settings)

    mirrored = interpret_store.get("viewer-1")
    assert mirrored is not None
    assert mirrored.source_files == ["bid.docx"]
    assert mirrored.status == "running"


def test_mirror_interpret_session_creates_viewer_record(tmp_path: Path) -> None:
    settings = ViewerSettings(data_dir=tmp_path)
    viewer_store = SessionStore(settings.sessions_file)
    interpret_store = InterpretSessionStore(settings.interpret_sessions_file)
    record = InterpretSessionRecord(
        id="interpret-1",
        title="bid.docx",
        workspace_path=str(tmp_path / "ws"),
        source_files=["bid.docx"],
        status="success",
        created_at=_now(),
        opened_at=_now(),
    )
    mirror_interpret_session(record, viewer_store)

    mirrored = viewer_store.get("interpret-1")
    assert mirrored is not None
    assert mirrored.title == "bid.docx"
    assert mirrored.status == "success"


def test_list_merged_sessions_includes_both_sides(tmp_path: Path) -> None:
    settings = ViewerSettings(data_dir=tmp_path)
    viewer_store = SessionStore(settings.sessions_file)
    interpret_store = InterpretSessionStore(settings.interpret_sessions_file)
    now = _now()
    viewer_store.add(
        SessionRecord(
            id="viewer-only",
            title="viewer.docx",
            workspace_path=str(tmp_path / "ws1"),
            source_type="upload",
            status="success",
            created_at=now,
            opened_at=now,
        )
    )
    interpret_store.add(
        InterpretSessionRecord(
            id="interpret-only",
            title="interpret.docx",
            workspace_path=str(tmp_path / "ws2"),
            source_files=["interpret.docx"],
            status="success",
            created_at=now,
            opened_at=now,
        )
    )

    viewer_sessions = list_merged_viewer_sessions(viewer_store, interpret_store, settings)
    interpret_sessions = list_merged_interpret_sessions(viewer_store, interpret_store, settings)

    assert {session.id for session in viewer_sessions} == {"viewer-only", "interpret-only"}
    assert {session.id for session in interpret_sessions} == {"viewer-only", "interpret-only"}


def test_resolve_session_materializes_missing_side(tmp_path: Path) -> None:
    settings = ViewerSettings(data_dir=tmp_path)
    viewer_store = SessionStore(settings.sessions_file)
    interpret_store = InterpretSessionStore(settings.interpret_sessions_file)
    now = _now()
    viewer_store.add(
        SessionRecord(
            id="shared",
            title="shared.docx",
            workspace_path=str(tmp_path / "ws"),
            source_type="upload",
            status="success",
            created_at=now,
            opened_at=now,
        )
    )

    resolved = resolve_interpret_session(
        "shared",
        viewer_store=viewer_store,
        interpret_store=interpret_store,
        settings=settings,
    )
    assert resolved is not None
    assert interpret_store.get("shared") is not None

    viewer_store.delete("shared")
    resolved_viewer = resolve_viewer_session(
        "shared",
        viewer_store=viewer_store,
        interpret_store=interpret_store,
    )
    assert resolved_viewer is not None
    assert viewer_store.get("shared") is not None


def test_upload_visible_in_both_session_lists(viewer_data_dir, sample_docx: Path) -> None:
    client = TestClient(create_app())
    with sample_docx.open("rb") as handle:
        response = client.post(
            "/api/upload",
            files={"file": (sample_docx.name, handle, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
    assert response.status_code == 200
    session_id = response.json()["session_id"]

    viewer_sessions = client.get("/api/sessions").json()
    interpret_sessions = client.get("/api/interpret/sessions").json()
    assert any(session["id"] == session_id for session in viewer_sessions)
    assert any(session["id"] == session_id for session in interpret_sessions)
