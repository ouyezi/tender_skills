from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from viewer.deps import get_interpret_session_store, get_session_store, get_settings
from viewer.main import create_app
from viewer.models import InterpretSessionRecord, SessionRecord


def test_list_and_get_sessions(viewer_data_dir) -> None:
    client = TestClient(create_app())
    store = get_session_store()
    now = datetime.now(UTC).isoformat()
    store.add(
        SessionRecord(
            id="s1",
            title="demo",
            workspace_path="/tmp/ws",
            source_type="open",
            status="success",
            created_at=now,
            opened_at=now,
        )
    )

    listed = client.get("/api/sessions")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == "s1"

    detail = client.get("/api/sessions/s1")
    assert detail.status_code == 200
    assert detail.json()["title"] == "demo"


def test_delete_session_removes_files_and_records(viewer_data_dir) -> None:
    client = TestClient(create_app())
    settings = get_settings()
    session_store = get_session_store()
    interpret_store = get_interpret_session_store()
    now = datetime.now(UTC).isoformat()

    workspace = settings.workspaces_dir / "del-1"
    workspace.mkdir(parents=True)
    (workspace / "content.md").write_text("# hi", encoding="utf-8")

    session_store.add(
        SessionRecord(
            id="del-1",
            title="to-delete",
            workspace_path=str(workspace),
            source_type="upload",
            status="success",
            created_at=now,
            opened_at=now,
        )
    )
    interpret_store.add(
        InterpretSessionRecord(
            id="del-1",
            title="to-delete",
            workspace_path=str(workspace),
            source_files=["a.docx"],
            status="success",
            created_at=now,
            opened_at=now,
        )
    )

    response = client.delete("/api/sessions/del-1")
    assert response.status_code == 200
    assert response.json()["deleted"] is True
    assert session_store.get("del-1") is None
    assert interpret_store.get("del-1") is None
    assert not workspace.exists()


def test_delete_missing_session_returns_404(viewer_data_dir) -> None:
    client = TestClient(create_app())
    response = client.delete("/api/sessions/missing")
    assert response.status_code == 404
