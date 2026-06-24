from __future__ import annotations

from fastapi.testclient import TestClient

from viewer.main import create_app
from viewer.models import InterpretSessionRecord


def test_interpret_page_served() -> None:
    client = TestClient(create_app())
    response = client.get("/interpret")
    assert response.status_code == 200
    assert "招标解读" in response.text


def test_interpret_upload_requires_file1(viewer_data_dir) -> None:
    client = TestClient(create_app())
    response = client.post("/api/interpret/upload", files={})
    assert response.status_code == 422


def test_interpret_llm_calls_endpoint(viewer_data_dir) -> None:
    from datetime import UTC, datetime

    from viewer.deps import get_interpret_session_store, get_settings

    client = TestClient(create_app())
    settings = get_settings()
    store = get_interpret_session_store()
    now = datetime.now(UTC).isoformat()
    workspace = settings.workspaces_dir / "llm-1"
    workspace.mkdir(parents=True)
    (workspace / "llm_calls.jsonl").write_text(
        '{"call_type":"segment","segment_id":"s1","messages":[{"role":"user","content":"hi"}]}\n'
        '{"event":"attempt","segment_id":"s1","attempt":0,"success":false,"response_raw":"bad"}\n'
        '{"event":"response","segment_id":"s1","response":"{}"}\n',
        encoding="utf-8",
    )
    store.add(
        InterpretSessionRecord(
            id="llm-1",
            title="demo",
            workspace_path=str(workspace),
            source_files=["a.docx"],
            status="success",
            created_at=now,
            opened_at=now,
        )
    )

    response = client.get("/api/interpret/sessions/llm-1/llm-calls")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["segment_id"] == "s1"
    assert data[0]["response"] == "{}"
    assert len(data[0]["attempts"]) == 1
    assert data[0]["attempts"][0]["response_raw"] == "bad"
