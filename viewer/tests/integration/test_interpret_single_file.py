from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient


def test_single_file_upload_and_result(interpret_client: TestClient, sample_docx: Path) -> None:
    with sample_docx.open("rb") as handle:
        response = interpret_client.post(
            "/api/interpret/upload",
            files={
                "file1": (
                    sample_docx.name,
                    handle,
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )
    assert response.status_code == 200
    body = response.json()
    job = None
    for _ in range(180):
        job = interpret_client.get(f"/api/interpret/jobs/{body['job_id']}").json()
        if job["status"] in {"done", "failed"}:
            break
        time.sleep(0.5)
    assert job is not None
    assert job["status"] == "done", job

    result = interpret_client.get(f"/api/interpret/sessions/{body['session_id']}/result")
    assert result.status_code == 200
    data = result.json()
    assert data["source_files"] == [sample_docx.name]
    assert "disqualification_items" in data["interpretation"]
