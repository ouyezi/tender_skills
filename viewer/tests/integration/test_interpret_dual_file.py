from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from viewer.deps import get_interpret_session_store, get_settings


def test_dual_file_merge(
    interpret_client: TestClient,
    sample_docx: Path,
    second_sample_docx: Path,
    viewer_data_dir: Path,
) -> None:
    with sample_docx.open("rb") as f1, second_sample_docx.open("rb") as f2:
        response = interpret_client.post(
            "/api/interpret/upload",
            files={
                "file1": (
                    sample_docx.name,
                    f1,
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ),
                "file2": (
                    second_sample_docx.name,
                    f2,
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ),
            },
        )
    assert response.status_code == 200
    body = response.json()
    job = None
    for _ in range(240):
        job = interpret_client.get(f"/api/interpret/jobs/{body['job_id']}").json()
        if job["status"] in {"done", "failed"}:
            break
        time.sleep(0.5)
    assert job is not None
    assert job["status"] == "done", job

    session = get_interpret_session_store().get(body["session_id"])
    assert session is not None
    ws = Path(session.workspace_path)
    content = (ws / "content.md").read_text(encoding="utf-8")
    assert f"<!-- source: {second_sample_docx.name} -->" in content
    outline = json.loads((ws / "outline.json").read_text(encoding="utf-8"))
    assert any(n["node_id"].startswith("m2:") for n in outline["nodes"])
