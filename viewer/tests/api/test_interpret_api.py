from __future__ import annotations

from fastapi.testclient import TestClient

from viewer.main import create_app


def test_interpret_page_served() -> None:
    client = TestClient(create_app())
    response = client.get("/interpret")
    assert response.status_code == 200
    assert "招标解读" in response.text


def test_interpret_upload_requires_file1(viewer_data_dir) -> None:
    client = TestClient(create_app())
    response = client.post("/api/interpret/upload", files={})
    assert response.status_code == 422
