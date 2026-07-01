# doc_chunk 原表切片（mini-docx）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract 阶段为每张表生成自包含 mini-docx 切片（`tables/t{NNNN}.docx`），Viewer 下载与 `patch_docx_tables()` 优先使用切片实现 Word 完整保真；JSON 侧车继续服务 LLM/结构化消费。

**Architecture:** Extract 在写 JSON 侧车后调用 `build_mini_docx_for_table()`，通过 OPC 层 deep-copy `w:tbl` 并 graft 源 docx 的 styles/theme/numbering/media 部件到最小 docx 包。Export/patch 读取 sidecar 的 `slice_ref`/`slice_status`，`ok` 时直接返回 slice 或 `embed_table_from_slice()`；否则降级现有 `render_sidecar_to_docx()`。

**Tech Stack:** Python 3.11+, python-docx (OPC package API), pydantic v2, lxml, pytest

**需求来源:** [`docs/superpowers/specs/2026-07-01-doc-chunk-table-ooxml-slice-design.md`](../specs/2026-07-01-doc-chunk-table-ooxml-slice-design.md)

---

## File Structure

```text
src/doc_chunk/
├── models/
│   ├── table_model.py              # MODIFY: schema 1.1 slice_ref, slice_status
│   └── tables_manifest.py          # MODIFY: slice_ref, slice_status, slice_byte_size
├── extract/
│   ├── table_sidecar.py            # MODIFY: write schema 1.1 fields
│   ├── table_slice.py              # NEW: extract_table_slice orchestrator
│   └── docx_extractor.py           # MODIFY: call extract_table_slice after JSON write
├── table/
│   ├── slice_deps.py               # NEW: XML walk — media rIds, style ids
│   ├── slice_pack.py               # NEW: build_mini_docx_for_table
│   ├── embed.py                    # NEW: embed_table_from_slice + graft_parts
│   ├── assets.py                   # MODIFY: manifest slice metadata
│   └── patch.py                    # MODIFY: prefer embed over grid rebuild
└── convert/
    └── table_export.py             # MODIFY: prefer slice bytes

tests/
├── unit/
│   ├── test_table_model.py         # MODIFY: schema 1.1 roundtrip
│   ├── test_table_slice_deps.py    # NEW
│   ├── test_table_slice_pack.py    # NEW
│   ├── test_table_embed.py         # NEW
│   ├── test_table_export_slice.py  # NEW
│   ├── test_table_patch_slice.py   # NEW
│   └── test_table_assets.py        # MODIFY: slice fields in manifest
├── integration/
│   └── test_table_slice_extract.py # NEW: extract_docx end-to-end
└── conftest.py                     # MODIFY: sample_docx_with_styled_table fixture

specs/001-document-extract-chunk/contracts/workspace-schemas.md  # MODIFY: schema 1.1 slice fields
```

P1（本计划不含实现步骤，spec 已标注）：`viewer/viewer/routes/content.py` 增加 `X-Table-Export-Mode` 响应头；tender_knowledge 适配层双 blob 落库。

---

### Task 1: Sidecar 与 Manifest schema 1.1 模型

**Files:**
- Modify: `src/doc_chunk/models/table_model.py`
- Modify: `src/doc_chunk/models/tables_manifest.py`
- Modify: `tests/unit/test_table_model.py`
- Modify: `tests/unit/test_table_placeholders.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_table_model.py — append
def test_table_sidecar_schema_1_1_slice_fields() -> None:
    sidecar = TableSidecar(
        schema_version="1.1",
        block_index=3,
        slice_ref="tables/t0003.docx",
        slice_status="ok",
        layout_type="simple",
        grid_width=2,
        grid={"rows": []},
        logical_rows=[["a", "b"]],
        markdown="| a | b |",
        llm_text="table",
    )
    parsed = TableSidecar.model_validate_json(sidecar.model_dump_json())
    assert parsed.schema_version == "1.1"
    assert parsed.slice_ref == "tables/t0003.docx"
    assert parsed.slice_status == "ok"


def test_table_sidecar_schema_1_0_defaults_missing_slice() -> None:
    raw = TableSidecar(
        block_index=0,
        layout_type="simple",
        grid_width=1,
        grid={"rows": []},
        logical_rows=[],
        markdown="| a |",
        llm_text="t",
    ).model_dump_json()
    parsed = TableSidecar.model_validate_json(raw)
    assert parsed.schema_version == "1.0"
    assert parsed.slice_ref is None
    assert parsed.slice_status == "missing"
```

