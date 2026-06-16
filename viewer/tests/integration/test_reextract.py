from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from viewer.config import ViewerSettings
from viewer.deps import get_session_store
from viewer.main import create_app
from viewer.models import SessionRecord
from viewer.services.reextract import resolve_reextract_input


def test_resolve_reextract_input_from_upload_dir(viewer_data_dir, tmp_path: Path) -> None:
    settings = ViewerSettings.load()
    session_id = "sess-upload"
    upload_dir = settings.data_dir / "uploads" / session_id
    upload_dir.mkdir(parents=True)
    source = upload_dir / "bid.docx"
    source.write_bytes(b"fake")
    session = SessionRecord(
        id=session_id,
        title="bid.docx",
        workspace_path=str(tmp_path / "ws"),
        source_type="upload",
        status="success",
        created_at="t",
        opened_at="t",
    )
    assert resolve_reextract_input(session, settings) == source.resolve()


def test_resolve_reextract_input_from_manifest(viewer_data_dir, tmp_path: Path) -> None:
    settings = ViewerSettings.load()
    ws = tmp_path / "ws"
    ws.mkdir()
    source = tmp_path / "source.docx"
    source.write_bytes(b"x")
    manifest = {"source": {"path": str(source)}}
    (ws / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    session = SessionRecord(
        id="sess-open",
        title="ws",
        workspace_path=str(ws),
        source_type="open",
        status="success",
        created_at="t",
        opened_at="t",
    )
    assert resolve_reextract_input(session, settings) == source.resolve()


def test_reextract_session_reruns_pipeline(sample_docx: Path, viewer_data_dir) -> None:
    client = TestClient(create_app())
    with sample_docx.open("rb") as handle:
        upload = client.post(
            "/api/upload",
            files={"file": (sample_docx.name, handle, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
    assert upload.status_code == 200
    session_id = upload.json()["session_id"]
    job_id = upload.json()["job_id"]
    for _ in range(120):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in {"done", "failed"}:
            break
        time.sleep(0.5)
    assert job["status"] == "done"

    first_outline = client.get(f"/api/sessions/{session_id}/outline").json()
    session = get_session_store().get(session_id)
    assert session is not None
    workspace = Path(session.workspace_path)
    (workspace / "content.md").write_text("# tampered\n", encoding="utf-8")

    reextract = client.post(f"/api/sessions/{session_id}/reextract")
    assert reextract.status_code == 200
    new_job_id = reextract.json()["job_id"]
    for _ in range(120):
        job = client.get(f"/api/jobs/{new_job_id}").json()
        if job["status"] in {"done", "failed"}:
            break
        time.sleep(0.5)
    assert job["status"] == "done"

    second_outline = client.get(f"/api/sessions/{session_id}/outline").json()
    assert second_outline["nodes"] == first_outline["nodes"]
    assert "# tampered" not in (workspace / "content.md").read_text(encoding="utf-8")
