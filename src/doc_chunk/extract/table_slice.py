from __future__ import annotations

from pathlib import Path

from docx.table import Table as DocxTable

from doc_chunk.models.table_model import SliceStatus
from doc_chunk.table.slice_pack import build_mini_docx_for_table


def slice_ref_for_block_index(block_index: int) -> str:
    return f"tables/t{block_index:04d}.docx"


def extract_table_slice(
    table: DocxTable,
    block_index: int,
    workspace_root: Path,
) -> tuple[str | None, SliceStatus, list[str]]:
    slice_ref = slice_ref_for_block_index(block_index)
    dest = workspace_root / slice_ref
    warnings: list[str] = []
    try:
        build_mini_docx_for_table(table, dest)
    except Exception as exc:
        if dest.is_file():
            dest.unlink()
        warnings.append(f"table_slice_failed:t{block_index:04d}:{exc}")
        return None, "failed", warnings
    return slice_ref, "ok", warnings
