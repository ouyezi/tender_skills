from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from viewer.deps import get_session_store
from viewer.main import create_app
from viewer.models import SessionRecord


def _register_session(workspace: Path) -> str:
    now = datetime.now(UTC).isoformat()
    session_id = "test-session"
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


def test_outline_and_section_endpoints(pipeline_workspace: Path, viewer_data_dir) -> None:
    client = TestClient(create_app())
    session_id = _register_session(pipeline_workspace)

    outline = client.get(f"/api/sessions/{session_id}/outline")
    assert outline.status_code == 200
    nodes = outline.json()["nodes"]
    assert len(nodes) >= 1

    node_id = nodes[0]["node_id"]
    section = client.get(f"/api/sessions/{session_id}/sections/{node_id}")
    assert section.status_code == 200
    assert section.json()["markdown"]
