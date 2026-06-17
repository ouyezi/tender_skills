from __future__ import annotations

import base64
from pathlib import Path

import pytest
from docx import Document


_TINY_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/w8AAgMBgN3k5+EAAAAASUVORK5CYII="
)


def _build_sample_docx(target: Path, *, include_image: bool) -> Path:
    doc = Document()
    doc.add_heading("示例标题", level=1)
    doc.add_paragraph("这是一段用于测试的正文。")
    if include_image:
        image_path = target.parent / "inline.png"
        image_path.write_bytes(base64.b64decode(_TINY_PNG_BASE64))
        doc.add_picture(str(image_path))
    doc.save(target)
    return target


@pytest.fixture
def sample_docx(tmp_path: Path) -> Path:
    return _build_sample_docx(tmp_path / "sample.docx", include_image=False)


@pytest.fixture
def sample_docx_with_image(tmp_path: Path) -> Path:
    return _build_sample_docx(tmp_path / "sample_with_image.docx", include_image=True)


@pytest.fixture
def merged_colspan_docx(tmp_path: Path) -> Path:
    path = tmp_path / "merged_colspan.docx"
    doc = Document()
    table = doc.add_table(rows=2, cols=3)
    table.cell(0, 0).merge(table.cell(0, 1))
    table.cell(0, 0).text = "姓名"
    table.cell(0, 2).text = "角色"
    table.cell(1, 0).merge(table.cell(1, 1))
    table.cell(1, 0).text = "刘敏"
    table.cell(1, 2).text = "开发"
    doc.save(path)
    return path
