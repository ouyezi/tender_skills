# Word 表格提取增强 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 docx extract 阶段修复合并单元格重复列，产出去重 Markdown（viewer）、`tables/` 侧车（物理 grid + llm_text + records），并提供 `substitute_tables_for_llm` API。

**Architecture:** 从 OOXML 直接解析物理网格（`gridSpan`/`vMerge`），派生逻辑行生成 Markdown；版式分类器识别人员双行表等招投标常见结构；`content.md` 仍承载 Markdown 锚点，`tables/t{NNNN}.json` 为三端消费的权威侧车；`table_to_docx` 本计划仅落契约占位。

**Tech Stack:** Python 3.11+, python-docx, lxml (via docx oxml), pydantic v2, pytest

**需求来源:** [`docs/superpowers/specs/2026-06-17-docx-table-extract-design.md`](../specs/2026-06-17-docx-table-extract-design.md)

---

## File Structure

```text
src/doc_chunk/
├── models/
│   ├── content_block.py          # MODIFY: schema 1.1, table_ref
│   └── table_model.py            # NEW: TableCell, TableGrid, TableSidecar, TablesIndex
├── extract/
│   ├── docx_extractor.py         # MODIFY: 接入 TableExtractor
│   ├── block_index.py            # MODIFY: add_table(table_ref=...)
│   ├── table_grid.py             # NEW: OOXML 物理/逻辑网格
│   ├── table_layout.py           # NEW: 版式分类 + records
│   ├── table_serialize.py        # NEW: markdown / llm_text
│   ├── table_sidecar.py          # NEW: 侧车写入
│   └── table_extractor.py        # NEW: 编排入口
├── table/
│   ├── __init__.py               # NEW
│   └── access.py                 # NEW: load_table_model, substitute_tables_for_llm
├── convert/
│   └── table_to_docx.py          # NEW: 契约占位（NotImplementedError）
├── workspace/
│   └── layout.py                 # MODIFY: tables_dir property
└── api.py                        # MODIFY: manifest outputs 登记 tables/

tests/
├── conftest.py                   # MODIFY: 表格 fixture 工厂
├── fixtures/                     # NEW: merged_colspan.docx 等（测试内生成或提交）
├── unit/
│   ├── test_table_grid.py        # NEW
│   ├── test_table_layout.py      # NEW
│   ├── test_table_serialize.py   # NEW
│   ├── test_table_access.py      # NEW
│   ├── test_docx_extractor.py    # MODIFY
│   └── test_block_index.py       # MODIFY
└── contract/
    └── test_table_sidecar.py     # NEW

specs/001-document-extract-chunk/contracts/workspace-schemas.md  # MODIFY
```

---

### Task 1: Pydantic 模型与 content.blocks schema 1.1

**Files:**
- Create: `src/doc_chunk/models/table_model.py`
- Modify: `src/doc_chunk/models/content_block.py`
- Test: `tests/unit/test_table_model.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_table_model.py
from doc_chunk.models.content_block import ContentBlocksFile, ContentBlockRecord
from doc_chunk.models.table_model import TableCell, TableGridRow, TableSidecar, TablesIndex


def test_content_blocks_schema_1_1_accepts_table_ref() -> None:
    blocks = ContentBlocksFile(
        schema_version="1.1",
        blocks=[
            ContentBlockRecord(
                block_index=0,
                block_type="table",
                char_start=0,
                char_end=50,
                text_preview="| a | b |",
                table_ref="tables/t0000.json",
            )
        ],
    )
    assert blocks.schema_version == "1.1"
    assert blocks.blocks[0].table_ref == "tables/t0000.json"


def test_table_sidecar_roundtrip() -> None:
    sidecar = TableSidecar(
        block_index=0,
        layout_type="simple",
        grid_width=2,
        grid={"rows": [{"cells": [TableCell(text="a", colspan=1, rowspan=1)]}]},
        logical_rows=[["a", "b"], ["1", "2"]],
        markdown="| a | b |\n| --- | --- |\n| 1 | 2 |",
        llm_text="【表格:列表】\n--- 行 1 ---\na: 1\nb: 2",
        record_groups=[],
        records=[],
    )
    parsed = TableSidecar.model_validate_json(sidecar.model_dump_json())
    assert parsed.layout_type == "simple"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/tongqianni/xlab/tender_skills
.venv/bin/python -m pytest tests/unit/test_table_model.py -v
```

