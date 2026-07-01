# doc_chunk 表格资产提取与回插 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 doc_chunk 中补齐表格资产链路——占位符、`tables/manifest.json`、`collect_table_assets()`、`ChunkBlock.table_ref`、`blocks_v1` asset 映射、`patch_docx_tables()` 后置回插——对齐现有图片资产模式。

**Architecture:** extract 阶段在 markdown 表格前写入 `<!-- table-ref:... -->` 隐藏占位符；`collect_table_assets()` 从 `content.blocks.json` + 侧车汇总 manifest；chunk 阶段 `build_chunk_blocks` 解析占位符写入 `table_ref`；生成 docx 后 `patch_docx_tables()` 扫描占位符段落，用 `render_sidecar_to_docx` 插入物理表格并删除占位符/markdown 段落。

**Tech Stack:** Python 3.11+, python-docx, pydantic v2, pytest

**需求来源:** [`docs/superpowers/specs/2026-07-01-doc-chunk-table-assets-design.md`](../specs/2026-07-01-doc-chunk-table-assets-design.md)

---

## File Structure

```text
src/doc_chunk/
├── models/
│   ├── chunk.py                    # MODIFY: ChunkBlock.table_ref
│   └── tables_manifest.py          # NEW: TableManifestEntry, TablesManifest
├── table/
│   ├── __init__.py                 # MODIFY: export new APIs
│   ├── placeholders.py             # NEW: regex + format helpers
│   ├── assets.py                   # NEW: collect_table_assets
│   └── patch.py                    # NEW: patch_docx_tables, PatchResult
├── extract/
│   ├── block_index.py              # MODIFY: add_table writes placeholder
│   └── docx_extractor.py           # MODIFY: call collect_table_assets
├── chunk/
│   └── blocks_builder.py           # MODIFY: parse table-ref comment
├── convert/
│   └── blocks_v1.py                # MODIFY: table_ref_to_asset_id
├── workspace/
│   └── layout.py                   # MODIFY: tables_manifest_path
└── api.py                          # MODIFY: manifest outputs

tests/
├── unit/
│   ├── test_table_placeholders.py  # NEW
│   ├── test_table_assets.py        # NEW
│   ├── test_table_patch.py         # NEW
│   ├── test_block_index.py         # MODIFY
│   ├── test_blocks_builder.py      # MODIFY
│   └── test_blocks_v1_convert.py   # MODIFY
└── contract/
    └── test_table_sidecar.py       # MODIFY: placeholder + manifest asserts

specs/001-document-extract-chunk/contracts/workspace-schemas.md  # MODIFY
```

---

### Task 1: 占位符常量与 TablesManifest 模型

**Files:**
- Create: `src/doc_chunk/table/placeholders.py`
- Create: `src/doc_chunk/models/tables_manifest.py`
- Create: `tests/unit/test_table_placeholders.py`
- Modify: `src/doc_chunk/workspace/layout.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_table_placeholders.py
from doc_chunk.models.tables_manifest import TableManifestEntry, TablesManifest
from doc_chunk.table.placeholders import (
    TABLE_REF_COMMENT_RE,
    format_table_ref_comment,
    parse_table_ref_from_line,
)


def test_format_table_ref_comment() -> None:
    assert format_table_ref_comment("tables/t0003.json") == "<!-- table-ref:tables/t0003.json -->"


def test_parse_table_ref_from_comment_line() -> None:
    line = "<!-- table-ref:tables/t0003.json -->"
    assert parse_table_ref_from_line(line) == "tables/t0003.json"
    assert parse_table_ref_from_line("| a | b |") is None


def test_table_ref_comment_regex() -> None:
    m = TABLE_REF_COMMENT_RE.search("<!-- table-ref:tables/t0012.json -->")
    assert m is not None
    assert m.group("ref") == "tables/t0012.json"


def test_tables_manifest_model() -> None:
    manifest = TablesManifest(
        tables=[
            TableManifestEntry(
                table_ref="tables/t0000.json",
                source_block_index=0,
                layout_type="simple",
                row_count=2,
                col_count=3,
                char_start=0,
                char_end=100,
                markdown_preview="| a | b |",
            )
        ]
    )
    assert manifest.schema_version == "1.0"
    assert manifest.tables[0].table_ref == "tables/t0000.json"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_table_placeholders.py -v`  
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/doc_chunk/table/placeholders.py
from __future__ import annotations

