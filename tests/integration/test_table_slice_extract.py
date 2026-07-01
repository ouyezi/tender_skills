from __future__ import annotations

from pathlib import Path

from doc_chunk.extract.docx_extractor import extract_docx
from doc_chunk.models.table_model import TableSidecar
from doc_chunk.workspace.layout import OutputWorkspace


def test_extract_docx_writes_table_slice(sample_docx_with_styled_table: Path, tmp_path: Path) -> None:
    ws = OutputWorkspace.create(tmp_path / "ws", overwrite=True)
    extract_docx(sample_docx_with_styled_table, ws)

    sidecars = list(ws.tables_dir.glob("t*.json"))
    assert len(sidecars) == 1

    sidecar = TableSidecar.model_validate_json(sidecars[0].read_text(encoding="utf-8"))
    assert sidecar.schema_version == "1.1"
    assert sidecar.slice_ref == "tables/t0000.docx"
    assert sidecar.slice_status == "ok"
    assert sidecar.slice_ref is not None
    assert (ws.root / sidecar.slice_ref).is_file()
    assert (ws.root / sidecar.slice_ref).read_bytes()[:2] == b"PK"