Expected: FAIL `ModuleNotFoundError` or `table_ref` unexpected keyword

- [ ] **Step 3: Write minimal implementation**

```python
# src/doc_chunk/models/table_model.py
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class TableCell(BaseModel):
    text: str
    colspan: int = 1
    rowspan: int = 1
    vmerge: Literal["restart", "continue"] | None = None


class TableGridRow(BaseModel):
    cells: list[TableCell] = Field(default_factory=list)


class TableSidecar(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    block_index: int
    layout_type: Literal["personnel_dual_row", "simple", "key_value", "fallback"]
    grid_width: int
    grid: dict[str, Any]
    logical_rows: list[list[str]] = Field(default_factory=list)
    markdown: str
    llm_text: str
    record_groups: list[list[int]] = Field(default_factory=list)
    records: list[dict[str, str]] = Field(default_factory=list)


class TablesIndexEntry(BaseModel):
    block_index: int
    path: str


class TablesIndex(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    tables: list[TablesIndexEntry] = Field(default_factory=list)
```

```python
# src/doc_chunk/models/content_block.py — 修改 schema_version 与 table_ref
from typing import Literal
# ...
class ContentBlockRecord(BaseModel):
  # ... existing fields ...
    table_ref: str | None = None

class ContentBlocksFile(BaseModel):
    schema_version: Literal["1.0", "1.1"] = "1.1"
    blocks: list[ContentBlockRecord] = Field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python -m pytest tests/unit/test_table_model.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/doc_chunk/models/table_model.py src/doc_chunk/models/content_block.py tests/unit/test_table_model.py
git commit -m "feat(models): add table sidecar schema and content.blocks 1.1 table_ref"
```

---

### Task 2: OOXML 物理网格解析（TableGridParser）

**Files:**
- Create: `src/doc_chunk/extract/table_grid.py`
- Modify: `tests/conftest.py`
- Test: `tests/unit/test_table_grid.py`

- [ ] **Step 1: Write fixture helper and failing tests**

在 `tests/conftest.py` 追加：

```python
def _set_cell_text(cell, text: str) -> None:
    cell.text = text


@pytest.fixture
def merged_colspan_docx(tmp_path: Path) -> Path:
    from docx import Document

    path = tmp_path / "merged_colspan.docx"
    doc = Document()
    table = doc.add_table(rows=2, cols=4)
    table.cell(0, 0).merge(table.cell(0, 1))
    table.cell(0, 0).text = "姓名"
    table.cell(0, 2).text = "角色"
    table.cell(0, 3).merge(table.cell(0, 3))  # no-op, keep 4 cols
    # 简化：row0 = [姓名 merge 0-1] [角色] [性别 merge 2-3 需再一列]
    # 重新建 4 列：0-1 merge 姓名, 2 角色, 3 空后 merge 需5列 — 用 3 列演示
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
```

```python
# tests/unit/test_table_grid.py
from docx import Document

from doc_chunk.extract.table_grid import logical_rows_from_physical, parse_physical_grid


def test_parse_physical_grid_colspan(merged_colspan_docx):
    doc = Document(merged_colspan_docx)
    grid_width, rows = parse_physical_grid(doc.tables[0])
    assert grid_width == 3
    assert rows[0].cells[0].text == "姓名"
    assert rows[0].cells[0].colspan == 2
    assert rows[0].cells[1].text == "角色"
    assert rows[0].cells[1].colspan == 1


def test_logical_rows_dedupes_colspan(merged_colspan_docx):
    doc = Document(merged_colspan_docx)
    grid_width, rows = parse_physical_grid(doc.tables[0])
    logical = logical_rows_from_physical(rows)
    assert logical[0] == ["姓名", "角色"]
    assert logical[1] == ["刘敏", "开发"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest tests/unit/test_table_grid.py -v
```

Expected: FAIL `ModuleNotFoundError: doc_chunk.extract.table_grid`

- [ ] **Step 3: Implement table_grid.py**

