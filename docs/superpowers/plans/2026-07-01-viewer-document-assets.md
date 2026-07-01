# Viewer 文档资产列表面板 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在切片预览页左侧 outline 下方展示全文档图片/表格资产列表，支持详情查看、表格 docx 下载，以及点击跳转章节并在正文高亮。

**Architecture:** doc_chunk 新增 `media` 层统一汇总 `images/manifest.json` + `tables/manifest.json` 与 `content.blocks.json` 字符区间；viewer 负责 `char → outline_node_id` 反查、REST API 与静态 UI（列表、modal、高亮）。

**Tech Stack:** Python 3.11+, pydantic v2, FastAPI, python-docx, pytest, 原生 JavaScript

**需求来源:** [`docs/superpowers/specs/2026-07-01-viewer-document-assets-design.md`](../specs/2026-07-01-viewer-document-assets-design.md)

**前置依赖:** [`doc-chunk-table-assets`](../plans/2026-07-01-doc-chunk-table-assets.md) P0 已落地（`tables/manifest.json`、`table_to_docx`）

---

## File Structure

```text
src/doc_chunk/media/
├── __init__.py
├── models.py                 # DocumentAssetEntry, DocumentAssetsFile
└── assets.py                 # collect_document_assets

src/doc_chunk/convert/
└── table_export.py           # export_table_ref_to_docx_bytes

tests/unit/
├── test_document_assets.py   # NEW

viewer/viewer/
├── models.py                 # MODIFY: DocumentAssetItemResponse, DocumentAssetsResponse
├── routes/content.py         # MODIFY: document-assets + table export
├── services/
│   └── asset_navigation.py   # NEW: resolve_outline_node_for_char
└── static/
    ├── index.html            # MODIFY: assets-panel + modal
    ├── style.css             # MODIFY: panel/modal/highlight styles
    └── app.js                # MODIFY: load/render/focus/modal

viewer/tests/
├── unit/
│   ├── test_asset_navigation.py      # NEW
│   └── test_index_static_assets.py   # NEW
└── api/
    └── test_document_assets_api.py   # NEW

viewer/README.md              # MODIFY: document new endpoints
```

---

### Task 1: doc_chunk DocumentAsset 模型与 collect_document_assets

**Files:**
- Create: `src/doc_chunk/media/__init__.py`
- Create: `src/doc_chunk/media/models.py`
- Create: `src/doc_chunk/media/assets.py`
- Create: `tests/unit/test_document_assets.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_document_assets.py
from __future__ import annotations

from pathlib import Path

from doc_chunk.extract.block_index import BlockAccumulator, write_accumulator_markdown, write_content_blocks
from doc_chunk.media.assets import collect_document_assets
from doc_chunk.models.images_manifest import ImageManifestEntry, ImagesManifest
from doc_chunk.models.table_model import TableSidecar
from doc_chunk.models.tables_manifest import TableManifestEntry, TablesManifest
from doc_chunk.workspace.layout import OutputWorkspace


def _write_table_sidecar(ws: OutputWorkspace, ref: str = "tables/t0000.json") -> None:
    sidecar = TableSidecar(
        block_index=0,
        layout_type="simple",
        grid_width=2,
        grid={"rows": [{"cells": [{"text": "a", "colspan": 1, "rowspan": 1}]}]},
        logical_rows=[["a", "b"]],
        markdown="| a | b |",
        llm_text="table",
    )
    (ws.root / ref).parent.mkdir(parents=True, exist_ok=True)
    (ws.root / ref).write_text(sidecar.model_dump_json(indent=2), encoding="utf-8")


def test_collect_document_assets_merges_images_and_tables(tmp_path: Path) -> None:
    ws = OutputWorkspace.create(tmp_path / "ws", overwrite=True)
    _write_table_sidecar(ws)
    acc = BlockAccumulator()
    acc.add_table("| a | b |", table_ref="tables/t0000.json")
    acc.add_image("images/img.png", alt="img")
    write_accumulator_markdown(ws, acc)
    write_content_blocks(ws, acc.finalize())

    (ws.images_dir / "img.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    images_manifest = ImagesManifest(
        images=[
            ImageManifestEntry(
                image_ref="images/img.png",
                file_name="img.png",
                content_type="image/png",
                source_block_index=1,
            )
        ]
    )
    ws.images_manifest_path.write_text(images_manifest.model_dump_json(indent=2), encoding="utf-8")
    tables_manifest = TablesManifest(
        tables=[
            TableManifestEntry(
                table_ref="tables/t0000.json",
                source_block_index=0,
                layout_type="simple",
                row_count=1,
                col_count=2,
                char_start=0,
                char_end=50,
                markdown_preview="| a | b |",
            )
        ]
    )
    ws.tables_manifest_path.write_text(tables_manifest.model_dump_json(indent=2), encoding="utf-8")

    doc = collect_document_assets(ws)
    assert len(doc.tables) == 1
    assert doc.tables[0].ref == "tables/t0000.json"
    assert doc.tables[0].char_start is not None
    assert len(doc.images) == 1
    assert doc.images[0].ref == "images/img.png"
    assert doc.images[0].preview == "img.png"
    assert doc.images[0].meta.get("content_type") == "image/png"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_document_assets.py -v`  
