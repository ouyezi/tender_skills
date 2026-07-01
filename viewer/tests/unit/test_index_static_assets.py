from pathlib import Path

STATIC = Path(__file__).resolve().parents[2] / "viewer/static"


def test_index_html_has_assets_panel() -> None:
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert "assets-panel" in html
    assert "assets-list" in html
    assert "image-preview-modal" in html


def test_app_js_has_document_assets_hooks() -> None:
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "loadDocumentAssets" in js
    assert "focusAssetInDocument" in js
    assert "openImagePreview" in js
