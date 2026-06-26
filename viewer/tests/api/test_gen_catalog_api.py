from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from viewer.main import create_app
from viewer.models import InterpretSessionRecord


def test_gen_catalog_start_requires_interpretation(viewer_data_dir) -> None:
    from viewer.deps import get_interpret_session_store, get_settings

    client = TestClient(create_app())
    settings = get_settings()
    store = get_interpret_session_store()
    now = datetime.now(UTC).isoformat()
    workspace = settings.workspaces_dir / "gc-no-interpret"
    workspace.mkdir(parents=True)
    (workspace / "content.md").write_text("# x\n", encoding="utf-8")
    (workspace / "manifest.json").write_text(
        '{"schema_version":"1.0","status":"success","source":{"path":"/tmp/a.docx","file_name":"a.docx","file_type":"docx"},"stages":{},"outputs":{},"warnings":[],"errors":[]}',
        encoding="utf-8",
    )
    store.add(
        InterpretSessionRecord(
            id="gc-no-interpret",
            title="demo",
            workspace_path=str(workspace),
            source_files=["a.docx"],
            status="success",
            created_at=now,
            opened_at=now,
        )
    )
    response = client.post("/api/gen-catalog/sessions/gc-no-interpret/start")
    assert response.status_code == 400


def test_gen_catalog_draft_endpoint(viewer_data_dir) -> None:
    from viewer.deps import get_interpret_session_store, get_settings

    client = TestClient(create_app())
    settings = get_settings()
    store = get_interpret_session_store()
    now = datetime.now(UTC).isoformat()
    workspace = settings.workspaces_dir / "gc-draft"
    workspace.mkdir(parents=True)
    (workspace / "bid_outline.draft.json").write_text(
        '{"schema_version":"1.0","source_workspace":"/tmp","interpretation_schema":"1.2","mode":"step","status":"paused","step_index":1,"step_total":2,"overview_snapshot":{},"root":{"id":"bid-root","title":"root","level":0,"order":0,"children":[]}}',
        encoding="utf-8",
    )
    store.add(
        InterpretSessionRecord(
            id="gc-draft",
            title="demo",
            workspace_path=str(workspace),
            source_files=["a.docx"],
            status="success",
            created_at=now,
            opened_at=now,
        )
    )
    response = client.get("/api/gen-catalog/sessions/gc-draft/draft")
    assert response.status_code == 200
    assert response.json()["root"]["id"] == "bid-root"


def test_gen_catalog_llm_calls_splits_plan_and_apply(viewer_data_dir) -> None:
    from viewer.deps import get_interpret_session_store, get_settings

    client = TestClient(create_app())
    settings = get_settings()
    store = get_interpret_session_store()
    now = datetime.now(UTC).isoformat()
    workspace = settings.workspaces_dir / "gc-llm-calls"
    workspace.mkdir(parents=True)
    (workspace / "llm_calls.jsonl").write_text(
        "\n".join(
            [
                '{"call_type":"gen_catalog_node_plan","segment_id":"bid-002","messages":[{"role":"user","content":"plan"}]}',
                '{"event":"response","call_type":"gen_catalog_node_plan","segment_id":"bid-002","response":"{\\"needs_optimization\\":true}"}',
                '{"call_type":"gen_catalog_node_apply","segment_id":"bid-002","messages":[{"role":"user","content":"apply"}]}',
                '{"event":"response","call_type":"gen_catalog_node_apply","segment_id":"bid-002","response":"{\\"outline\\":{}}"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    store.add(
        InterpretSessionRecord(
            id="gc-llm-calls",
            title="demo",
            workspace_path=str(workspace),
            source_files=["a.docx"],
            status="success",
            created_at=now,
            opened_at=now,
        )
    )
    response = client.get("/api/gen-catalog/sessions/gc-llm-calls/llm-calls")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    types = {item["call_type"] for item in data}
    assert types == {"gen_catalog_node_plan", "gen_catalog_node_apply"}
    assert all(item["segment_id"] == "bid-002" for item in data)