```python
# tests/unit/test_table_placeholders.py — append
def test_tables_manifest_schema_1_1_slice_fields() -> None:
    manifest = TablesManifest(
        schema_version="1.1",
        tables=[
            TableManifestEntry(
                table_ref="tables/t0003.json",
                slice_ref="tables/t0003.docx",
                slice_status="ok",
                slice_byte_size=4096,
                source_block_index=3,
                layout_type="simple",
                row_count=2,
                col_count=2,
                char_start=0,
                char_end=50,
            )
        ],
    )
    assert manifest.schema_version == "1.1"
    assert manifest.tables[0].slice_byte_size == 4096
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_table_model.py::test_table_sidecar_schema_1_1_slice_fields tests/unit/test_table_placeholders.py::test_tables_manifest_schema_1_1_slice_fields -v`  
Expected: FAIL — `slice_ref` / `slice_status` unexpected keyword

- [ ] **Step 3: Write minimal implementation**

```python
# src/doc_chunk/models/table_model.py — TableSidecar 扩展
from typing import Literal

SliceStatus = Literal["ok", "failed", "missing"]

class TableSidecar(BaseModel):
    schema_version: Literal["1.0", "1.1"] = "1.0"
    block_index: int
    slice_ref: str | None = None
    slice_status: SliceStatus = "missing"
    layout_type: Literal["personnel_dual_row", "simple", "key_value", "fallback"]
    # ... 其余字段不变
```

```python
# src/doc_chunk/models/tables_manifest.py
SliceStatus = Literal["ok", "failed", "missing"]

class TableManifestEntry(BaseModel):
    table_ref: str
    slice_ref: str | None = None
    slice_status: SliceStatus = "missing"
    slice_byte_size: int | None = None
    source_block_index: int
    layout_type: str
    row_count: int
    col_count: int
    char_start: int
    char_end: int
    markdown_preview: str | None = None


class TablesManifest(BaseModel):
    schema_version: Literal["1.0", "1.1"] = "1.0"
    tables: list[TableManifestEntry] = Field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_table_model.py tests/unit/test_table_placeholders.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/doc_chunk/models/table_model.py src/doc_chunk/models/tables_manifest.py \
  tests/unit/test_table_model.py tests/unit/test_table_placeholders.py
git commit -m "feat(table): add schema 1.1 slice fields to sidecar and manifest"
```

---

### Task 2: 表格 XML 依赖收集（slice_deps）

**Files:**
- Create: `src/doc_chunk/table/slice_deps.py`
- Create: `tests/unit/test_table_slice_deps.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_table_slice_deps.py
from __future__ import annotations

from pathlib import Path

import pytest
from docx import Document

from doc_chunk.table.slice_deps import (
    collect_embed_relationship_ids,
    collect_style_ids_from_tbl,
    iter_tbl_elements,
)


@pytest.fixture
def docx_with_table_and_image(tmp_path: Path) -> Path:
    path = tmp_path / "tbl_img.docx"
    img = tmp_path / "cell.png"
    img.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
        b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
        b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    doc = Document()
    table = doc.add_table(rows=1, cols=1)
    table.cell(0, 0).paragraphs[0].add_run().add_picture(str(img))
    doc.save(path)
    return path


def test_collect_embed_relationship_ids_finds_cell_image(docx_with_table_and_image: Path) -> None:
    doc = Document(docx_with_table_and_image)
    tbl = doc.tables[0]._tbl
    rids = collect_embed_relationship_ids(tbl)
    assert len(rids) >= 1


def test_collect_style_ids_from_tbl_returns_set(docx_with_table_and_image: Path) -> None:
    doc = Document(docx_with_table_and_image)
    tbl = doc.tables[0]._tbl
    styles = collect_style_ids_from_tbl(tbl)
    assert isinstance(styles, set)


def test_iter_tbl_elements_yields_tbl_only(docx_with_table_and_image: Path) -> None:
    doc = Document(docx_with_table_and_image)
    tags = [el.tag.split("}")[-1] for el in iter_tbl_elements(doc.tables[0]._tbl)]
    assert "tbl" in tags
    assert "tr" in tags
    assert "tc" in tags
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_table_slice_deps.py -v`  
Expected: FAIL — `ModuleNotFoundError: doc_chunk.table.slice_deps`

