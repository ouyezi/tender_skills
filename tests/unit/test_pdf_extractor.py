from pathlib import Path

import fitz

from doc_chunk.extract.pdf_extractor import extract_pdf
from doc_chunk.workspace.layout import OutputWorkspace


def _create_pdf(path: Path, *, with_text: bool) -> Path:
    doc = fitz.open()
    page = doc.new_page()
    if with_text:
        page.insert_text((72, 72), "PDF example text")
    pix = fitz.Pixmap(fitz.csRGB, fitz.Rect(0, 0, 20, 20))
    pix.set_rect(pix.irect, (255, 0, 0))
    page.insert_image(fitz.Rect(72, 100, 120, 140), pixmap=pix)
    doc.save(path)
    doc.close()
    return path


def test_extract_pdf_writes_text_and_images(tmp_path: Path) -> None:
    pdf_path = _create_pdf(tmp_path / "sample.pdf", with_text=True)
    ws = OutputWorkspace.create(tmp_path / "ws", overwrite=False)

    result = extract_pdf(pdf_path, ws)

    content = ws.content_path.read_text(encoding="utf-8")
    assert "## Page 1" in content
    assert "PDF example text" in content
    assert result.image_count == 1
    assert result.warnings == []
    assert any(p.name.startswith("page-001-img-001") for p in ws.images_dir.iterdir())


def test_extract_pdf_warns_for_scanned_page(tmp_path: Path) -> None:
    pdf_path = _create_pdf(tmp_path / "scanned.pdf", with_text=False)
    ws = OutputWorkspace.create(tmp_path / "ws", overwrite=False)

    result = extract_pdf(pdf_path, ws)

    content = ws.content_path.read_text(encoding="utf-8")
    assert "## Page 1" in content
    assert "![page-001]" in content
    assert "scanned_page_no_text: page 1" in result.warnings
    assert (ws.images_dir / "page-001.png").exists()
