from __future__ import annotations

from pathlib import Path

from docx import Document

from doc_chunk.table.slice_pack import build_mini_docx_for_table


def test_build_mini_docx_for_table_writes_valid_docx(
    sample_docx_with_styled_table: Path, tmp_path: Path
) -> None:
    source = Document(sample_docx_with_styled_table)
    dest = tmp_path / "slice.docx"
    build_mini_docx_for_table(source.tables[0], dest)

    assert dest.is_file()
    assert dest.read_bytes()[:2] == b"PK"

    loaded = Document(dest)
    assert len(loaded.tables) == 1
    assert loaded.tables[0].cell(0, 0).text == "Header"
    assert loaded.tables[0].cell(1, 1).text == "B"


def test_build_mini_docx_preserves_colspan(merged_colspan_docx: Path, tmp_path: Path) -> None:
    source = Document(merged_colspan_docx)
    dest = tmp_path / "merged_slice.docx"
    build_mini_docx_for_table(source.tables[0], dest)

    loaded = Document(dest)
    assert len(loaded.tables) == 1
    assert "姓名" in loaded.tables[0].cell(0, 0).text


def test_build_mini_docx_preserves_cell_image(
    sample_docx_with_reused_image_in_body_and_table: Path, tmp_path: Path
) -> None:
    source = Document(sample_docx_with_reused_image_in_body_and_table)
    dest = tmp_path / "img_slice.docx"
    build_mini_docx_for_table(source.tables[0], dest)

    loaded = Document(dest)
    assert len(loaded.tables) == 1
    blips = [node for node in loaded.tables[0]._tbl.iter() if node.tag.endswith("}blip")]
    assert len(blips) >= 1
