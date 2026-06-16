from __future__ import annotations

from fastapi.testclient import TestClient

from viewer.main import create_app


def test_app_serves_index(viewer_data_dir) -> None:
    client = TestClient(create_app())
    response = client.get("/")
    assert response.status_code == 200
    assert "doc-chunk viewer" in response.text.lower() or "viewer" in response.text.lower()
