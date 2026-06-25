from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from viewer.main import create_app


def test_gen_catalog_page_served() -> None:
    client = TestClient(create_app())
    response = client.get("/gen-catalog")
    assert response.status_code == 200
    assert "目录生成" in response.text


def test_gen_catalog_html_has_continue_button() -> None:
    html = (Path(__file__).resolve().parents[2] / "viewer/static/gen-catalog.html").read_text(encoding="utf-8")
    assert "continue-btn" in html
    assert "progress-panel" in html