Expected: FAIL `ModuleNotFoundError: doc_chunk.media`

- [ ] **Step 3: Implement**

```python
# src/doc_chunk/media/models.py
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class DocumentAssetEntry(BaseModel):
    asset_type: Literal["image", "table"]
    ref: str
    source_block_index: int | None = None
    char_start: int | None = None
    char_end: int | None = None
    preview: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class DocumentAssetsFile(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    images: list[DocumentAssetEntry] = Field(default_factory=list)
    tables: list[DocumentAssetEntry] = Field(default_factory=list)
```

```python
# src/doc_chunk/media/assets.py
from __future__ import annotations

from pathlib import Path

from doc_chunk.media.models import DocumentAssetEntry, DocumentAssetsFile
from doc_chunk.models.content_block import ContentBlocksFile
from doc_chunk.models.images_manifest import ImagesManifest
from doc_chunk.models.tables_manifest import TablesManifest
from doc_chunk.workspace.layout import OutputWorkspace


def _char_range_for_ref(
    blocks: ContentBlocksFile,
    *,
    image_ref: str | None = None,
    table_ref: str | None = None,
) -> tuple[int | None, int | None, int | None]:
    for block in blocks.blocks:
        if image_ref and block.image_ref == image_ref:
            return block.block_index, block.char_start, block.char_end
        if table_ref and block.table_ref == table_ref:
            return block.block_index, block.char_start, block.char_end
    return None, None, None


def _sort_key(entry: DocumentAssetEntry) -> tuple[int, str]:
    if entry.char_start is None:
        return (10**9, entry.ref)
    return (entry.char_start, entry.ref)


def collect_document_assets(workspace: OutputWorkspace | Path) -> DocumentAssetsFile:
    ws = workspace if isinstance(workspace, OutputWorkspace) else OutputWorkspace.open_existing(Path(workspace))
    blocks_file: ContentBlocksFile | None = None
    if ws.content_blocks_path.is_file():
        blocks_file = ContentBlocksFile.model_validate_json(
            ws.content_blocks_path.read_text(encoding="utf-8")
        )

    images: list[DocumentAssetEntry] = []
    if ws.images_manifest_path.is_file():
        manifest = ImagesManifest.model_validate_json(ws.images_manifest_path.read_text(encoding="utf-8"))
        for item in manifest.images:
            block_index, char_start, char_end = (None, None, None)
            if blocks_file is not None:
                block_index, char_start, char_end = _char_range_for_ref(
                    blocks_file, image_ref=item.image_ref
                )
            images.append(
                DocumentAssetEntry(
                    asset_type="image",
                    ref=item.image_ref,
                    source_block_index=block_index if block_index is not None else item.source_block_index,
                    char_start=char_start,
                    char_end=char_end,
                    preview=item.file_name,
                    meta={
                        "content_type": item.content_type,
                        "byte_size": item.byte_size,
                        "width": item.width,
                        "height": item.height,
                    },
                )
            )

    tables: list[DocumentAssetEntry] = []
    if ws.tables_manifest_path.is_file():
        manifest = TablesManifest.model_validate_json(ws.tables_manifest_path.read_text(encoding="utf-8"))
        for item in manifest.tables:
            block_index, char_start, char_end = (None, None, None)
            if blocks_file is not None:
                block_index, char_start, char_end = _char_range_for_ref(
                    blocks_file, table_ref=item.table_ref
                )
            tables.append(
                DocumentAssetEntry(
                    asset_type="table",
                    ref=item.table_ref,
                    source_block_index=block_index if block_index is not None else item.source_block_index,
                    char_start=char_start if char_start is not None else item.char_start,
                    char_end=char_end if char_end is not None else item.char_end,
                    preview=item.markdown_preview,
                    meta={
                        "layout_type": item.layout_type,
                        "row_count": item.row_count,
                        "col_count": item.col_count,
                    },
                )
            )

    return DocumentAssetsFile(
        images=sorted(images, key=_sort_key),
        tables=sorted(tables, key=_sort_key),
    )
```

