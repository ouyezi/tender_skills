from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from PIL import Image

from doc_chunk.workspace.layout import OutputWorkspace
from tender_insights.common.ocr.enricher import (
    _file_sha256,
    _is_logo_skip,
    enrich_content_with_ocr,
    list_image_refs,
)
from tender_insights.config import InsightsConfig


def test_is_logo_skip_small_icon() -> None:
    assert _is_logo_skip(64, 64, 5000, max_bytes=10240, max_px=128) is True


def test_is_logo_skip_normal_image() -> None:
    assert _is_logo_skip(200, 200, 5000, max_bytes=10240, max_px=128) is False


def test_file_sha256_stable(tmp_path: Path) -> None:
    p = tmp_path / "a.bin"
    p.write_bytes(b"hello")
    assert _file_sha256(p) == _file_sha256(p)


def test_list_image_refs_unique() -> None:
    md = "![a](images/a.png)\n![b](images/a.png)"
    assert list_image_refs(md) == ["images/a.png"]


def test_enrich_inserts_ocr_block(tmp_path: Path) -> None:
    ws_root = tmp_path / "ws"
    ws = OutputWorkspace.create(ws_root, overwrite=True)
    img_path = ws.images_dir / "scan.png"
    Image.new("RGB", (400, 300), color="white").save(img_path)

    content = "# Title\n\n![scan](images/scan.png)\n"
    ws.content_path.write_text(content, encoding="utf-8")

    mock_client = MagicMock()
    mock_client.recognize_image_bytes.return_value = "表格文字"

    config = InsightsConfig(ocr_enabled=True, ocr_model="qwen-vl-ocr")
    enriched, cache, calls = enrich_content_with_ocr(
        ws,
        content,
        config=config,
        client=mock_client,
    )

    assert "<!-- ocr:" in enriched
    assert "表格文字" in enriched
    assert calls == 1
    assert cache.entries

    enriched2, _, calls2 = enrich_content_with_ocr(ws, content, config=config, client=mock_client)
    assert calls2 == 0
    assert "表格文字" in enriched2


def test_enrich_skips_logo(tmp_path: Path) -> None:
    ws_root = tmp_path / "ws"
    ws = OutputWorkspace.create(ws_root, overwrite=True)
    img_path = ws.images_dir / "logo.png"
    Image.new("RGB", (32, 32), color="white").save(img_path, optimize=True)

    content = "![logo](images/logo.png)\n"
    ws.content_path.write_text(content, encoding="utf-8")

    mock_client = MagicMock()
    config = InsightsConfig()
    enriched, _, calls = enrich_content_with_ocr(ws, content, config=config, client=mock_client)

    assert calls == 0
    mock_client.recognize_image_bytes.assert_not_called()
    assert "<!-- ocr:" not in enriched
