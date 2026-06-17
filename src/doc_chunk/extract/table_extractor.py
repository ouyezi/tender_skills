from __future__ import annotations

from docx.table import Table as DocxTable

from doc_chunk.extract.table_grid import (
    fallback_grid_from_row_cells,
    logical_rows_from_physical,
    parse_physical_grid,
)
from doc_chunk.extract.table_layout import build_records, classify_layout
from doc_chunk.extract.table_serialize import logical_to_markdown, records_to_llm_text
from doc_chunk.models.table_model import TableSidecar


def extract_table(table: DocxTable, block_index: int) -> tuple[str, TableSidecar | None, list[str]]:
    warnings: list[str] = []
    try:
        grid_width, physical_rows = parse_physical_grid(table)
    except Exception as exc:
        warnings.append(f"table_grid_fallback:{block_index}:{exc}")
        grid_width, physical_rows = fallback_grid_from_row_cells(table)

    logical = logical_rows_from_physical(physical_rows)
    if not logical or not any(any(c.strip() for c in row) for row in logical):
        return "", None, warnings

    layout, groups = classify_layout(logical)
    records = build_records(logical, layout, groups)
    markdown = logical_to_markdown(logical)
    llm_text = records_to_llm_text(layout, records, logical_rows=logical)

    sidecar = TableSidecar(
        block_index=block_index,
        layout_type=layout,  # type: ignore[arg-type]
        grid_width=grid_width,
        grid={"rows": [r.model_dump() for r in physical_rows]},
        logical_rows=logical,
        markdown=markdown,
        llm_text=llm_text,
        record_groups=groups,
        records=records,
    )
    return markdown, sidecar, warnings
