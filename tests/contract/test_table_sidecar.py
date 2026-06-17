from __future__ import annotations

from pathlib import Path

from doc_chunk.api import extract_file
from doc_chunk.models.content_block import ContentBlocksFile
from doc_chunk.models.table_model import TableSidecar, TablesIndex


def test_extract_table_sidecar_aligns_with_blocks(
    personnel_dual_row_docx: Path, tmp_path: Path
) -> None:
    out = tmp_path / "ws"
    extract_file(personnel_dual_row_docx, out, overwrite=True)
    blocks = ContentBlocksFile.model_validate_json(
        (out / "content.blocks.json").read_text(encoding="utf-8")
    )
    index = TablesIndex.model_validate_json(
        (out / "tables" / "index.json").read_text(encoding="utf-8")
    )
    table_blocks = [b for b in blocks.blocks if b.block_type == "table"]
    assert len(table_blocks) == 1
    assert table_blocks[0].table_ref == index.tables[0].path
    sidecar = TableSidecar.model_validate_json(
        (out / table_blocks[0].table_ref).read_text(encoding="utf-8")
    )
    md = (out / "content.md").read_text(encoding="utf-8")
    assert (
        md[table_blocks[0].char_start : table_blocks[0].char_end].strip()
        == sidecar.markdown.strip()
    )
    assert sidecar.records[0]["姓名"] == "刘敏"