```python
# src/doc_chunk/media/__init__.py
from doc_chunk.media.assets import collect_document_assets
from doc_chunk.media.models import DocumentAssetEntry, DocumentAssetsFile

__all__ = ["DocumentAssetEntry", "DocumentAssetsFile", "collect_document_assets"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_document_assets.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/doc_chunk/media tests/unit/test_document_assets.py
git commit -m "feat(media): add collect_document_assets for images and tables"
```

---

### Task 2: export_table_ref_to_docx_bytes

**Files:**
- Create: `src/doc_chunk/convert/table_export.py`
- Modify: `tests/unit/test_document_assets.py` (append export test)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/unit/test_document_assets.py
from doc_chunk.convert.table_export import export_table_ref_to_docx_bytes


def test_export_table_ref_to_docx_bytes(tmp_path: Path) -> None:
    ws = OutputWorkspace.create(tmp_path / "ws-export", overwrite=True)
    _write_table_sidecar(ws)
    data = export_table_ref_to_docx_bytes(ws, "tables/t0000.json")
    assert data[:2] == b"PK"  # zip/docx magic
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_document_assets.py::test_export_table_ref_to_docx_bytes -v`  
Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# src/doc_chunk/convert/table_export.py
from __future__ import annotations

import io
from pathlib import Path

from docx import Document

from doc_chunk.convert.table_to_docx import render_sidecar_to_docx
from doc_chunk.table.access import load_table_model
from doc_chunk.workspace.layout import OutputWorkspace


def export_table_ref_to_docx_bytes(workspace: OutputWorkspace | Path, table_ref: str) -> bytes:
    ws = workspace if isinstance(workspace, OutputWorkspace) else OutputWorkspace.open_existing(Path(workspace))
    sidecar_path = ws.root / table_ref
    if not sidecar_path.is_file():
        raise FileNotFoundError(f"table sidecar not found: {table_ref}")
    sidecar = load_table_model(ws, table_ref)
    document = Document()
    render_sidecar_to_docx(document, sidecar)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()
```

- [ ] **Step 4: Run test**

Run: `.venv/bin/pytest tests/unit/test_document_assets.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/doc_chunk/convert/table_export.py tests/unit/test_document_assets.py
git commit -m "feat(convert): add export_table_ref_to_docx_bytes"
```

---

### Task 3: viewer resolve_outline_node_for_char

**Files:**
- Create: `viewer/viewer/services/asset_navigation.py`
- Create: `viewer/tests/unit/test_asset_navigation.py`

- [ ] **Step 1: Write the failing test**