- [ ] **Step 3: Write minimal implementation**

```python
# src/doc_chunk/table/slice_deps.py
from __future__ import annotations

from collections.abc import Iterator

from docx.oxml.ns import qn
from lxml.etree import _Element as OxmlElement

EMBED_ATTR = qn("r:embed")
LINK_ATTR = qn("r:link")
STYLE_VAL_ATTR = qn("w:val")
STYLE_TAGS = {
    qn("w:tblStyle"),
    qn("w:pStyle"),
    qn("w:rStyle"),
    qn("w:tblStyle"),
}
STYLE_LIKE = {qn("w:tblStyle"), qn("w:pStyle"), qn("w:rStyle"), qn("w:tcStyle")}


def iter_tbl_elements(tbl: OxmlElement) -> Iterator[OxmlElement]:
    yield tbl
    for el in tbl.iter():
        if el is not tbl:
            yield el


def collect_embed_relationship_ids(tbl: OxmlElement) -> set[str]:
    ids: set[str] = set()
    for el in iter_tbl_elements(tbl):
        for attr in (EMBED_ATTR, LINK_ATTR):
            val = el.get(attr)
            if val:
                ids.add(val)
    return ids


def collect_style_ids_from_tbl(tbl: OxmlElement) -> set[str]:
    ids: set[str] = set()
    for el in iter_tbl_elements(tbl):
        tag = el.tag
        if tag in STYLE_LIKE:
            val = el.get(STYLE_VAL_ATTR)
            if val:
                ids.add(val)
    return ids
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_table_slice_deps.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/doc_chunk/table/slice_deps.py tests/unit/test_table_slice_deps.py
git commit -m "feat(table): add slice dependency collectors for tbl XML"
```

---

### Task 3: MiniDocxBuilder — 组装自包含 mini-docx

**Files:**
- Create: `src/doc_chunk/table/slice_pack.py`
- Create: `tests/unit/test_table_slice_pack.py`
- Modify: `tests/conftest.py`（新增 `sample_docx_with_styled_table` fixture）

- [ ] **Step 1: Write the failing test**

```python
# tests/conftest.py — append fixture
@pytest.fixture
def sample_docx_with_styled_table(tmp_path: Path) -> Path:
    path = tmp_path / "styled_table.docx"
    doc = Document()
    table = doc.add_table(rows=2, cols=2)
    table.style = "Table Grid"
    table.cell(0, 0).text = "Header"
    table.cell(0, 1).text = "Value"
    table.cell(1, 0).text = "A"
    table.cell(1, 1).text = "B"
    doc.save(path)
    return path
```

```python
# tests/unit/test_table_slice_pack.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_table_slice_pack.py -v`  
Expected: FAIL — `ModuleNotFoundError: doc_chunk.table.slice_pack`

- [ ] **Step 3: Write minimal implementation**

