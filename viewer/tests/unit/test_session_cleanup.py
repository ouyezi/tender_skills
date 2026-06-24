from __future__ import annotations

from datetime import UTC, datetime

from viewer.config import ViewerSettings
from viewer.deps import get_settings
from viewer.models import InterpretSessionRecord, SessionRecord
from viewer.services.interpret_job_registry import InterpretJobRegistry
from viewer.services.interpret_session_store import InterpretSessionStore
from viewer.services.job_registry import JobRegistry
from viewer.services.session_cleanup import delete_session_fully
from viewer.services.session_store import SessionStore


def test_delete_session_fully_removes_records_and_files(viewer_data_dir) -> None:
    settings = ViewerSettings.load()
    session_store = SessionStore(settings.sessions_file)
    interpret_store = InterpretSessionStore(settings.interpret_sessions_file)
    job_registry = JobRegistry()
    interpret_job_registry = InterpretJobRegistry()

    now = datetime.now(UTC).isoformat()
    workspace = settings.workspaces_dir / "sess-1"
    workspace.mkdir(parents=True)
    (workspace / "outline.json").write_text("{}", encoding="utf-8")
    upload_dir = settings.data_dir / "uploads" / "sess-1"
    upload_dir.mkdir(parents=True)
    (upload_dir / "demo.docx").write_bytes(b"x")
    interpret_upload = settings.interpret_uploads_dir / "sess-1"
    interpret_upload.mkdir(parents=True)
    (interpret_upload / "demo.docx").write_bytes(b"x")

    session_store.add(
        SessionRecord(
            id="sess-1",
            title="demo",
            workspace_path=str(workspace),
            source_type="upload",
            status="success",
            created_at=now,
            opened_at=now,
        )
    )
    interpret_store.add(
        InterpretSessionRecord(
            id="sess-1",
            title="demo",
            workspace_path=str(workspace),
            source_files=["demo.docx"],
            status="success",
            created_at=now,
            opened_at=now,
        )
    )
    job_registry.create("job-1", "sess-1")
    interpret_job_registry.create("ijob-1", "sess-1")

    assert delete_session_fully(
        "sess-1",
        settings=settings,
        session_store=session_store,
        interpret_store=interpret_store,
        job_registry=job_registry,
        interpret_job_registry=interpret_job_registry,
    )

    assert session_store.get("sess-1") is None
    assert interpret_store.get("sess-1") is None
    assert job_registry.get("job-1") is None
    assert interpret_job_registry.get("ijob-1") is None
    assert not workspace.exists()
    assert not upload_dir.exists()
    assert not interpret_upload.exists()


def test_delete_session_fully_missing_returns_false(viewer_data_dir) -> None:
    settings = get_settings()
    assert not delete_session_fully(
        "missing",
        settings=settings,
        session_store=SessionStore(settings.sessions_file),
        interpret_store=InterpretSessionStore(settings.interpret_sessions_file),
        job_registry=JobRegistry(),
        interpret_job_registry=InterpretJobRegistry(),
    )
