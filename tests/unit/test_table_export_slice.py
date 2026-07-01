from __future__ import annotations

from pathlib import Path

from doc_chunk.convert.table_export import export_table_ref_to_docx_bytes
from doc_chunk.models.table_model import TableSidecar
from doc_chunk.workspace.layout import OutputWorkspace


def _write_sidecar_with_slice(
    ws: OutputWorkspace,
    *,
    slice_status: str = "ok",
    slice_bytes: bytes | None = b"PKfake",
) -> str:
    ref = "tables/t0000.json"
    slice_ref = "tables/t0000.docx"
    sidecar = TableSidecar(
        schema_version="1.1",
        block_index=0,
        slice_ref=slice_ref,
        slice_status=slice_status,  # type: ignore[arg-type]
        layout_type="simple",
        grid_width=2,
        grid={"rows": [{"cells": [{"text": "a", "colspan": 1, "rowspan": 1}]}]},
        logical_rows=[["a", "b"]],
        markdown="| a | b |",
        llm_text="table",
    )
    (ws.root / ref).parent.mkdir(parents=True, exist_ok=True)
    (ws.root / ref).write_text(sidecar.model_dump_json(indent=2), encoding="utf-8")
    if slice_bytes is not None:
        (ws.root / slice_ref).write_bytes(slice_bytes)
    return ref


def test_export_returns_slice_bytes_when_ok(tmp_path: Path) -> None:
    ws = OutputWorkspace.create(tmp_path / "ws", overwrite=True)
    ref = _write_sidecar_with_slice(ws, slice_bytes=b"PKSLICE")
    data = export_table_ref_to_docx_bytes(ws, ref)
    assert data == b"PKSLICE"


def test_export_falls_back_to_rebuild_when_missing(tmp_path: Path) -> None:
    ws = OutputWorkspace.create(tmp_path / "ws-fallback", overwrite=True)
    ref = _write_sidecar_with_slice(ws, slice_status="missing", slice_bytes=None)
    data = export_table_ref_to_docx_bytes(ws, ref)
    assert data[:2] == b"PK"
    assert data != b"PKSLICE"