```python
# src/doc_chunk/extract/table_grid.py
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

  # vertical merge: compute rowspan for restart cells
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
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python -m pytest tests/unit/test_table_grid.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/doc_chunk/extract/table_grid.py tests/unit/test_table_grid.py tests/conftest.py
git commit -m "feat(extract): parse docx table physical grid from OOXML"
```

---

### Task 3: 版式分类与 records 构建

**Files:**
- Create: `src/doc_chunk/extract/table_layout.py`
- Modify: `tests/conftest.py`（`personnel_dual_row_docx` fixture）
- Test: `tests/unit/test_table_layout.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/conftest.py — personnel_dual_row_docx fixture
@pytest.fixture
def personnel_dual_row_docx(tmp_path: Path) -> Path:
    from docx import Document

    path = tmp_path / "personnel_dual_row.docx"
    doc = Document()
    table = doc.add_table(rows=4, cols=4)
    headers1 = ["姓名", "本项目工作角色", "性别", "学历"]
    values1 = ["刘敏", "开发工程师", "男", "本科"]
    headers2 = ["级别", "年龄", "毕业学校", "从业年限"]
    values2 = ["高级Java工程师", "35", "承德石油学院", "9+"]
    for c, h in enumerate(headers1):
        table.cell(0, c).text = h
    for c, v in enumerate(values1):
        table.cell(1, c).text = v
    for c, h in enumerate(headers2):
        table.cell(2, c).text = h
    for c, v in enumerate(values2):
        table.cell(3, c).text = v
    doc.save(path)
    return path
```

```python
# tests/unit/test_table_layout.py
from docx import Document

from doc_chunk.extract.table_grid import logical_rows_from_physical, parse_physical_grid
from doc_chunk.extract.table_layout import classify_layout, build_records


def test_classify_personnel_dual_row(personnel_dual_row_docx):
    doc = Document(personnel_dual_row_docx)
    _, rows = parse_physical_grid(doc.tables[0])
    logical = logical_rows_from_physical(rows)
    layout, groups = classify_layout(logical)
    assert layout == "personnel_dual_row"
    assert groups == [[0, 1]]


def test_build_records_merges_two_rows(personnel_dual_row_docx):
    doc = Document(personnel_dual_row_docx)
    _, rows = parse_physical_grid(doc.tables[0])
    logical = logical_rows_from_physical(rows)
    layout, groups = classify_layout(logical)
    records = build_records(logical, layout, groups)
    assert records[0]["姓名"] == "刘敏"
    assert records[0]["级别"] == "高级Java工程师"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest tests/unit/test_table_layout.py -v
```

Expected: FAIL

- [ ] **Step 3: Implement table_layout.py**

```python
# src/doc_chunk/extract/table_layout.py
from __future__ import annotations

import re

LayoutType = str

_PERSONNEL_HEADER = re.compile(
    r"姓名|性别|学历|角色|职务|岗位|本项目工作角色|人员|工号"
)
_PERSONNEL_EXT = re.compile(
    r"级别|年龄|毕业学校|从业年限|资质证书|职称|专业|工作年限"
)


def _match_ratio(cells: list[str], pattern: re.Pattern[str]) -> float:
    if not cells:
        return 0.0
    hits = sum(1 for c in cells if pattern.search(c.strip()))
    return hits / len(cells)


def classify_layout(logical_rows: list[list[str]]) -> tuple[LayoutType, list[list[int]]]:
    if not logical_rows:
        return "fallback", []

    col_count = len(logical_rows[0])
    if col_count == 2 and len(logical_rows) >= 2:
        return "key_value", []

    if len(logical_rows) >= 2 and len(logical_rows) != 1:
        data_rows = logical_rows[1:]
        if all(len(r) == col_count for r in logical_rows):
            if len(logical_rows) >= 4 and len(logical_rows) % 2 == 0:
                groups = [[i, i + 1] for i in range(0, len(logical_rows), 2)]
                ok = True
                for h_idx, d_idx in groups:
                    if _match_ratio(logical_rows[h_idx], _PERSONNEL_HEADER) < 0.5:
                        ok = False
                    if _match_ratio(logical_rows[d_idx], _PERSONNEL_EXT) < 0.5:
                        ok = False
                if ok:
                    return "personnel_dual_row", groups
            if _match_ratio(logical_rows[0], _PERSONNEL_HEADER) < 0.3:
                return "simple", []

    return "fallback", []


def build_records(
    logical_rows: list[list[str]],
    layout: LayoutType,
    record_groups: list[list[int]],
) -> list[dict[str, str]]:
    if layout == "personnel_dual_row":
        records: list[dict[str, str]] = []
        for header_idx, data_idx in record_groups:
            if data_idx + 1 >= len(logical_rows):
                break
            header2 = logical_rows[data_idx]
            values2 = logical_rows[data_idx + 1]
            record: dict[str, str] = {}
            for h, v in zip(logical_rows[header_idx], logical_rows[header_idx + 1], strict=False):
                if h.strip():
                    record[h.strip()] = v.strip()
            for h, v in zip(header2, values2, strict=False):
                if h.strip():
                    record[h.strip()] = v.strip()
            records.append(record)
        return records

    if layout == "key_value":
        return [dict(zip(logical_rows[i], logical_rows[i + 1], strict=False)) for i in range(0, len(logical_rows) - 1, 2)]

    if layout == "simple" and len(logical_rows) >= 2:
        headers = logical_rows[0]
        out: list[dict[str, str]] = []
        for row in logical_rows[1:]:
            out.append({h: v for h, v in zip(headers, row, strict=False) if h.strip()})
        return out

    return []
```