```python
# src/doc_chunk/table/slice_pack.py
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from docx import Document
from docx.table import Table as DocxTable

# P0: 整包拷贝以下部件以保证完整保真；体积换正确性
_WHOLE_PARTS = (
    "word/styles.xml",
    "word/theme/theme1.xml",
    "word/fontTable.xml",
    "word/numbering.xml",
    "word/settings.xml",
)


def _replace_body_with_table(dest_doc: Document, tbl_copy) -> None:
    body = dest_doc.element.body
    for child in list(body):
        body.remove(child)
    body.append(tbl_copy)
    sect_pr = dest_doc.element.body.get_or_add_sectPr()
    body.append(sect_pr)


def _graft_whole_parts(source_doc: Document, dest_doc: Document) -> None:
    src_pkg = source_doc.part.package
    dst_pkg = dest_doc.part.package
    for partname in _WHOLE_PARTS:
        if partname in src_pkg.parts:
            src_part = src_pkg.parts[partname]
            if partname in dst_pkg.parts:
                dst_pkg.parts[partname]._blob = src_part.blob
            else:
                dst_pkg.parts[partname] = src_part


def _graft_media_parts(source_doc: Document, dest_doc: Document, tbl_element) -> None:
    from doc_chunk.table.slice_deps import collect_embed_relationship_ids

    src_part = source_doc.part
    dst_part = dest_doc.part
    for rid in collect_embed_relationship_ids(tbl_element):
        if rid not in src_part.rels:
            continue
        rel = src_part.rels[rid]
        if rel.is_external:
            dst_part.rels.add_relationship(rel.reltype, rel.target_ref, rid, is_external=True)
        else:
            new_rel = dst_part.rels.get_or_add(rel.reltype, rel.target_part)
            # 更新 tbl 内 rId 引用
            for el in tbl_element.iter():
                for attr_qn in (rel.target_part.partname,):  # replaced below
                    pass
            # 简化 P0：直接按 rel.target_part 复制 blob 到新 part
            dst_part.relate_to(rel.target_part, rel.reltype, rid)


def build_mini_docx_for_table(source_table: DocxTable, dest_path: Path) -> None:
    source_doc = source_table._parent
    tbl_copy = deepcopy(source_table._tbl)

    dest_doc = Document()
    _replace_body_with_table(dest_doc, tbl_copy)
    _graft_whole_parts(source_doc, dest_doc)
    _graft_media_parts(source_doc, dest_doc, tbl_copy)

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_doc.save(dest_path)
```

**实现说明（工程师必读）：** `_graft_media_parts` 中 rId remap 是 P0 关键路径。若 `relate_to` 不能直接指定 rId，则改为：遍历 `tbl_copy` 中所有 `r:embed`/`r:link`，为每个源 rId 在目标 part 新建 relationship，用 `el.set(qn("r:embed"), new_rid)` 替换。参考 python-docx `DocumentPart.relate_to` 与 `InlineShape` 的图片嵌入逻辑。单元测试 Task 3 通过后，Task 3b 补充 cell 内图片 fixture 测试。

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_table_slice_pack.py -v`  
Expected: PASS（若 media graft 未完成，先让无图表格通过，图片测试在 Step 3 完善 `_graft_media_parts` 后补跑）

- [ ] **Step 5: Commit**

```bash
git add src/doc_chunk/table/slice_pack.py tests/unit/test_table_slice_pack.py tests/conftest.py
git commit -m "feat(table): build self-contained mini-docx slice from source table"
```

---

### Task 4: Extract 集成 — extract_table_slice + sidecar 写入

**Files:**
- Create: `src/doc_chunk/extract/table_slice.py`
- Modify: `src/doc_chunk/extract/table_sidecar.py`
- Modify: `src/doc_chunk/extract/docx_extractor.py`
- Create: `tests/integration/test_table_slice_extract.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_table_slice_extract.py
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
    assert (ws.root / sidecar.slice_ref).is_file()
    assert (ws.root / sidecar.slice_ref).read_bytes()[:2] == b"PK"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/integration/test_table_slice_extract.py -v`  
Expected: FAIL — `slice_status` 仍为 `missing` 或 slice 文件不存在

- [ ] **Step 3: Write minimal implementation**

```python
# src/doc_chunk/extract/table_slice.py
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
```

```python
# src/doc_chunk/extract/table_sidecar.py — write() 扩展
def write(
    self,
    sidecar: TableSidecar,
    *,
    slice_ref: str | None = None,
    slice_status: SliceStatus = "missing",
) -> str:
    rel = f"tables/t{sidecar.block_index:04d}.json"
    payload = sidecar.model_copy(
        update={
            "schema_version": "1.1",
            "slice_ref": slice_ref,
            "slice_status": slice_status,
        }
    )
    path = self._ws.root / rel
    path.write_text(payload.model_dump_json(indent=2), encoding="utf-8")
    ...