```python
# viewer/tests/unit/test_asset_navigation.py
from doc_chunk.models.outline import Anchor, OutlineNode, OutlineTree

from viewer.services.asset_navigation import resolve_outline_node_for_char
from viewer.services.outline_tree import PREFACE_NODE_ID


def test_resolve_preface_char() -> None:
    content_md = "Preface text\n\n# Chapter 1\n\nBody"
    tree = OutlineTree(
        nodes=[
            OutlineNode(
                node_id="n1",
                title="Chapter 1",
                level=1,
                parent_id=None,
                sort_order=0,
                anchor=Anchor(char_start=content_md.index("Body")),
            )
        ]
    )
    assert resolve_outline_node_for_char(5, content_md, tree) == PREFACE_NODE_ID


def test_resolve_chapter_char() -> None:
    content_md = "Preface\n\n# Chapter 1\n\nAlpha\n\n# Chapter 2\n\nBeta"
    tree = OutlineTree(
        nodes=[
            OutlineNode(
                node_id="n1",
                title="Chapter 1",
                level=1,
                parent_id=None,
                sort_order=0,
                anchor=Anchor(char_start=0),
            ),
            OutlineNode(
                node_id="n2",
                title="Chapter 2",
                level=1,
                parent_id=None,
                sort_order=1,
                anchor=Anchor(char_start=0),
            ),
        ]
    )
    pos = content_md.index("Alpha")
    assert resolve_outline_node_for_char(pos, content_md, tree) == "n1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest viewer/tests/unit/test_asset_navigation.py -v`  
Expected: FAIL

- [ ] **Step 3: Implement**

```python
# viewer/viewer/services/asset_navigation.py
from __future__ import annotations

from doc_chunk.models.outline import OutlineTree

from viewer.services.outline_tree import PREFACE_NODE_ID
from viewer.services.section_slice import slice_section


def resolve_outline_node_for_char(
    char_pos: int,
    content_md: str,
    outline_tree: OutlineTree,
) -> str | None:
    if char_pos < 0:
        return None

    preface = slice_section(content_md, outline_tree, PREFACE_NODE_ID)
    if char_pos < preface.char_end:
        return PREFACE_NODE_ID

    for node in outline_tree.nodes:
        try:
            section = slice_section(content_md, outline_tree, node.node_id)
        except KeyError:
            continue
        if section.char_start <= char_pos < section.char_end:
            return node.node_id
    return None
```

- [ ] **Step 4: Run test**

Run: `.venv/bin/pytest viewer/tests/unit/test_asset_navigation.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add viewer/viewer/services/asset_navigation.py viewer/tests/unit/test_asset_navigation.py
git commit -m "feat(viewer): resolve outline node for document char position"
```

---

### Task 4: Viewer API — document-assets 与 table export

**Files:**
- Modify: `viewer/viewer/models.py`
- Modify: `viewer/viewer/routes/content.py`
- Create: `viewer/tests/api/test_document_assets_api.py`

- [ ] **Step 1: Write the failing API test**

```python
# viewer/tests/api/test_document_assets_api.py
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from viewer.deps import get_session_store
from viewer.main import create_app
from viewer.models import SessionRecord


def _register_session(workspace: Path) -> str:
    now = datetime.now(UTC).isoformat()
    session_id = "assets-session"
    get_session_store().add(
        SessionRecord(
            id=session_id,
            title=workspace.name,
            workspace_path=str(workspace),
            source_type="open",
            status="success",
            created_at=now,
            opened_at=now,
        )
    )
    return session_id


def test_document_assets_endpoint(pipeline_workspace: Path, viewer_data_dir) -> None:
    client = TestClient(create_app())
    session_id = _register_session(pipeline_workspace)
    response = client.get(f"/api/sessions/{session_id}/document-assets")
    assert response.status_code == 200
    data = response.json()
    assert "images" in data
    assert "tables" in data
    assert isinstance(data["images"], list)
    assert isinstance(data["tables"], list)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest viewer/tests/api/test_document_assets_api.py::test_document_assets_endpoint -v`  
Expected: FAIL 404

- [ ] **Step 3: Add models and routes**

```python
# viewer/viewer/models.py — append
class DocumentAssetItemResponse(BaseModel):
    asset_type: Literal["image", "table"]
    ref: str
    source_block_index: int | None = None
    char_start: int | None = None
    char_end: int | None = None
    preview: str | None = None
    outline_node_id: str | None = None
    meta: dict = Field(default_factory=dict)


class DocumentAssetsResponse(BaseModel):
    images: list[DocumentAssetItemResponse] = Field(default_factory=list)
    tables: list[DocumentAssetItemResponse] = Field(default_factory=list)
```