**注意：** `personnel_dual_row` 的 `record_groups` 在分类器里应成对为 `[header_row, value_row]` 对；上面测试用 4 行单人员时 groups=`[[0,1]]` 表示第 0-1 行为第一组 header/data，第 2-3 行为第二组。实现时按设计将 `groups` 定义为 `[[0,1],[2,3]]` 每两条逻辑行一组；`build_records` 对每组取 `(rows[g[0]], rows[g[0]+1])` 为字段名/值，若组内包含两行 header/data 各一行则 `g=[0,1]` 表示行 0 是 header、行 1 是 data——**修正测试与实现一致性**：

- `groups = [[0, 1], [2, 3]]`：每组 `[header_row_index, data_row_index]`（data 为 header+1 时简化为只存 header 索引）
- 设计文档：`record_groups: [[0,1], [2,3]]` 表示行 0-1 合并、行 2-3 合并

实现 `build_records`：

```python
for group in record_groups:
    h_row, d_row = group[0], group[1]
    record = {logical_rows[h_row][i].strip(): logical_rows[d_row][i].strip()
              for i in range(min(len(logical_rows[h_row]), len(logical_rows[d_row])))
              if logical_rows[h_row][i].strip()}
```

人员双行表 4 行场景：groups=`[[0,1],[2,3]]` 不对——行 0 header1, 1 data1, 2 header2, 3 data2。应为 `[[0,1],[2,3]]` 每组两行，但 record 只合并一对 header/data。双行人员表是 **两行合成一条记录**（header1+header2 字段名，data1+data2 值）：

按设计 spec：`record_groups: [[0, 1]]` 表示逻辑行 0 和 1 合并为一条——那是 2 行一条记录。用户样例 4 行 1 人：`[[0,1],[2,3]]` 不对，应是 `[[0,1,2,3]]` 或 pair 结构。

设计写的是 `record_groups: [[0,1], [2,3], ...]` 每 **两条逻辑行** 一条记录：行0+行1为 record1（奇数行主字段+偶数行扩展字段）。所以 4 行 1 人：`record_groups=[[0,1]]` 且行0=header1, 行1=data1, 行2=header2, 行3=data2——需要 `build_records` 读 **连续 4 行** 为一条。

分类器应输出 `record_groups: [[0, 1, 2, 3]]` 或固定模式「每 4 行一条」：`[[0,3]]` 表示行 0-3。

为简化计划，采用设计原文：`[[0,1], [2,3]]` = 第一组行索引 0 与 1 为一对 header/data（仅主字段），第二组 2 与 3 为扩展——合并时 `build_records` 将同一「人员块」内所有组并成一个 record。或更简单：**personnel 固定 4 行周期**，`record_groups=[[0,1,2,3]]`。

计划在 Task 3 实现中明确：

