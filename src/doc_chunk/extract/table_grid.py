from __future__ import annotations

from docx.oxml.ns import qn
from docx.table import Table as DocxTable

from doc_chunk.models.table_model import TableCell, TableGridRow


def _tc_text(tc) -> str:
    parts: list[str] = []
    for node in tc.iter():
        if node.tag == qn("w:t") and node.text:
            parts.append(node.text)
    return " ".join("".join(parts).split())


def _tc_colspan(tc) -> int:
    tc_pr = tc.find(qn("w:tcPr"))
    if tc_pr is None:
        return 1
    grid_span = tc_pr.find(qn("w:gridSpan"))
    if grid_span is None:
        return 1
    val = grid_span.get(qn("w:val"))
    return int(val) if val else 1


def _tc_vmerge(tc) -> str | None:
    tc_pr = tc.find(qn("w:tcPr"))
    if tc_pr is None:
        return None
    v_merge = tc_pr.find(qn("w:vMerge"))
    if v_merge is None:
        return None
    val = v_merge.get(qn("w:val"))
    if val == "continue":
        return "continue"
    return "restart"


def _grid_width(tbl) -> int:
    grid = tbl.find(qn("w:tblGrid"))
    if grid is not None:
        cols = grid.findall(qn("w:gridCol"))
        if cols:
            return len(cols)
    return 0


def parse_physical_grid(table: DocxTable) -> tuple[int, list[TableGridRow]]:
    tbl = table._tbl
    trs = tbl.findall(qn("w:tr"))
    width = _grid_width(tbl)
    raw_rows: list[list[tuple[TableCell, int]]] = []

    for tr in trs:
        row_cells: list[tuple[TableCell, int]] = []
        col = 0
        for tc in tr.findall(qn("w:tc")):
            vmerge = _tc_vmerge(tc)
            if vmerge == "continue":
                colspan = _tc_colspan(tc)
                col += colspan
                continue
            cell = TableCell(
                text=_tc_text(tc).strip(),
                colspan=_tc_colspan(tc),
                rowspan=1,
                vmerge=vmerge,
            )
            row_cells.append((cell, col))
            col += cell.colspan
        raw_rows.append(row_cells)
        if width == 0:
            width = max(width, col)

    for r_idx, row in enumerate(raw_rows):
        for cell, start_col in row:
            if cell.vmerge != "restart":
                continue
            span = 1
            for next_r in range(r_idx + 1, len(raw_rows)):
                covered = False
                for ncell, ncol in raw_rows[next_r]:
                    if ncol == start_col and ncell.vmerge == "continue":
                        span += 1
                        covered = True
                        break
                if not covered:
                    break
            cell.rowspan = span

    rows = [TableGridRow(cells=[c for c, _ in row]) for row in raw_rows]
    return width, rows


def logical_rows_from_physical(rows: list[TableGridRow]) -> list[list[str]]:
    return [[cell.text for cell in row.cells] for row in rows]


def fallback_grid_from_row_cells(table: DocxTable) -> tuple[int, list[TableGridRow]]:
    """OOXML 失败时：python-docx row.cells + id(_tc) 行内去重。"""
    rows: list[TableGridRow] = []
    max_cols = 0
    for row in table.rows:
        seen: set[int] = set()
        cells: list[TableCell] = []
        for cell in row.cells:
            tc_id = id(cell._tc)
            if tc_id in seen:
                continue
            seen.add(tc_id)
            cells.append(TableCell(text=cell.text.strip().replace("\n", " "), colspan=1, rowspan=1))
        rows.append(TableGridRow(cells=cells))
        max_cols = max(max_cols, len(cells))
    return max_cols, rows
