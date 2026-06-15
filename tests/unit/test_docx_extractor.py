from pathlib import Path

from doc_chunk.extract.docx_extractor import extract_docx
from doc_chunk.workspace.layout import OutputWorkspace


def test_extract_docx_writes_markdown(sample_docx: Path, tmp_path: Path) -> None:
    ws = OutputWorkspace.create(tmp_path / "ws", overwrite=False)

    result = extract_docx(sample_docx, ws)

    content = ws.content_path.read_text(encoding="utf-8")
    assert ws.content_path.exists()
    assert "# 示例标题" in content
    assert "这是一段用于测试的正文。" in content
    assert result.image_count == 0
    assert result.warnings == []


def test_extract_docx_exports_inline_images(
    sample_docx_with_image: Path, tmp_path: Path
) -> None:
    ws = OutputWorkspace.create(tmp_path / "ws", overwrite=False)

    result = extract_docx(sample_docx_with_image, ws)

    content = ws.content_path.read_text(encoding="utf-8")
    images = [p for p in ws.images_dir.iterdir() if p.name != "manifest.json"]
    assert result.image_count == 1
    assert len(images) == 1
    assert images[0].name.startswith("docx-img-001")
    assert "![docx-img-001]" in content