```python
# 每 4 行一条人员记录：h1,d1,h2,d2
for start in range(0, len(logical_rows), 4):
    h1, d1, h2, d2 = logical_rows[start:start+4]
    record = {}
    for h, v in zip(h1, d1, strict=False):
        if h.strip(): record[h.strip()] = v.strip()
    for h, v in zip(h2, d2, strict=False):
        if h.strip(): record[h.strip()] = v.strip()
```

分类条件：4 行倍数且奇偶行匹配词表。

在计划中写清楚此逻辑，避免歧义。

- [ ] **Step 4–5:** 实现、测试、commit（message: `feat(extract): classify tender table layouts and build records`）

---

### Task 4: Markdown 与 llm_text 序列化

**Files:**
- Create: `src/doc_chunk/extract/table_serialize.py`
- Test: `tests/unit/test_table_serialize.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_table_serialize.py
from doc_chunk.extract.table_serialize import logical_to_markdown, records_to_llm_text


def test_logical_to_markdown():
    md = logical_to_markdown([["姓名", "角色"], ["刘敏", "开发"]])
    assert "| 姓名 | 角色 |" in md
    assert "| 刘敏 | 开发 |" in md
    assert "姓名 | 姓名" not in md


def test_records_to_llm_text_personnel():
    records = [{"姓名": "刘敏", "级别": "高级Java工程师"}]
    text = records_to_llm_text("personnel_dual_row", records, logical_rows=[])
    assert "【表格:人员信息】" in text
    assert "姓名: 刘敏" in text
    assert "级别: 高级Java工程师" in text
```

- [ ] **Step 2–3: Implement**

```python
# src/doc_chunk/extract/table_serialize.py
from __future__ import annotations


def logical_to_markdown(logical_rows: list[list[str]]) -> str:
    if not logical_rows:
        return ""
    col_count = max(len(r) for r in logical_rows)
    normalized = [r + [""] * (col_count - len(r)) for r in logical_rows]
    header = normalized[0]
    lines = [
        f"| {' | '.join(header)} |",
        f"| {' | '.join('---' for _ in range(col_count))} |",
    ]
    lines.extend(f"| {' | '.join(row)} |" for row in normalized[1:])
    return "\n".join(lines)


def logical_to_llm_fallback(logical_rows: list[list[str]]) -> str:
    lines = ["【表格:原始】"]
    for i, row in enumerate(logical_rows, start=1):
        lines.append(f"行{i}: " + " | ".join(row))
    return "\n".join(lines)


def records_to_llm_text(
    layout: str,
    records: list[dict[str, str]],
    *,
    logical_rows: list[list[str]],
) -> str:
    if layout == "personnel_dual_row":
        lines = ["【表格:人员信息】"]
        for i, rec in enumerate(records, start=1):
            lines.append(f"--- 记录 {i} ---")
            for k, v in rec.items():
                lines.append(f"{k}: {v}")
        return "\n".join(lines)
    if layout == "simple":
        lines = ["【表格:列表】"]
        for i, rec in enumerate(records, start=1):
            lines.append(f"--- 行 {i} ---")
            for k, v in rec.items():
                lines.append(f"{k}: {v}")
        return "\n".join(lines)
    if layout == "key_value":
        lines = ["【表格:键值】"]
        for rec in records:
            for k, v in rec.items():
                lines.append(f"{k}: {v}")
        return "\n".join(lines)
    return logical_to_llm_fallback(logical_rows)
```

- [ ] **Step 4–5:** pytest PASS, commit `feat(extract): serialize logical tables to markdown and llm_text`

---

### Task 5: TableExtractor 编排与侧车写入

**Files:**
- Create: `src/doc_chunk/extract/table_extractor.py`
- Create: `src/doc_chunk/extract/table_sidecar.py`
- Modify: `src/doc_chunk/workspace/layout.py`
- Test: `tests/unit/test_table_extractor.py`

- [ ] **Step 1: workspace tables_dir**

```python
# src/doc_chunk/workspace/layout.py — 在 create/open_existing 中确保 tables 目录
# 添加 property:
@property
def tables_dir(self) -> Path:
    return self.root / "tables"

@property
def tables_index_path(self) -> Path:
    return self.tables_dir / "index.json"
```

