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


def test_interpret_brief_endpoint(viewer_data_dir) -> None:
    from datetime import UTC, datetime

    from viewer.deps import get_interpret_session_store, get_settings

    client = TestClient(create_app())
    settings = get_settings()
    store = get_interpret_session_store()
    now = datetime.now(UTC).isoformat()
    workspace = settings.workspaces_dir / "brief-1"
    workspace.mkdir(parents=True)
    (workspace / "tender_brief.json").write_text(
        '{"schema_version":"1.0","summary_text":"概要","fields":{"issuer_company":"甲公司"}}',
        encoding="utf-8",
    )
    store.add(
        InterpretSessionRecord(
            id="brief-1",
            title="demo",
            workspace_path=str(workspace),
            source_files=["a.docx"],
            status="success",
            created_at=now,
            opened_at=now,
        )
    )

    response = client.get("/api/interpret/sessions/brief-1/brief")
    assert response.status_code == 200
    assert response.json()["summary_text"] == "概要"


def test_upload_brief_via_job_kind_query(viewer_data_dir) -> None:
    client = TestClient(create_app())
    response = client.post("/api/interpret/upload?job_kind=brief", files={})
    assert response.status_code == 422


def test_brief_upload_alias(viewer_data_dir) -> None:
    client = TestClient(create_app())
    response = client.post("/api/interpret/brief-upload", files={})
    assert response.status_code == 422


def test_run_brief_on_existing_session(viewer_data_dir, pipeline_workspace: Path) -> None:
    from datetime import UTC, datetime

    from viewer.deps import get_interpret_session_store, get_settings

    client = TestClient(create_app())
    settings = get_settings()
    store = get_interpret_session_store()
    session_id = "brief-rerun"
    workspace = settings.workspaces_dir / session_id
    import shutil

    if workspace.exists():
        shutil.rmtree(workspace)
    shutil.copytree(pipeline_workspace, workspace)
    now = datetime.now(UTC).isoformat()
    store.add(
        InterpretSessionRecord(
            id=session_id,
            title="demo.docx",
            workspace_path=str(workspace),
            source_files=["demo.docx"],
            status="success",
            created_at=now,
            opened_at=now,
        )
    )

    response = client.post(f"/api/interpret/sessions/{session_id}/brief")
    assert response.status_code == 200
    assert response.json()["session_id"] == session_id


def test_run_brief_on_missing_session_returns_404(viewer_data_dir) -> None:
    client = TestClient(create_app())
    response = client.post("/api/interpret/sessions/missing-id/brief")
    assert response.status_code == 404


def test_run_template_on_existing_session(viewer_data_dir, pipeline_workspace: Path) -> None:
    from datetime import UTC, datetime

    from viewer.deps import get_interpret_session_store, get_settings

    client = TestClient(create_app())
    settings = get_settings()
    store = get_interpret_session_store()
    session_id = "template-rerun"
    workspace = settings.workspaces_dir / session_id
    import shutil

    if workspace.exists():
        shutil.rmtree(workspace)
    shutil.copytree(pipeline_workspace, workspace)
    now = datetime.now(UTC).isoformat()
    store.add(
        InterpretSessionRecord(
            id=session_id,
            title="demo.docx",
            workspace_path=str(workspace),
            source_files=["demo.docx"],
            status="success",
            created_at=now,
            opened_at=now,
        )
    )

    response = client.post(f"/api/interpret/sessions/{session_id}/template")
    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == session_id
    assert "job_id" in body