```

```python
# src/doc_chunk/extract/docx_extractor.py — tbl 分支内，sidecar_writer.write 前
if sidecar:
    slice_ref, slice_status, slice_warnings = extract_table_slice(
        table, sidecar.block_index, workspace.root
    )
    all_warnings.extend(slice_warnings)
    table_ref = sidecar_writer.write(
        sidecar, slice_ref=slice_ref, slice_status=slice_status
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/integration/test_table_slice_extract.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/doc_chunk/extract/table_slice.py src/doc_chunk/extract/table_sidecar.py \
  src/doc_chunk/extract/docx_extractor.py tests/integration/test_table_slice_extract.py
git commit -m "feat(extract): emit self-contained table slice docx alongside JSON sidecar"
```

---

### Task 5: Export 优先返回 slice

**Files:**
- Modify: `src/doc_chunk/convert/table_export.py`
- Create: `tests/unit/test_table_export_slice.py`
- Modify: `tests/unit/test_document_assets.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_table_export_slice.py
from __future__ import annotations

from pathlib import Path

from docx import Document

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
    ws = OutputWorkspace.create(tmp_path / "ws", overwrite=True)
    ref = _write_sidecar_with_slice(ws, slice_status="missing", slice_bytes=None)
    data = export_table_ref_to_docx_bytes(ws, ref)
    assert data[:2] == b"PK"
    assert data != b"PKSLICE"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_table_export_slice.py -v`  
Expected: FAIL — export 仍走 grid 重建，不返回 slice 字节

- [ ] **Step 3: Write minimal implementation**

```python
# src/doc_chunk/convert/table_export.py
from doc_chunk.models.table_model import SliceStatus


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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_table_export_slice.py tests/unit/test_document_assets.py::test_export_table_ref_to_docx_bytes -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/doc_chunk/convert/table_export.py tests/unit/test_table_export_slice.py
git commit -m "feat(table): prefer mini-docx slice for table export"
```

---

### Task 6: TableEmbedder — patch 时注入 slice

**Files:**
- Create: `src/doc_chunk/table/embed.py`
- Create: `tests/unit/test_table_embed.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_table_embed.py
from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.text.paragraph import Paragraph

from doc_chunk.table.embed import embed_table_from_slice
from doc_chunk.table.slice_pack import build_mini_docx_for_table


def test_embed_table_from_slice_inserts_word_table(
    sample_docx_with_styled_table: Path, tmp_path: Path
) -> None:
    source = Document(sample_docx_with_styled_table)
    slice_path = tmp_path / "slice.docx"
    build_mini_docx_for_table(source.tables[0], slice_path)

    target = Document()
    anchor = target.add_paragraph("<!-- table-ref:tables/t0000.json -->")
    target.add_paragraph("| H | V |")

    embed_table_from_slice(target, slice_path, anchor)

    assert len(target.tables) == 1
    assert target.tables[0].cell(0, 0).text == "Header"
    assert "<!-- table-ref:" not in anchor.text or anchor._element.getparent() is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_table_embed.py -v`  
Expected: FAIL — `ModuleNotFoundError: doc_chunk.table.embed`

- [ ] **Step 3: Write minimal implementation**

```python
# src/doc_chunk/table/embed.py
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from docx import Document
from docx.text.paragraph import Paragraph

from doc_chunk.table.slice_pack import _graft_media_parts, _graft_whole_parts


def embed_table_from_slice(
    target_doc: Document,
    slice_path: Path,
    before_paragraph: Paragraph,
) -> None:
    slice_doc = Document(slice_path)
    if not slice_doc.tables:
        raise ValueError(f"slice has no table: {slice_path}")
    tbl_copy = deepcopy(slice_doc.tables[0]._tbl)

    _graft_whole_parts(slice_doc, target_doc)
    _graft_media_parts(slice_doc, target_doc, tbl_copy)

    before_paragraph._p.addprevious(tbl_copy)
```

**实现说明：** `_graft_whole_parts` / `_graft_media_parts` 应从 `slice_pack.py` 提取到 `table/slice_graft.py` 供 pack 与 embed 共用，避免循环 import。embed 时若 style id 冲突，P0 策略：后写入的 slice styles 覆盖目标同名 style（记录 warning）；单表失败时由 patch 捕获并 fallback。

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_table_embed.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/doc_chunk/table/embed.py src/doc_chunk/table/slice_graft.py \
  tests/unit/test_table_embed.py
git commit -m "feat(table): embed mini-docx slice into target document"
```

---

### Task 7: patch_docx_tables 优先 embed slice

**Files:**
- Modify: `src/doc_chunk/table/patch.py`
- Create: `tests/unit/test_table_patch_slice.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_table_patch_slice.py
from __future__ import annotations

from pathlib import Path

from docx import Document

from doc_chunk.extract.block_index import BlockAccumulator, write_accumulator_markdown, write_content_blocks
from doc_chunk.extract.docx_extractor import extract_docx
from doc_chunk.table.patch import patch_docx_tables
from doc_chunk.workspace.layout import OutputWorkspace


def test_patch_docx_tables_uses_slice_when_ok(
    sample_docx_with_styled_table: Path, tmp_path: Path
) -> None:
    ws = OutputWorkspace.create(tmp_path / "ws", overwrite=True)
    extract_docx(sample_docx_with_styled_table, ws)

    md = ws.content_path.read_text(encoding="utf-8")
    doc = Document()
    for line in md.splitlines():
        doc.add_paragraph(line)

    result = patch_docx_tables(doc, ws)
    assert result.patched_count == 1
    assert len(doc.tables) == 1
    # slice 保真：源表 cell 文本
    assert doc.tables[0].cell(0, 0).text == "Header"
    assert result.warnings == [] or all("fallback" not in w for w in result.warnings)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_table_patch_slice.py -v`  
Expected: FAIL — patch 仍走 grid 重建，或 cell 文本不匹配 slice

- [ ] **Step 3: Write minimal implementation**

```python
# src/doc_chunk/table/patch.py — 修改 _insert_table_before_paragraph 调用链
from doc_chunk.table.embed import embed_table_from_slice


def _insert_table_from_sidecar(
    document: Document,
    paragraph: Paragraph,
    sidecar: TableSidecar,
    ws: OutputWorkspace,
    result: PatchResult,
) -> bool:
    if sidecar.slice_status == "ok" and sidecar.slice_ref:
        slice_path = ws.root / sidecar.slice_ref
        if slice_path.is_file():
            try:
                embed_table_from_slice(document, slice_path, paragraph)
                return True
            except Exception as exc:
                result.warnings.append(f"table_embed_fallback:{sidecar.slice_ref}:{exc}")
    table = render_sidecar_to_docx(document, sidecar)
    paragraph._p.addprevious(table._tbl)
    return True
```

在 `patch_docx_tables` 循环中，将 `_insert_table_before_paragraph` 替换为 `_insert_table_from_sidecar`。

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_table_patch.py tests/unit/test_table_patch_slice.py -v`  
Expected: PASS（旧测试仍通过 — 无 slice 时走 rebuild）

- [ ] **Step 5: Commit**

```bash
git add src/doc_chunk/table/patch.py tests/unit/test_table_patch_slice.py
git commit -m "feat(table): patch docx tables via mini-docx slice when available"
```

---

### Task 8: collect_table_assets 汇总 slice 元数据

**Files:**
- Modify: `src/doc_chunk/table/assets.py`
- Modify: `tests/unit/test_table_assets.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_table_assets.py — append
def test_collect_table_assets_includes_slice_metadata(tmp_path: Path) -> None:
    ws = OutputWorkspace.create(tmp_path / "ws-slice", overwrite=True)
    ref = "tables/t0000.json"
    slice_ref = "tables/t0000.docx"
    sidecar = TableSidecar(
        schema_version="1.1",
        block_index=0,
        slice_ref=slice_ref,
        slice_status="ok",
        layout_type="simple",
        grid_width=2,
        grid={"rows": []},
        logical_rows=[["a", "b"]],
        markdown="| a | b |",
        llm_text="table",
    )
    (ws.root / ref).write_text(sidecar.model_dump_json(indent=2), encoding="utf-8")
    (ws.root / slice_ref).write_bytes(b"PK" + b"x" * 100)

    acc = BlockAccumulator()
    acc.add_table("| a | b |", table_ref=ref)
    write_accumulator_markdown(ws, acc)
    write_content_blocks(ws, acc.finalize())

    manifest = collect_table_assets(ws, write_manifest=True)
    entry = manifest.tables[0]
    assert manifest.schema_version == "1.1"
    assert entry.slice_ref == slice_ref
    assert entry.slice_status == "ok"
    assert entry.slice_byte_size == 102
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_table_assets.py::test_collect_table_assets_includes_slice_metadata -v`  
Expected: FAIL — manifest `schema_version` 仍为 `1.0`，无 slice 字段

- [ ] **Step 3: Write minimal implementation**

```python
# src/doc_chunk/table/assets.py — collect loop 内
slice_ref = sidecar.slice_ref
slice_status = sidecar.slice_status
slice_byte_size = None
if slice_ref and (ws.root / slice_ref).is_file():
    slice_byte_size = (ws.root / slice_ref).stat().st_size

entries.append(
    TableManifestEntry(
        table_ref=block.table_ref,
        slice_ref=slice_ref,
        slice_status=slice_status,
        slice_byte_size=slice_byte_size,
        ...
    )
)
manifest = TablesManifest(schema_version="1.1", tables=...)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_table_assets.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/doc_chunk/table/assets.py tests/unit/test_table_assets.py
git commit -m "feat(table): include slice metadata in tables manifest"
```

---

### Task 9: 契约文档与回归测试

**Files:**
- Modify: `specs/001-document-extract-chunk/contracts/workspace-schemas.md`
- Modify: `tests/contract/test_table_sidecar.py`（若存在）

- [ ] **Step 1: 更新 workspace-schemas.md**

在 `tables/t{NNNN}.json` 节追加 schema 1.1 字段：

```markdown
### tables/t{NNNN}.json schema 1.1

| 字段 | 类型 | 说明 |
|------|------|------|
| `slice_ref` | string \| null | mini-docx 相对路径，如 `tables/t0003.docx` |
| `slice_status` | `ok` \| `failed` \| `missing` | 切片状态 |

### tables/manifest.json schema 1.1

新增 `slice_ref`, `slice_status`, `slice_byte_size`；`schema_version` 升为 `1.1`。

### Schema Evolution

| 1.2 | 侧车/manifest schema 1.1；新增 `tables/t{NNNN}.docx` mini-docx 切片 |
```

- [ ] **Step 2: 契约/回归测试**

Run: `.venv/bin/pytest tests/unit/test_table_patch.py tests/unit/test_table_export_slice.py tests/integration/test_table_slice_extract.py tests/contract/ -v`  
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add specs/001-document-extract-chunk/contracts/workspace-schemas.md
git commit -m "docs(contract): document table slice schema 1.1 and mini-docx assets"
```

---

## Self-Review

**1. Spec coverage**

| Spec 要求 | 对应 Task |
|-----------|-----------|
| Extract mini-docx | Task 3, 4 |
| schema 1.1 sidecar/manifest | Task 1, 8 |
| export 优先 slice | Task 5 |
| patch 优先 embed | Task 6, 7 |
| collect_table_assets slice 元数据 | Task 8 |
| 降级 grid 重建 | Task 5, 7（`_slice_is_usable` / embed fallback） |
| 单元/集成测试 | Task 2–7, 9 |
| tk 落库 / Viewer 响应头 | P1，本计划标注为非 P0 |

**2. Placeholder scan:** 无 TBD；Task 3 media graft 有明确实现说明。

**3. Type consistency:** `SliceStatus` 在 `table_model.py` 定义；`table_sidecar.write(slice_status=...)` 与 sidecar 字段一致；`slice_ref_for_block_index` 与 sidecar 路径 `tables/t{NNNN}.docx` 一致。

**4. 风险备注:** `_graft_media_parts` rId remap 是最高风险点；Task 3 完成后必须用 `sample_docx_with_reused_image_in_body_and_table` fixture 补测 cell 内图片。

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-01-doc-chunk-table-ooxml-slice.md`. Two execution options:

**1. Subagent-Driven (recommended)** — 每个 Task 派一个全新 subagent，Task 间做 review，迭代快

**2. Inline Execution** — 在本会话用 executing-plans 按 Task 批量执行，checkpoint 处暂停 review

Which approach?