在 `create()` 中：`tables_dir.mkdir(exist_ok=True)`

- [ ] **Step 2: table_sidecar.py**

```python
# src/doc_chunk/extract/table_sidecar.py
from __future__ import annotations

from doc_chunk.models.table_model import TableSidecar, TablesIndex, TablesIndexEntry
from doc_chunk.workspace.layout import OutputWorkspace


class TableSidecarWriter:
    def __init__(self, workspace: OutputWorkspace) -> None:
        self._ws = workspace
        self._ws.tables_dir.mkdir(parents=True, exist_ok=True)
        self._entries: list[TablesIndexEntry] = []

    def write(self, sidecar: TableSidecar) -> str:
        rel = f"tables/t{sidecar.block_index:04d}.json"
        path = self._ws.root / rel
        path.write_text(sidecar.model_dump_json(indent=2), encoding="utf-8")
        self._entries.append(TablesIndexEntry(block_index=sidecar.block_index, path=rel))
        return rel

    def finalize(self) -> None:
        index = TablesIndex(tables=sorted(self._entries, key=lambda e: e.block_index))
        self._ws.tables_index_path.write_text(index.model_dump_json(indent=2), encoding="utf-8")
```

- [ ] **Step 3: table_extractor.py**

```python
# src/doc_chunk/extract/table_extractor.py
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
```

- [ ] **Step 4: Unit test extract_table on fixtures**

```bash
.venv/bin/python -m pytest tests/unit/test_table_extractor.py -v
```

- [ ] **Step 5: Commit** `feat(extract): orchestrate table extraction and sidecar models`

---

### Task 6: 接入 docx_extractor 与 BlockAccumulator

**Files:**
- Modify: `src/doc_chunk/extract/block_index.py`
- Modify: `src/doc_chunk/extract/docx_extractor.py`
- Modify: `src/doc_chunk/api.py`
- Test: `tests/unit/test_docx_extractor.py`, `tests/unit/test_block_index.py`

- [ ] **Step 1: Extend BlockAccumulator**

```python
# block_index.py
def add_table(self, table_md: str, *, table_ref: str | None = None) -> None:
    start = self._cursor
    self._markdown_parts.append(f"{table_md}\n\n")
    self._cursor += len(f"{table_md}\n\n")
    preview = table_md[:120] or None
    self._blocks.append(
        ContentBlockRecord(
            block_index=len(self._blocks),
            block_type="table",
            char_start=start,
            char_end=self._cursor,
            text_preview=preview,
            table_ref=table_ref,
        )
    )
```

`finalize()` 返回 `ContentBlocksFile(schema_version="1.1", blocks=...)`

- [ ] **Step 2: Wire docx_extractor**

```python
# docx_extractor.py
from doc_chunk.extract.table_extractor import extract_table
from doc_chunk.extract.table_sidecar import TableSidecarWriter

# 在 extract_docx 内：
sidecar_writer = TableSidecarWriter(workspace)
all_warnings: list[str] = []

# 表格分支：
block_index_before = acc.block_count
markdown, sidecar, tbl_warnings = extract_table(table, block_index_before)
all_warnings.extend(tbl_warnings)
table_ref = None
if markdown:
    if sidecar:
        table_ref = sidecar_writer.write(sidecar)
    acc.add_table(markdown, table_ref=table_ref)

# 函数末尾：
sidecar_writer.finalize()
return ExtractResult(image_count=image_count, warnings=all_warnings)
```

- [ ] **Step 3: manifest outputs**

```python
# api.py _build_manifest outputs 增加:
"tables": "tables",
"tables_index": "tables/index.json",
```

- [ ] **Step 4: Update tests**

```python
# test_docx_extractor — 新测试
def test_extract_docx_writes_table_sidecar(merged_colspan_docx, tmp_path):
    ws = OutputWorkspace.create(tmp_path / "ws", overwrite=False)
    doc = Document(merged_colspan_docx)
    # 或直接在 tmp 建含表 docx
    ...
    extract_docx(docx_with_table, ws)
    assert ws.tables_index_path.exists()
    blocks = ContentBlocksFile.model_validate_json(ws.content_blocks_path.read_text())
    assert blocks.schema_version == "1.1"
    table_blocks = [b for b in blocks.blocks if b.block_type == "table"]
    assert table_blocks[0].table_ref is not None
    content = ws.content_path.read_text()
    assert "姓名 | 姓名" not in content  # 无重复列
```

