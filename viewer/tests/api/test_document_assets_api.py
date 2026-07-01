from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from viewer.deps import get_session_store
from viewer.main import create_app
from viewer.models import SessionRecord


def _register_session(workspace: Path) -> str:
    now = datetime.now(UTC).isoformat()
    session_id = "assets-session"
    get_session_store().add(
        SessionRecord(
            id=session_id,
            title=workspace.name,
            workspace_path=str(workspace),
            source_type="open",
            status="success",
            created_at=now,
            opened_at=now,
        )
    )
    return session_id


def test_document_assets_endpoint(pipeline_workspace: Path, viewer_data_dir) -> None:
    client = TestClient(create_app())
    session_id = _register_session(pipeline_workspace)
    response = client.get(f"/api/sessions/{session_id}/document-assets")
    assert response.status_code == 200
    data = response.json()
    assert "images" in data
    assert "tables" in data
    assert isinstance(data["images"], list)
    assert isinstance(data["tables"], list)


def test_table_export_docx(pipeline_workspace: Path, viewer_data_dir) -> None:
    client = TestClient(create_app())
    session_id = _register_session(pipeline_workspace)
    assets = client.get(f"/api/sessions/{session_id}/document-assets").json()
    if not assets["tables"]:
        return
    ref = assets["tables"][0]["ref"]
    response = client.get(f"/api/sessions/{session_id}/tables/{ref}/export.docx")
    assert response.status_code == 200
    assert response.content[:2] == b"PK"
