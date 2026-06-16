from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from viewer.deps import get_session_store
from viewer.main import create_app
from viewer.models import SessionRecord


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