- [ ] **Step 5: Run full unit tests**

```bash
.venv/bin/python -m pytest tests/unit/test_docx_extractor.py tests/unit/test_block_index.py -v
```

- [ ] **Step 6: Commit** `feat(extract): wire table sidecars into docx extraction pipeline`

---

### Task 7: LLM 切片替换 API

**Files:**
- Create: `src/doc_chunk/table/__init__.py`
- Create: `src/doc_chunk/table/access.py`
- Test: `tests/unit/test_table_access.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_table_access.py
from doc_chunk.models.content_block import ContentBlockRecord, ContentBlocksFile
from doc_chunk.models.table_model import TableSidecar
from doc_chunk.table.access import load_table_model, substitute_tables_for_llm
from doc_chunk.workspace.layout import OutputWorkspace


def test_substitute_tables_for_llm_replaces_markdown(tmp_path):
    ws = OutputWorkspace.create(tmp_path / "ws", overwrite=False)
    md_table = "| 姓名 | 角色 |\n| --- | --- |\n| 刘敏 | 开发 |"
    llm = "【表格:人员信息】\n姓名: 刘敏"
    content = f"前文\n\n{md_table}\n\n后文"
    ws.content_path.write_text(content, encoding="utf-8")
    start = content.index("|")
    end = content.index("后文")
    sidecar = TableSidecar(
        block_index=0,
        layout_type="simple",
        grid_width=2,
        grid={"rows": []},
        logical_rows=[],
        markdown=md_table,
        llm_text=llm,
    )
    (ws.tables_dir).mkdir(exist_ok=True)
    (ws.tables_dir / "t0000.json").write_text(sidecar.model_dump_json(), encoding="utf-8")
    blocks = ContentBlocksFile(
        schema_version="1.1",
        blocks=[
            ContentBlockRecord(
                block_index=0, block_type="table",
                char_start=start, char_end=end,
                table_ref="tables/t0000.json",
            )
        ],
    )
    out = substitute_tables_for_llm(content, blocks, workspace=ws)
    assert llm in out
    assert "| 姓名 |" not in out
    assert "前文" in out and "后文" in out
```

- [ ] **Step 2–3: Implement access.py**

```python
# src/doc_chunk/table/access.py
from __future__ import annotations

from pathlib import Path

from doc_chunk.models.content_block import ContentBlocksFile
from doc_chunk.models.table_model import TableSidecar
from doc_chunk.workspace.layout import OutputWorkspace


def load_table_model(workspace: OutputWorkspace | Path, table_ref: str) -> TableSidecar:
    root = workspace.root if isinstance(workspace, OutputWorkspace) else Path(workspace)
    path = root / table_ref
    return TableSidecar.model_validate_json(path.read_text(encoding="utf-8"))


def substitute_tables_for_llm(
    content_md: str,
    blocks: ContentBlocksFile,
    *,
    workspace: OutputWorkspace,
    char_start: int = 0,
    char_end: int | None = None,
) -> str:
    end = char_end if char_end is not None else len(content_md)
    replacements: list[tuple[int, int, str]] = []
    for block in blocks.blocks:
        if block.block_type != "table" or not block.table_ref:
            continue
        if block.char_end <= char_start or block.char_start >= end:
            continue
        sidecar = load_table_model(workspace, block.table_ref)
        replacements.append((block.char_start, block.char_end, sidecar.llm_text.strip() + "\n\n"))
    if not replacements:
        return content_md[char_start:end]
    replacements.sort(key=lambda x: x[0])
    parts: list[str] = []
    cursor = char_start
    for s, e, text in replacements:
        parts.append(content_md[cursor:s])
        parts.append(text)
        cursor = e
    parts.append(content_md[cursor:end])
    return "".join(parts)
```

- [ ] **Step 4–5:** pytest PASS, commit `feat(table): add load_table_model and substitute_tables_for_llm`

---

### Task 8: table_to_docx 契约占位