import re

TABLE_REF_COMMENT_RE = re.compile(
    r"<!--\s*table-ref:(?P<ref>tables/t\d{4}\.json)\s*-->"
)
TABLE_REF_TOKEN_RE = re.compile(
    r"⟦table:(?P<ref>tables/t\d{4}\.json)⟧"
)


def format_table_ref_comment(table_ref: str) -> str:
    return f"<!-- table-ref:{table_ref} -->"


def parse_table_ref_from_line(line: str) -> str | None:
    stripped = line.strip()
    for pattern in (TABLE_REF_COMMENT_RE, TABLE_REF_TOKEN_RE):
        match = pattern.search(stripped)
        if match:
            return match.group("ref")
    return None
```

```python
# src/doc_chunk/models/tables_manifest.py
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class TableManifestEntry(BaseModel):
    table_ref: str
    source_block_index: int
    layout_type: str
    row_count: int
    col_count: int
    char_start: int
    char_end: int
    markdown_preview: str | None = None


class TablesManifest(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    tables: list[TableManifestEntry] = Field(default_factory=list)
```

```python
# src/doc_chunk/workspace/layout.py — add property
@property
def tables_manifest_path(self) -> Path:
    return self.tables_dir / "manifest.json"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_table_placeholders.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/doc_chunk/table/placeholders.py src/doc_chunk/models/tables_manifest.py \
  src/doc_chunk/workspace/layout.py tests/unit/test_table_placeholders.py
git commit -m "feat(table): add placeholder helpers and TablesManifest model"
```

---

### Task 2: BlockAccumulator 写入占位符

**Files:**
- Modify: `src/doc_chunk/extract/block_index.py`
- Modify: `tests/unit/test_block_index.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_block_index.py — append
from doc_chunk.table.placeholders import format_table_ref_comment


def test_block_accumulator_table_writes_placeholder_in_markdown() -> None:
    acc = BlockAccumulator()
    acc.add_table("| a | b |", table_ref="tables/t0000.json")
    md = acc.markdown
    assert format_table_ref_comment("tables/t0000.json") in md
    assert "| a | b |" in md
    block = acc.finalize().blocks[0]
    assert block.char_start == 0
    assert md[block.char_start : block.char_end].startswith("<!-- table-ref:")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_block_index.py::test_block_accumulator_table_writes_placeholder_in_markdown -v`  
Expected: FAIL (placeholder not in markdown)

- [ ] **Step 3: Write minimal implementation**

```python
# src/doc_chunk/extract/block_index.py
from doc_chunk.table.placeholders import format_table_ref_comment

def add_table(self, table_md: str, *, table_ref: str | None = None) -> None:
    start = self._cursor
    body = f"{table_md}\n\n"
    if table_ref:
        body = f"{format_table_ref_comment(table_ref)}\n{body}"
    self._markdown_parts.append(body)
    self._cursor += len(body)
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

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/unit/test_block_index.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/doc_chunk/extract/block_index.py tests/unit/test_block_index.py
git commit -m "feat(extract): write table-ref placeholder in content markdown"
```

---

### Task 3: collect_table_assets()

**Files:**
- Create: `src/doc_chunk/table/assets.py`
- Create: `tests/unit/test_table_assets.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_table_assets.py
from __future__ import annotations

from pathlib import Path

from doc_chunk.extract.block_index import BlockAccumulator, write_accumulator_markdown, write_content_blocks
from doc_chunk.models.content_block import ContentBlocksFile
from doc_chunk.models.table_model import TableSidecar
from doc_chunk.models.tables_manifest import TablesManifest
from doc_chunk.table.assets import collect_table_assets
from doc_chunk.workspace.layout import OutputWorkspace


def _write_minimal_sidecar(ws: OutputWorkspace, block_index: int = 0) -> str:
    ref = f"tables/t{block_index:04d}.json"
    sidecar = TableSidecar(
        block_index=block_index,
        layout_type="simple",
        grid_width=2,
        grid={"rows": [{"cells": [{"text": "a", "colspan": 1, "rowspan": 1}]}]},
        logical_rows=[["a", "b"]],
        markdown="| a | b |",
        llm_text="table",
    )
    path = ws.root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(sidecar.model_dump_json(indent=2), encoding="utf-8")
    return ref


def test_collect_table_assets_builds_manifest(tmp_path: Path) -> None:
    ws = OutputWorkspace.create(tmp_path / "ws", overwrite=True)
    ref = _write_minimal_sidecar(ws)
    acc = BlockAccumulator()
    acc.add_table("| a | b |", table_ref=ref)
    write_accumulator_markdown(ws, acc)
    write_content_blocks(ws, acc.finalize())

    manifest = collect_table_assets(ws, write_manifest=True)
    assert len(manifest.tables) == 1
    assert manifest.tables[0].table_ref == ref
    assert manifest.tables[0].layout_type == "simple"
    assert ws.tables_manifest_path.exists()
    loaded = TablesManifest.model_validate_json(ws.tables_manifest_path.read_text(encoding="utf-8"))
    assert loaded.tables[0].source_block_index == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_table_assets.py -v`  
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/doc_chunk/table/assets.py
from __future__ import annotations

from pathlib import Path

from doc_chunk.models.content_block import ContentBlocksFile
from doc_chunk.models.tables_manifest import TableManifestEntry, TablesManifest
from doc_chunk.table.access import load_table_model
from doc_chunk.workspace.layout import OutputWorkspace


def collect_table_assets(
    workspace: OutputWorkspace | Path,
    *,
    write_manifest: bool = True,
) -> TablesManifest:
    ws = workspace if isinstance(workspace, OutputWorkspace) else OutputWorkspace.open_existing(Path(workspace))
    blocks_path = ws.content_blocks_path
    if not blocks_path.is_file():
        return TablesManifest()

    blocks_file = ContentBlocksFile.model_validate_json(blocks_path.read_text(encoding="utf-8"))
    entries: list[TableManifestEntry] = []

    for block in blocks_file.blocks:
        if block.block_type != "table" or not block.table_ref:
            continue
        sidecar = load_table_model(ws, block.table_ref)
        row_count = len(sidecar.logical_rows) or len(sidecar.grid.get("rows", []))
        col_count = sidecar.grid_width
        entries.append(
            TableManifestEntry(
                table_ref=block.table_ref,
                source_block_index=block.block_index,
                layout_type=sidecar.layout_type,
                row_count=row_count,
                col_count=col_count,
                char_start=block.char_start,
                char_end=block.char_end,
                markdown_preview=block.text_preview,
            )
        )

    manifest = TablesManifest(tables=sorted(entries, key=lambda e: e.source_block_index))
    if write_manifest:
        ws.tables_dir.mkdir(parents=True, exist_ok=True)
        ws.tables_manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return manifest
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_table_assets.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/doc_chunk/table/assets.py tests/unit/test_table_assets.py
git commit -m "feat(table): add collect_table_assets manifest builder"
```

---

### Task 4: extract 集成 collect_table_assets

**Files:**
- Modify: `src/doc_chunk/extract/docx_extractor.py`
- Modify: `src/doc_chunk/api.py`
- Modify: `tests/contract/test_table_sidecar.py`

- [ ] **Step 1: Write the failing contract test**

```python
# tests/contract/test_table_sidecar.py — append
from doc_chunk.models.tables_manifest import TablesManifest
from doc_chunk.table.placeholders import TABLE_REF_COMMENT_RE


def test_extract_writes_table_placeholder_and_manifest(
    personnel_dual_row_docx: Path, tmp_path: Path
) -> None:
    out = tmp_path / "ws"
    extract_file(personnel_dual_row_docx, out, overwrite=True)
    md = (out / "content.md").read_text(encoding="utf-8")
    assert TABLE_REF_COMMENT_RE.search(md) is not None
    manifest_path = out / "tables" / "manifest.json"
    assert manifest_path.exists()
    manifest = TablesManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    assert len(manifest.tables) >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/contract/test_table_sidecar.py::test_extract_writes_table_placeholder_and_manifest -v`  
Expected: FAIL (no manifest or no placeholder)

- [ ] **Step 3: Wire extract**

```python
# src/doc_chunk/extract/docx_extractor.py — before return, after sidecar_writer.finalize()
from doc_chunk.table.assets import collect_table_assets

sidecar_writer.finalize()
if image_entries:
    ...
collect_table_assets(workspace, write_manifest=True)
```

```python
# src/doc_chunk/api.py — _build_manifest outputs
"tables_manifest": "tables/manifest.json",
```

- [ ] **Step 4: Run contract tests**

Run: `.venv/bin/pytest tests/contract/test_table_sidecar.py -v`  
Expected: PASS (update existing test if char slice now includes placeholder prefix)

- [ ] **Step 5: Commit**

```bash
git add src/doc_chunk/extract/docx_extractor.py src/doc_chunk/api.py tests/contract/test_table_sidecar.py
git commit -m "feat(extract): emit tables/manifest.json and table-ref placeholders"
```

---

### Task 5: ChunkBlock.table_ref 与 build_chunk_blocks 解析

**Files:**
- Modify: `src/doc_chunk/models/chunk.py`
- Modify: `src/doc_chunk/chunk/blocks_builder.py`
- Modify: `tests/unit/test_blocks_builder.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_blocks_builder.py — append
def test_build_chunk_blocks_parses_table_ref_placeholder() -> None:
    markdown = (
        "<!-- table-ref:tables/t0001.json -->\n"
        "| a | b |\n"
        "| --- | --- |\n"
        "| 1 | 2 |\n"
    )
    blocks = build_chunk_blocks(markdown=markdown)
    assert len(blocks) == 1
    assert blocks[0].type == "table"
    assert blocks[0].table_ref == "tables/t0001.json"
    assert blocks[0].text is not None
    assert blocks[0].text.startswith("| a | b |")


def test_build_chunk_blocks_table_without_placeholder_has_no_ref() -> None:
    blocks = build_chunk_blocks(markdown="| a | b |\n| --- | --- |\n| 1 | 2 |")
    assert blocks[0].type == "table"
    assert blocks[0].table_ref is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_blocks_builder.py::test_build_chunk_blocks_parses_table_ref_placeholder -v`  
Expected: FAIL (`table_ref` missing or attribute error)

- [ ] **Step 3: Implement**

```python
# src/doc_chunk/models/chunk.py
class ChunkBlock(BaseModel):
    type: Literal["paragraph", "table", "image"]
    text: str | None = None
    image_ref: str | None = None
    table_ref: str | None = None
```

```python
# src/doc_chunk/chunk/blocks_builder.py
from doc_chunk.table.placeholders import parse_table_ref_from_line

def build_chunk_blocks(...) -> list[ChunkBlock]:
    ...
    pending_table_ref: str | None = None

    for line in markdown.splitlines():
        table_ref_on_line = parse_table_ref_from_line(line)
        if table_ref_on_line:
            flush_paragraph()
            flush_table()
            pending_table_ref = table_ref_on_line
            continue
        # existing image/table/paragraph logic ...
    def flush_table() -> None:
        ...
        blocks.append(ChunkBlock(type="table", text=text, table_ref=pending_table_ref))
        pending_table_ref = None  # reset after flush
```

注意：`flush_table` 内 reset `pending_table_ref`；`flush_paragraph` 不 reset pending（占位符与表格紧邻）。

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/unit/test_blocks_builder.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/doc_chunk/models/chunk.py src/doc_chunk/chunk/blocks_builder.py tests/unit/test_blocks_builder.py
git commit -m "feat(chunk): parse table-ref placeholder into ChunkBlock.table_ref"
```

---

### Task 6: blocks_v1 table asset_id 映射

**Files:**
- Modify: `src/doc_chunk/convert/blocks_v1.py`
- Modify: `tests/unit/test_blocks_v1_convert.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_blocks_v1_convert.py — append
def test_blocks_to_v1_json_table_with_asset_mapping() -> None:
    payload = blocks_to_v1_json(
        [ChunkBlock(type="table", text="| a |", table_ref="tables/t0000.json")],
        table_ref_to_asset_id={"tables/t0000.json": "uuid-table-1"},
    )
    block = json.loads(payload)["blocks"][0]
    assert block == {
        "type": "table",
        "asset_id": "uuid-table-1",
        "table_ref": "tables/t0000.json",
        "text": "| a |",
    }


def test_blocks_to_v1_json_table_without_mapping() -> None:
    payload = blocks_to_v1_json(
        [ChunkBlock(type="table", text="| a |", table_ref="tables/t0000.json")],
    )
    block = json.loads(payload)["blocks"][0]
    assert block["table_ref"] == "tables/t0000.json"
    assert "asset_id" not in block
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_blocks_v1_convert.py::test_blocks_to_v1_json_table_with_asset_mapping -v`  
Expected: FAIL

- [ ] **Step 3: Implement**

```python
# src/doc_chunk/convert/blocks_v1.py
def _block_to_v1_dict(
    block: ChunkBlock,
    image_ref_to_asset_id: dict[str, str] | None,
    table_ref_to_asset_id: dict[str, str] | None,
) -> dict:
    data = block.model_dump(mode="json", exclude_none=True)
    if block.type == "image" and block.image_ref and image_ref_to_asset_id:
        asset_id = image_ref_to_asset_id.get(block.image_ref)
        if asset_id:
            data["asset_id"] = asset_id
    if block.type == "table" and block.table_ref and table_ref_to_asset_id:
        asset_id = table_ref_to_asset_id.get(block.table_ref)
        if asset_id:
            data["asset_id"] = asset_id
    return data


def blocks_to_v1_json(
    blocks: list[ChunkBlock],
    *,
    image_ref_to_asset_id: dict[str, str] | None = None,
    table_ref_to_asset_id: dict[str, str] | None = None,
) -> str:
    payload = {
        "format": "blocks_v1",
        "blocks": [
            _block_to_v1_dict(block, image_ref_to_asset_id, table_ref_to_asset_id)
            for block in blocks
        ],
    }
    return json.dumps(payload, ensure_ascii=False)
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/unit/test_blocks_v1_convert.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/doc_chunk/convert/blocks_v1.py tests/unit/test_blocks_v1_convert.py
git commit -m "feat(convert): blocks_v1 table_ref to asset_id mapping"
```

---

### Task 7: patch_docx_tables()

**Files:**
- Create: `src/doc_chunk/table/patch.py`
- Create: `tests/unit/test_table_patch.py`
- Modify: `src/doc_chunk/table/__init__.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_table_patch.py
from __future__ import annotations

from pathlib import Path

from docx import Document

from doc_chunk.extract.block_index import BlockAccumulator, write_accumulator_markdown, write_content_blocks
from doc_chunk.models.table_model import TableSidecar
from doc_chunk.table.patch import patch_docx_tables
from doc_chunk.workspace.layout import OutputWorkspace


def _setup_workspace_with_sidecar(tmp_path: Path) -> OutputWorkspace:
    ws = OutputWorkspace.create(tmp_path / "ws", overwrite=True)
    ref = "tables/t0000.json"
    sidecar = TableSidecar(
        block_index=0,
        layout_type="simple",
        grid_width=2,
        grid={
            "rows": [
                {"cells": [
                    {"text": "H1", "colspan": 1, "rowspan": 1},
                    {"text": "H2", "colspan": 1, "rowspan": 1},
                ]},
                {"cells": [
                    {"text": "V1", "colspan": 1, "rowspan": 1},
                    {"text": "V2", "colspan": 1, "rowspan": 1},
                ]},
            ]
        },
        logical_rows=[["H1", "H2"], ["V1", "V2"]],
        markdown="| H1 | H2 |\n| --- | --- |\n| V1 | V2 |",
        llm_text="table",
    )
    (ws.root / ref).write_text(sidecar.model_dump_json(indent=2), encoding="utf-8")
    acc = BlockAccumulator()
    acc.add_table(sidecar.markdown, table_ref=ref)
    write_accumulator_markdown(ws, acc)
    write_content_blocks(ws, acc.finalize())
    return ws


def test_patch_docx_tables_replaces_placeholder_with_word_table(tmp_path: Path) -> None:
    ws = _setup_workspace_with_sidecar(tmp_path)
    md = ws.content_path.read_text(encoding="utf-8")

    doc = Document()
    for line in md.splitlines():
        doc.add_paragraph(line)
    assert len(doc.tables) == 0

    result = patch_docx_tables(doc, ws)
    assert result.patched_count == 1
    assert len(doc.tables) == 1
    assert doc.tables[0].cell(0, 0).text == "H1"
    assert "<!-- table-ref:" not in "\n".join(p.text for p in doc.paragraphs)
    assert not any(p.text.strip().startswith("|") for p in doc.paragraphs)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_table_patch.py -v`  
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement patch module**

```python
# src/doc_chunk/table/patch.py
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from docx.document import Document
from docx.text.paragraph import Paragraph

from doc_chunk.convert.table_to_docx import render_sidecar_to_docx
from doc_chunk.table.access import load_table_model
from doc_chunk.table.placeholders import parse_table_ref_from_line
from doc_chunk.workspace.layout import OutputWorkspace


@dataclass
class PatchResult:
    patched_count: int = 0
    skipped: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _is_markdown_table_line(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith("|") and stripped.endswith("|")


def _collect_markdown_table_paragraphs(paragraphs: list[Paragraph], start_index: int) -> list[int]:
    indices: list[int] = []
    for idx in range(start_index + 1, len(paragraphs)):
        if _is_markdown_table_line(paragraphs[idx].text):
            indices.append(idx)
            continue
        if not paragraphs[idx].text.strip():
            indices.append(idx)
            continue
        break
    return indices


def _insert_table_before_paragraph(document: Document, paragraph: Paragraph, sidecar) -> None:
    table = render_sidecar_to_docx(document, sidecar)
    paragraph._p.addprevious(table._tbl)


def patch_docx_tables(
    document: Document,
    workspace: OutputWorkspace | Path,
    *,
    table_refs: list[str] | None = None,
) -> PatchResult:
    ws = workspace if isinstance(workspace, OutputWorkspace) else OutputWorkspace.open_existing(Path(workspace))
    allowed = set(table_refs) if table_refs else None
    paragraphs = list(document.paragraphs)
    result = PatchResult()
    targets: list[tuple[int, str, list[int]]] = []

    for idx, paragraph in enumerate(paragraphs):
        ref = parse_table_ref_from_line(paragraph.text)
        if ref is None:
            continue
        if allowed is not None and ref not in allowed:
            continue
        md_indices = _collect_markdown_table_paragraphs(paragraphs, idx)
        targets.append((idx, ref, md_indices))

    for placeholder_idx, ref, md_indices in reversed(targets):
        sidecar_path = ws.root / ref
        if not sidecar_path.is_file():
            result.skipped.append(ref)
            result.warnings.append(f"table_sidecar_missing:{ref}")
            continue
        sidecar = load_table_model(ws, ref)
        placeholder = document.paragraphs[placeholder_idx]
        _insert_table_before_paragraph(document, placeholder, sidecar)
        delete_indices = sorted([placeholder_idx] + md_indices, reverse=True)
        for del_idx in delete_indices:
            p = document.paragraphs[del_idx]
            p._element.getparent().remove(p._element)
        result.patched_count += 1

    return result
```

```python
# src/doc_chunk/table/__init__.py
from doc_chunk.table.access import load_table_model, substitute_tables_for_llm
from doc_chunk.table.assets import collect_table_assets
from doc_chunk.table.patch import PatchResult, patch_docx_tables

__all__ = [
    "PatchResult",
    "collect_table_assets",
    "load_table_model",
    "patch_docx_tables",
    "substitute_tables_for_llm",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_table_patch.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/doc_chunk/table/patch.py src/doc_chunk/table/__init__.py tests/unit/test_table_patch.py
git commit -m "feat(table): add patch_docx_tables post-hoc table insertion"
```

---

### Task 8: 契约文档与 contract test 更新

**Files:**
- Modify: `specs/001-document-extract-chunk/contracts/workspace-schemas.md`
- Modify: `tests/contract/test_table_sidecar.py`

- [ ] **Step 1: Update contract test for char slice including placeholder**

```python
# tests/contract/test_table_sidecar.py — adjust existing test
# char slice should include <!-- table-ref:... --> line AND markdown
snippet = md[table_blocks[0].char_start : table_blocks[0].char_end].strip()
assert snippet.startswith("<!-- table-ref:")
assert sidecar.markdown.strip() in snippet
```

- [ ] **Step 2: Document tables/manifest.json in workspace-schemas.md**

在 `tables/index.json` 节后新增 `tables/manifest.json` 节，字段与 spec 一致；在 `blocks_v1` 节补充 table 块 `asset_id` + `table_ref` 示例。

- [ ] **Step 3: Run full test suite for table-related tests**

Run: `.venv/bin/pytest tests/unit/test_table_placeholders.py tests/unit/test_table_assets.py tests/unit/test_table_patch.py tests/unit/test_block_index.py tests/unit/test_blocks_builder.py tests/unit/test_blocks_v1_convert.py tests/contract/test_table_sidecar.py -v`  
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add specs/001-document-extract-chunk/contracts/workspace-schemas.md tests/contract/test_table_sidecar.py
git commit -m "docs: document tables manifest and table-ref placeholder contract"
```

---

## P1 Follow-ups (out of P0 scope)

| Item | Notes |
|------|-------|
| `inject_table_placeholders()` | LLM 生成 markdown 补注入 |
| `ContentChunk.table_refs[]` | planner/anchor_planner 汇总 |
| token fallback `⟦table:...⟧` | md→docx 丢 comment 时启用 |
| tk 适配层集成测试 | mock `table_ref_to_asset_id` 落库 |

---

## Spec Coverage Checklist

| Spec 要求 | Task |
|-----------|------|
| 占位符写入 content.md | Task 2, 4 |
| tables/manifest.json | Task 1, 3, 4 |
| collect_table_assets | Task 3 |
| ChunkBlock.table_ref | Task 5 |
| blocks_v1 asset_id | Task 6 |
| patch_docx_tables | Task 7 |
| 契约文档 | Task 8 |
| inject_table_placeholders (P1) | Follow-ups |
| ContentChunk.table_refs (P1) | Follow-ups |
