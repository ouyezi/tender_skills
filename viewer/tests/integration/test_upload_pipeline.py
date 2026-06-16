from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from viewer.main import create_app


def test_upload_runs_pipeline_and_exposes_outline(sample_docx: Path, viewer_data_dir) -> None:
    client = TestClient(create_app())
    with sample_docx.open("rb") as handle:
        response = client.post(
            "/api/upload",
            files={"file": (sample_docx.name, handle, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
    assert response.status_code == 200
    body = response.json()
    session_id = body["session_id"]
    job_id = body["job_id"]

    for _ in range(120):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in {"done", "failed"}:
            break
        time.sleep(0.5)
    assert job["status"] == "done"

    outline = client.get(f"/api/sessions/{session_id}/outline")
    assert outline.status_code == 200
    assert outline.json()["nodes"]