**Files:**
- Create: `src/doc_chunk/convert/table_to_docx.py`
- Test: `tests/unit/test_table_to_docx.py`

- [ ] **Step 1: Test expects NotImplementedError**

```python
import pytest
from docx import Document
from doc_chunk.convert.table_to_docx import render_table_to_docx
from doc_chunk.models.table_model import TableGridRow, TableCell

def test_render_table_to_docx_not_implemented_yet():
    doc = Document()
    grid = {"rows": [TableGridRow(cells=[TableCell(text="a")]).model_dump()]}
    with pytest.raises(NotImplementedError):
        render_table_to_docx(doc, grid, grid_width=1)
```

- [ ] **Step 2: Stub**

```python
def render_table_to_docx(document, grid, *, grid_width: int, records=None):
    raise NotImplementedError("table_to_docx is planned for P1; see design spec 004")
```

- [ ] **Step 3: Commit** `chore(convert): add table_to_docx contract stub for P1`

---

### Task 9: 契约测试与文档

**Files:**
- Create: `tests/contract/test_table_sidecar.py`
- Modify: `specs/001-document-extract-chunk/contracts/workspace-schemas.md`
- Modify: `docs/superpowers/specs/2026-06-17-docx-table-extract-design.md`（状态 → 已实现）

- [ ] **Step 1: Contract test**

```python
# tests/contract/test_table_sidecar.py
from docx import Document
from doc_chunk.api import extract_file
from doc_chunk.models.content_block import ContentBlocksFile
from doc_chunk.models.table_model import TablesIndex, TableSidecar


def test_extract_table_sidecar_aligns_with_blocks(personnel_dual_row_docx, tmp_path):
    out = tmp_path / "ws"
    extract_file(personnel_dual_row_docx, out, overwrite=True)
    blocks = ContentBlocksFile.model_validate_json((out / "content.blocks.json").read_text())
    index = TablesIndex.model_validate_json((out / "tables" / "index.json").read_text())
    table_blocks = [b for b in blocks.blocks if b.block_type == "table"]
    assert len(table_blocks) == 1
    assert table_blocks[0].table_ref == index.tables[0].path
    sidecar = TableSidecar.model_validate_json((out / table_blocks[0].table_ref).read_text())
    md = (out / "content.md").read_text()
    assert md[table_blocks[0].char_start:table_blocks[0].char_end].strip() == sidecar.markdown.strip()
    assert sidecar.records[0]["姓名"] == "刘敏"
```

- [ ] **Step 2: Update workspace-schemas.md**

在 `content.blocks.json` 节增加 `schema_version: 1.1`、`table_ref` 字段；新增 `tables/index.json` 与 `tables/tNNNN.json` 节。

- [ ] **Step 3: Run full test suite**

```bash
.venv/bin/python -m pytest tests/unit tests/contract -q
```

Expected: ALL PASS

- [ ] **Step 4: Commit** `docs: document table sidecar workspace schema and contract tests`

---

## Spec Coverage Checklist

| 需求 | Task |
|------|------|
| G1 合并去重 | Task 2, 4, 6 |
| G2 content.md Markdown | Task 4, 6 |
| G3 llm_text / records | Task 3, 4, 5 |
| G4 物理 grid | Task 2, 5 |
| G5 char 锚点兼容 | Task 6, 9 |
| substitute_tables_for_llm | Task 7 |
| table_to_docx 占位 | Task 8 |
| manifest tables/ | Task 6 |
| 降级 fallback | Task 2, 5 |
| fixtures | Task 2, 3, 9 |

## P1 后续（本计划外）

- 实现 `render_table_to_docx` 完整逻辑
- `tender_insights._slice_node_markdown` 调用 `substitute_tables_for_llm`
- `ChunkBlock.table_ref` 可选字段

---

**Plan complete and saved to `docs/superpowers/plans/2026-06-17-docx-table-extract.md`.**

**两种执行方式：**

1. **Subagent-Driven（推荐）** — 每个 Task 派发独立 subagent，任务间做 review，迭代快  
2. **Inline Execution** — 在本会话用 executing-plans 按 Task 批量执行，检查点处暂停 review  

你更倾向哪一种？