```python
# viewer/viewer/routes/content.py — append imports and routes
from io import BytesIO

from fastapi.responses import StreamingResponse

from doc_chunk.convert.table_export import export_table_ref_to_docx_bytes
from doc_chunk.media.assets import collect_document_assets
from viewer.models import DocumentAssetItemResponse, DocumentAssetsResponse
from viewer.services.asset_navigation import resolve_outline_node_for_char


def _enrich_assets(session_id: str, workspace: Path) -> DocumentAssetsResponse:
    content_md = (workspace / "content.md").read_text(encoding="utf-8")
    outline = OutlineTree.model_validate_json((workspace / "outline.json").read_text(encoding="utf-8"))
    doc_assets = collect_document_assets(workspace)

    def enrich(entry) -> DocumentAssetItemResponse:
        outline_node_id = None
        if entry.char_start is not None:
            outline_node_id = resolve_outline_node_for_char(entry.char_start, content_md, outline)
        return DocumentAssetItemResponse(
            asset_type=entry.asset_type,
            ref=entry.ref,
            source_block_index=entry.source_block_index,
            char_start=entry.char_start,
            char_end=entry.char_end,
            preview=entry.preview,
            outline_node_id=outline_node_id,
            meta=entry.meta,
        )

    return DocumentAssetsResponse(
        images=[enrich(e) for e in doc_assets.images],
        tables=[enrich(e) for e in doc_assets.tables],
    )


@router.get("/sessions/{session_id}/document-assets")
def get_document_assets(session_id: str) -> dict:
    workspace = _load_workspace(session_id)
    return _enrich_assets(session_id, workspace).model_dump()


@router.get("/sessions/{session_id}/tables/{table_ref:path}/export.docx")
def export_table_docx(session_id: str, table_ref: str) -> StreamingResponse:
    workspace = _load_workspace(session_id)
    if not table_ref.startswith("tables/"):
        raise HTTPException(status_code=400, detail="invalid table_ref")
    try:
        data = export_table_ref_to_docx_bytes(workspace, table_ref)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="table sidecar not found") from exc
    filename = Path(table_ref).stem + ".docx"
    return StreamingResponse(
        BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

- [ ] **Step 4: Run API tests**

Run: `.venv/bin/pytest viewer/tests/api/test_document_assets_api.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add viewer/viewer/models.py viewer/viewer/routes/content.py viewer/tests/api/test_document_assets_api.py
git commit -m "feat(viewer): add document-assets and table export API"
```

---

### Task 5: 切片预览 HTML/CSS — 资产面板与图片 modal

**Files:**
- Modify: `viewer/viewer/static/index.html`
- Modify: `viewer/viewer/static/style.css`
- Create: `viewer/tests/unit/test_index_static_assets.py`

- [ ] **Step 1: Write static asset test**

```python
# viewer/tests/unit/test_index_static_assets.py
from pathlib import Path

STATIC = Path(__file__).resolve().parents[2] / "viewer/static"


def test_index_html_has_assets_panel() -> None:
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert "assets-panel" in html
    assert "assets-list" in html
    assert "image-preview-modal" in html


def test_app_js_has_document_assets_hooks() -> None:
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "loadDocumentAssets" in js
    assert "focusAssetInDocument" in js
    assert "openImagePreview" in js
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest viewer/tests/unit/test_index_static_assets.py -v`  
Expected: FAIL

- [ ] **Step 3: Update index.html**

在 `outline-tree` 后、`</aside>` 前插入：

```html
<div class="assets-panel">
  <div class="assets-panel-header">文档资产</div>
  <div id="assets-list" class="assets-list muted">加载中…</div>
</div>

<div id="image-preview-modal" class="asset-modal" hidden>
  <div class="asset-modal-backdrop" id="image-preview-backdrop"></div>
  <div class="asset-modal-body">
    <header class="asset-modal-header">
      <code id="image-preview-ref"></code>
      <button type="button" id="close-image-preview">关闭</button>
    </header>
    <img id="image-preview-img" alt="">
  </div>
