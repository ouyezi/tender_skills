from __future__ import annotations

import io
from pathlib import Path

from docx import Document

from doc_chunk.convert.table_to_docx import render_sidecar_to_docx
from doc_chunk.table.access import load_table_model
from doc_chunk.workspace.layout import OutputWorkspace


def _slice_is_usable(sidecar, ws: OutputWorkspace) -> bool:
    if sidecar.slice_status != "ok" or not sidecar.slice_ref:
        return False
    return (ws.root / sidecar.slice_ref).is_file()


def export_table_ref_to_docx_bytes(workspace: OutputWorkspace | Path, table_ref: str) -> bytes:
    ws = workspace if isinstance(workspace, OutputWorkspace) else OutputWorkspace.open_existing(Path(workspace))
    sidecar_path = ws.root / table_ref
    if not sidecar_path.is_file():
        raise FileNotFoundError(f"table sidecar not found: {table_ref}")
    sidecar = load_table_model(ws, table_ref)
    if _slice_is_usable(sidecar, ws):
        return (ws.root / sidecar.slice_ref).read_bytes()

    document = Document()
    render_sidecar_to_docx(document, sidecar)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()
