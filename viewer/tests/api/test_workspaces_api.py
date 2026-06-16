from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from viewer.main import create_app


def test_open_workspace_registers_session(viewer_data_dir, tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "content.md").write_text("# Title\n\nBody", encoding="utf-8")
    (ws / "outline.json").write_text(
        json.dumps({"schema_version": "1.0", "strategy": "flat_fallback", "nodes": []}),
        encoding="utf-8",
    )

    client = TestClient(create_app())
    response = client.post("/api/workspaces/open", json={"path": str(ws)})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["session_id"]