</div>
```

- [ ] **Step 4: Append CSS**

```css
/* viewer/viewer/static/style.css */
.assets-panel {
  flex: 0 0 35%;
  max-height: 40%;
  min-height: 160px;
  display: flex;
  flex-direction: column;
  border-top: 1px solid #ddd;
  background: #fafafa;
}
.assets-panel-header {
  flex-shrink: 0;
  padding: 0.4rem 0.75rem;
  font-weight: 600;
  font-size: 0.85rem;
  border-bottom: 1px solid #eee;
}
.assets-list {
  flex: 1;
  overflow: auto;
  padding: 0.35rem 0.5rem;
}
.asset-group summary {
  cursor: pointer;
  font-weight: 600;
  padding: 0.25rem 0;
}
.asset-row {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.3rem 0.25rem;
  border-radius: 4px;
  cursor: pointer;
}
.asset-row:hover { background: #eef6ff; }
.asset-row.active { background: #dbeafe; }
.asset-ref {
  flex: 1;
  font-family: ui-monospace, monospace;
  font-size: 0.75rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.asset-preview {
  font-size: 0.7rem;
  color: #666;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.asset-detail-btn {
  flex-shrink: 0;
  font-size: 0.75rem;
  padding: 0.15rem 0.4rem;
}
.asset-modal[hidden] { display: none; }
.asset-modal {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
}
.asset-modal-backdrop {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
}
.asset-modal-body {
  position: relative;
  background: #fff;
  border-radius: 8px;
  max-width: 90vw;
  max-height: 90vh;
  padding: 0.75rem;
  z-index: 1;
}
.asset-modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.5rem;
}
#image-preview-img {
  max-width: 100%;
  max-height: 75vh;
  display: block;
}
.content-panel .asset-highlight {
  outline: 2px solid #2563eb;
  background: rgba(37, 99, 235, 0.08);
}
```

- [ ] **Step 5: Commit HTML/CSS only (app.js in Task 6)**

```bash
git add viewer/viewer/static/index.html viewer/viewer/static/style.css viewer/tests/unit/test_index_static_assets.py
git commit -m "feat(viewer): add assets panel and image preview modal markup"
```

---

### Task 6: app.js — 加载列表、详情、跳转与高亮

**Files:**
- Modify: `viewer/viewer/static/app.js`

- [ ] **Step 1: Extend state and loadDocumentAssets**

在 `state` 增加：

```javascript
documentAssets: null,
activeAssetRef: null,
```

新增函数（完整实现写入 app.js）：

```javascript
async function loadDocumentAssets() {
  const listEl = document.getElementById("assets-list");
  if (!state.sessionId) {
    listEl.textContent = "—";
    return;
  }
  listEl.textContent = "加载中…";
  try {
    state.documentAssets = await api(`/api/sessions/${state.sessionId}/document-assets`);
    renderAssetsList(state.documentAssets);
  } catch (err) {
    listEl.textContent = err.message || "加载失败";
  }
}
```

在 `loadOutline()` 末尾调用 `await loadDocumentAssets()`；在 `pollJob` done、`session-select` change、`reextract` 成功后同样刷新。

- [ ] **Step 2: renderAssetsList**

```javascript
function renderAssetsList(data) {
  const listEl = document.getElementById("assets-list");
  listEl.innerHTML = "";
  const groups = [
    ["图片", data.images || []],
    ["表格", data.tables || []],
  ];
  let any = false;
  for (const [label, items] of groups) {
    if (!items.length) continue;
    any = true;
    const details = document.createElement("details");
    details.className = "asset-group";
    details.open = true;
    const summary = document.createElement("summary");
    summary.textContent = `${label} (${items.length})`;
    details.appendChild(summary);
    for (const item of items) {
      details.appendChild(buildAssetRow(item));
    }
    listEl.appendChild(details);
  }
  if (!any) {
    listEl.textContent = "暂无图片/表格资产";
  }
}
```

`buildAssetRow(item)` 创建 `.asset-row`，含 `.asset-ref`（`item.ref`）、可选 preview、「查看详情」按钮。

- [ ] **Step 3: 详情与跳转**

```javascript
function openImagePreview(ref) {
  const modal = document.getElementById("image-preview-modal");
  document.getElementById("image-preview-ref").textContent = ref;
  document.getElementById("image-preview-img").src =
    `/api/sessions/${state.sessionId}/assets/${ref}`;
  modal.hidden = false;
}

function downloadTableDocx(ref) {
  const url = `/api/sessions/${state.sessionId}/tables/${encodeURIComponent(ref)}/export.docx`;
  window.location.assign(url);
}

async function focusAssetInDocument(asset) {
  if (!asset.outline_node_id || asset.char_start == null) {
    setProgress("无法定位该资产");
    return;
  }
  state.activeAssetRef = asset.ref;
  document.querySelectorAll(".asset-row").forEach((row) => {
    row.classList.toggle("active", row.dataset.ref === asset.ref);
  });
  if (state.selectedNodeId !== asset.outline_node_id) {
    await selectNode(asset.outline_node_id);
  }
  highlightAssetInContent(asset);
}

function highlightAssetInContent(asset) {
  document.querySelectorAll(".asset-highlight").forEach((el) => {
    el.classList.remove("asset-highlight");
  });
  const panel = document.getElementById("content-panel");
  let target = null;
  if (asset.asset_type === "image") {
    target = panel.querySelector(`img[src*="${asset.ref}"]`);
  } else {
    target = panel.querySelector("table");
  }
  if (target) {
    target.classList.add("asset-highlight");
    target.scrollIntoView({ block: "center", behavior: "smooth" });
  }
}
```

- [ ] **Step 4: Wire events**

- 「查看详情」：`stopPropagation`；image → `openImagePreview`；table → `downloadTableDocx`
- 行点击 → `focusAssetInDocument`
- `selectNode` 开头清除 `activeAssetRef` 与高亮
- modal 关闭按钮 + backdrop 点击关闭

- [ ] **Step 5: Run static tests**

Run: `.venv/bin/pytest viewer/tests/unit/test_index_static_assets.py -v`  
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add viewer/viewer/static/app.js
git commit -m "feat(viewer): document assets list with preview, download, and highlight"
```

---

### Task 7: API 表格导出测试 + README

**Files:**
- Modify: `viewer/tests/api/test_document_assets_api.py`
- Modify: `viewer/README.md`

- [ ] **Step 1: Add table export test**

```python
def test_table_export_docx(pipeline_workspace: Path, viewer_data_dir) -> None:
    client = TestClient(create_app())
    session_id = _register_session(pipeline_workspace)
    assets = client.get(f"/api/sessions/{session_id}/document-assets").json()
    if not assets["tables"]:
        return  # sample docx may have no tables
    ref = assets["tables"][0]["ref"]
    response = client.get(
        f"/api/sessions/{session_id}/tables/{ref}/export.docx"
    )
    assert response.status_code == 200
    assert response.content[:2] == b"PK"
```

- [ ] **Step 2: Update viewer README**

在 REST API 表增加：

| `GET` | `/api/sessions/{id}/document-assets` | 全文档图片/表格资产列表 |
| `GET` | `/api/sessions/{id}/tables/{table_ref}/export.docx` | 下载表格 Word |

切片预览节补充：左栏下方资产面板、点击查看详情、点击行跳转高亮。

- [ ] **Step 3: Run full viewer + doc_chunk tests**

Run:

```bash
.venv/bin/pytest tests/unit/test_document_assets.py viewer/tests/unit/test_asset_navigation.py viewer/tests/unit/test_index_static_assets.py viewer/tests/api/test_document_assets_api.py viewer/tests/api/test_content_api.py -v
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add viewer/tests/api/test_document_assets_api.py viewer/README.md
git commit -m "docs(viewer): document assets API and slice preview panel"
```

---

## P1 Follow-ups (out of P0 scope)

| Item | Notes |
|------|-------|
| URL `?asset=` 深链接 | bootstrapFromUrl 解析并 focusAssetInDocument |
| images manifest char 字段 | extract 写入，减少 blocks 反查 |

---

## Spec Coverage Checklist

| Spec 要求 | Task |
|-----------|------|
| collect_document_assets | Task 1 |
| export_table_ref_to_docx_bytes | Task 2 |
| resolve_outline_node_for_char | Task 3 |
| GET /document-assets | Task 4 |
| GET /tables/.../export.docx | Task 4 |
| 左栏资产面板 | Task 5 |
| 图片 modal | Task 5, 6 |
| 表格下载 | Task 6 |
| 跳转 + 高亮 | Task 6 |
| 测试 + README | Task 7 |
| ?asset= 深链接 (P1) | Follow-ups |
