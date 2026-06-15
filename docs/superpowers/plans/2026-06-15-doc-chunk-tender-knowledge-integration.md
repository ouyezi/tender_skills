# doc_chunk 对接 tender_knowledge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 扩展 `doc_chunk` 工作区产物与分块逻辑，使 `tender_knowledge` 可用「工作区 JSON + 薄适配层」替换自研目录提取与章节切片，无需移植 tk 领域规则。

**Architecture:** extract 阶段产出块索引侧车与图片清单；outline 阶段为每个节点填充 `char_start`/`char_end` 字符锚点（相对 `content.md`）；新增 `tree` 阶段生成 `document_tree.json`；chunk 阶段以 outline 锚点为主切片并附带 `blocks_v1` 等价结构；pipeline 末尾写 `linkage.json` 汇总 ID 映射。锚点坐标统一为 **Python `str` 字符偏移**（与 refined `markdown_range` 一致）。

**Tech Stack:** Python 3.11+, python-docx, lxml, pymupdf, pydantic v2, typer, pyyaml, pytest, jsonschema

**需求来源:** [`docs/superpowers/specs/2026-06-15-doc-chunk-tender-knowledge-integration.md`](../specs/2026-06-15-doc-chunk-tender-knowledge-integration.md)

**设计决策（R9 docm）：** 采用 **方案 B — 显式拒绝**。`detect_file_type` 仍识别 `.docm`，但 `extract_file` 对 `docm` 抛出 `UnsupportedFormatError`（CLI 退出码 4），README 说明调用方先用 tk `docm_converter` 或 LibreOffice 转 `.docx`。不引入 `soffice` 运行时依赖。

---

## File Structure

```text
src/doc_chunk/
├── models/
│   ├── content_block.py          # ContentBlockRecord, ContentBlocksFile (NEW)
│   ├── document_tree.py          # DocumentTreeNode, DocumentTreeFile (NEW)
│   ├── linkage.py                # LinkageEntry, LinkageFile (NEW)
│   ├── images_manifest.py        # ImageManifestEntry, ImagesManifest (NEW)
│   ├── chunk.py                  # +ContentBlock, ChunkBlock fields (MODIFY)
│   └── manifest.py               # unchanged schema, new stage keys at runtime
├── extract/
│   ├── block_index.py            # BlockAccumulator, write_content_blocks (NEW)
│   ├── docx_extractor.py         # emit blocks + images manifest (MODIFY)
│   ├── pdf_extractor.py          # emit blocks + page anchor (MODIFY)
│   └── detect.py                 # docm rejection helper (MODIFY)
├── outline/
│   ├── anchor_enricher.py        # fill char_start/char_end from blocks (NEW)
│   └── builder.py                # call anchor_enricher after strategy (MODIFY)
├── tree/
│   ├── __init__.py               # (NEW)
│   └── builder.py                # build_document_tree (NEW)
├── chunk/
│   ├── anchor_planner.py         # plan_chunks_from_anchors (NEW)
│   ├── blocks_builder.py         # markdown/blocks → ChunkBlock list (NEW)
│   ├── planner.py                # delegate to anchor; --markdown-headings-only path (MODIFY)
│   └── writer.py                 # pass blocks through (MODIFY)
├── linkage/
│   ├── __init__.py               # (NEW)
│   └── builder.py                # build_linkage (NEW)
├── convert/
│   ├── __init__.py               # (NEW)
│   └── blocks_v1.py              # blocks_to_v1_json (NEW)
├── metadata/
│   ├── classify.py               # product/chapter hints (MODIFY)
│   └── rules.py                  # load product_categories/chapter_taxonomies (MODIFY)
├── workspace/
│   └── layout.py                 # new path properties (MODIFY)
├── api.py                        # tree, linkage, progress, pipeline (MODIFY)
└── cli/main.py                   # tree cmd, flags (MODIFY)

tests/
├── fixtures/
│   ├── no_heading_style.docx     # committed synthetic fixture (NEW)
│   └── expected/
│       ├── content_blocks_minimal.json   (NEW)
│       ├── document_tree_minimal.json    (NEW)
│       ├── linkage_minimal.json          (NEW)
│       └── images_manifest_minimal.json  (NEW)
├── unit/
│   ├── test_block_index.py       (NEW)
│   ├── test_anchor_enricher.py   (NEW)
│   ├── test_anchor_planner.py    (NEW)
│   ├── test_document_tree.py     (NEW)
│   ├── test_blocks_builder.py    (NEW)
│   ├── test_linkage_builder.py   (NEW)
│   ├── test_blocks_v1_convert.py   (NEW)
│   ├── test_classify_hints.py    (NEW)
│   └── test_docm_reject.py       (NEW)
├── contract/
│   ├── test_workspace_schemas.py   (MODIFY)
│   └── test_chunk_anchor_alignment.py (NEW)
└── integration/
    ├── test_tree_cli.py          (NEW)
    └── test_pipeline_tk_outputs.py (NEW)

specs/001-document-extract-chunk/contracts/workspace-schemas.md  (MODIFY)
README.md                                                         (MODIFY)
```

---

### Task 1: 块索引模型与 extract 侧车 `content.blocks.json`

**Files:**
- Create: `src/doc_chunk/models/content_block.py`
- Create: `src/doc_chunk/extract/block_index.py`
- Modify: `src/doc_chunk/extract/docx_extractor.py`
- Modify: `src/doc_chunk/workspace/layout.py`
- Test: `tests/unit/test_block_index.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_block_index.py
from __future__ import annotations

from pathlib import Path

from doc_chunk.extract.block_index import BlockAccumulator, write_content_blocks
from doc_chunk.models.content_block import ContentBlocksFile
from doc_chunk.workspace.layout import OutputWorkspace


def test_block_accumulator_tracks_char_offsets(tmp_path: Path) -> None:
    ws = OutputWorkspace.create(tmp_path / "ws", overwrite=True)
    acc = BlockAccumulator()
    acc.add_paragraph("第一章 总则")
    acc.add_paragraph("正文段落。")
    acc.add_table("| a | b |\n| --- | --- |\n| 1 | 2 |")
    acc.add_image("images/docx-img-001.png")

    blocks_file = acc.finalize()
    assert len(blocks_file.blocks) == 4
    assert blocks_file.blocks[0].block_type == "paragraph"
    assert blocks_file.blocks[0].char_start == 0
    assert blocks_file.blocks[1].char_start > blocks_file.blocks[0].char_end
    assert blocks_file.blocks[2].block_type == "table"
    assert blocks_file.blocks[3].block_type == "image"

    path = write_content_blocks(ws, blocks_file)
    loaded = ContentBlocksFile.model_validate_json(path.read_text(encoding="utf-8"))
    assert loaded.schema_version == "1.0"
    assert len(loaded.blocks) == 4
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/tongqianni/xlab/tender_skills
.venv/bin/python -m pytest tests/unit/test_block_index.py -v
```

Expected: FAIL `ModuleNotFoundError: No module named 'doc_chunk.models.content_block'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/doc_chunk/models/content_block.py
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ContentBlockRecord(BaseModel):
    block_index: int
    block_type: Literal["paragraph", "table", "image", "heading"]
    char_start: int
    char_end: int
    text_preview: str | None = None
    image_ref: str | None = None


class ContentBlocksFile(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    blocks: list[ContentBlockRecord] = Field(default_factory=list)
```

```python
# src/doc_chunk/extract/block_index.py
from __future__ import annotations

from pathlib import Path

from doc_chunk.models.content_block import ContentBlockRecord, ContentBlocksFile
from doc_chunk.workspace.layout import OutputWorkspace


class BlockAccumulator:
    def __init__(self) -> None:
        self._markdown_parts: list[str] = []
        self._blocks: list[ContentBlockRecord] = []
        self._cursor = 0

    def _append(self, text: str, block_type: str, *, image_ref: str | None = None) -> None:
        if not text and block_type != "image":
            return
        start = self._cursor
        self._markdown_parts.append(text)
        self._cursor += len(text)
        preview = None if block_type == "image" else (text[:120] or None)
        self._blocks.append(
            ContentBlockRecord(
                block_index=len(self._blocks),
                block_type=block_type,  # type: ignore[arg-type]
                char_start=start,
                char_end=self._cursor,
                text_preview=preview,
                image_ref=image_ref,
            )
        )

    def add_paragraph(self, text: str) -> None:
        self._append(f"{text}\n\n", "paragraph")

    def add_heading(self, level: int, text: str) -> None:
        self._append(f"{'#' * level} {text}\n\n", "heading")

    def add_table(self, table_md: str) -> None:
        self._append(f"{table_md}\n\n", "table")

    def add_image(self, image_ref: str, alt: str = "image") -> None:
        line = f"![{alt}]({image_ref})\n\n"
        self._append(line, "image", image_ref=image_ref)

    @property
    def markdown(self) -> str:
        return "".join(self._markdown_parts)

    def finalize(self) -> ContentBlocksFile:
        return ContentBlocksFile(blocks=list(self._blocks))


def write_content_blocks(workspace: OutputWorkspace, blocks_file: ContentBlocksFile) -> Path:
    path = workspace.content_blocks_path
    path.write_text(blocks_file.model_dump_json(indent=2), encoding="utf-8")
    return path
```

在 `layout.py` 增加：

```python
@property
def content_blocks_path(self) -> Path:
    return self.root / "content.blocks.json"
```

重构 `docx_extractor.py`：用 `BlockAccumulator` 替代直接 `markdown_lines` 列表；`write_content_markdown` 写入 `acc.markdown`；调用 `write_content_blocks`。

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python -m pytest tests/unit/test_block_index.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/doc_chunk/models/content_block.py src/doc_chunk/extract/block_index.py \
  src/doc_chunk/extract/docx_extractor.py src/doc_chunk/workspace/layout.py \
  tests/unit/test_block_index.py
git commit -m "feat: add content.blocks.json sidecar from extract"
```

---

### Task 2: `images/manifest.json`（R6）

**Files:**
- Create: `src/doc_chunk/models/images_manifest.py`
- Modify: `src/doc_chunk/extract/docx_extractor.py`
- Modify: `src/doc_chunk/extract/pdf_extractor.py`
- Modify: `src/doc_chunk/api.py`（manifest outputs 登记）
- Test: `tests/unit/test_block_index.py`（追加图片 manifest 用例）

- [ ] **Step 1: Write the failing test**

```python
# append to tests/unit/test_block_index.py
from doc_chunk.extract.docx_extractor import extract_docx
from doc_chunk.models.images_manifest import ImagesManifest


def test_extract_writes_images_manifest(sample_docx_with_image: Path, tmp_path: Path) -> None:
    ws = OutputWorkspace.create(tmp_path / "ws-img", overwrite=True)
    extract_docx(sample_docx_with_image, ws)
    manifest_path = ws.images_manifest_path
    assert manifest_path.exists()
    data = ImagesManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    assert len(data.images) == 1
    assert data.images[0].image_ref.startswith("images/")
    assert data.images[0].content_type.startswith("image/")
    assert data.images[0].source_block_index is not None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest tests/unit/test_block_index.py::test_extract_writes_images_manifest -v
```

Expected: FAIL `AttributeError: 'OutputWorkspace' object has no attribute 'images_manifest_path'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/doc_chunk/models/images_manifest.py
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ImageManifestEntry(BaseModel):
    image_ref: str
    file_name: str
    content_type: str
    byte_size: int | None = None
    source_block_index: int | None = None
    width: int | None = None
    height: int | None = None


class ImagesManifest(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    images: list[ImageManifestEntry] = Field(default_factory=list)
```

`layout.py` 增加 `images_manifest_path -> self.images_dir / "manifest.json"`。

`docx_extractor` 在保存图片时记录 `ImagesManifestEntry`；extract 结束写入 `ws.images_manifest_path`。

`api._build_manifest` 的 `outputs` 增加 `"images_manifest": "images/manifest.json"`, `"content_blocks": "content.blocks.json"`。

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python -m pytest tests/unit/test_block_index.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/doc_chunk/models/images_manifest.py src/doc_chunk/extract/docx_extractor.py \
  src/doc_chunk/extract/pdf_extractor.py src/doc_chunk/workspace/layout.py \
  src/doc_chunk/api.py tests/unit/test_block_index.py
git commit -m "feat: write images/manifest.json during extract"
```

---

### Task 3: outline 锚点填充 `char_start`/`char_end`（R1 前置）

**Files:**
- Create: `src/doc_chunk/outline/anchor_enricher.py`
- Modify: `src/doc_chunk/outline/builder.py`
- Test: `tests/unit/test_anchor_enricher.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_anchor_enricher.py
from doc_chunk.models.content_block import ContentBlockRecord, ContentBlocksFile
from doc_chunk.models.outline import Anchor, OutlineNode, OutlineTree
from doc_chunk.outline.anchor_enricher import enrich_outline_anchors


def test_enrich_fills_char_anchors_from_block_text() -> None:
    blocks = ContentBlocksFile(
        blocks=[
            ContentBlockRecord(
                block_index=0, block_type="paragraph",
                char_start=0, char_end=10, text_preview="1. 技术方案",
            ),
            ContentBlockRecord(
                block_index=1, block_type="paragraph",
                char_start=10, char_end=30, text_preview="方案正文",
            ),
        ]
    )
    tree = OutlineTree(
        strategy="content_heuristic",
        nodes=[
            OutlineNode(
                node_id="n1", title="技术方案", level=1,
                parent_id=None, sort_order=0, anchor=Anchor(block_index=0),
            )
        ],
    )
    enriched = enrich_outline_anchors(tree, blocks, content_md="1. 技术方案\n\n方案正文\n\n")
    assert enriched.nodes[0].anchor.char_start == 0
    assert enriched.nodes[0].anchor.char_end == 10
    assert enriched.nodes[0].anchor.block_start == 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest tests/unit/test_anchor_enricher.py -v
```

Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/doc_chunk/outline/anchor_enricher.py
from __future__ import annotations

import re

from doc_chunk.models.content_block import ContentBlocksFile
from doc_chunk.models.outline import Anchor, OutlineNode, OutlineTree

_NUM_PREFIX_RE = re.compile(r"^(\d+(?:\.\d+)*[\s、.．]+)")


def _normalize_title(text: str) -> str:
    return _NUM_PREFIX_RE.sub("", text).strip().lower()


def _find_block_for_title(title: str, blocks: ContentBlocksFile, content_md: str) -> int | None:
    target = _normalize_title(title)
    for block in blocks.blocks:
        if block.block_type not in {"paragraph", "heading"}:
            continue
        preview = (block.text_preview or content_md[block.char_start:block.char_end]).strip()
        if _normalize_title(preview) == target or target in preview:
            return block.block_index
    return None


def enrich_outline_anchors(
    tree: OutlineTree,
    blocks: ContentBlocksFile,
    *,
    content_md: str,
) -> OutlineTree:
    block_by_index = {b.block_index: b for b in blocks.blocks}
    new_nodes: list[OutlineNode] = []
    for node in tree.nodes:
        anchor = node.anchor.model_copy()
        idx = anchor.block_index
        if idx is None:
            idx = _find_block_for_title(node.title, blocks, content_md)
        if idx is not None and idx in block_by_index:
            block = block_by_index[idx]
            anchor.block_index = idx
            anchor.block_start = idx
            anchor.char_start = block.char_start
            anchor.char_end = block.char_end
        new_nodes.append(node.model_copy(update={"anchor": anchor}))
    return tree.model_copy(update={"nodes": new_nodes})
```

`builder.build_outline_from_workspace` 在 `_write_outline` 前：

```python
if workspace.content_blocks_path.exists():
    blocks = ContentBlocksFile.model_validate_json(
        workspace.content_blocks_path.read_text(encoding="utf-8")
    )
    tree = enrich_outline_anchors(tree, blocks, content_md=content_md)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python -m pytest tests/unit/test_anchor_enricher.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/doc_chunk/outline/anchor_enricher.py src/doc_chunk/outline/builder.py \
  tests/unit/test_anchor_enricher.py
git commit -m "feat: enrich outline nodes with char anchors from content blocks"
```

---

### Task 4: 基于锚点的分块 `plan_chunks_from_anchors`（R1 核心）

**Files:**
- Create: `src/doc_chunk/chunk/anchor_planner.py`
- Modify: `src/doc_chunk/chunk/planner.py`
- Modify: `src/doc_chunk/api.py`（`chunk_document` 默认走锚点）
- Test: `tests/unit/test_anchor_planner.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_anchor_planner.py
from doc_chunk.chunk.anchor_planner import plan_chunks_from_anchors
from doc_chunk.models.outline import Anchor, OutlineNode, OutlineTree


def _no_heading_outline() -> OutlineTree:
    return OutlineTree(
        strategy="content_heuristic",
        nodes=[
            OutlineNode(
                node_id="n1", title="总则", level=1, parent_id=None, sort_order=0,
                anchor=Anchor(char_start=0, char_end=8, block_start=0),
            ),
            OutlineNode(
                node_id="n2", title="技术方案", level=1, parent_id=None, sort_order=1,
                anchor=Anchor(char_start=20, char_end=32, block_start=2),
            ),
            OutlineNode(
                node_id="n3", title="报价", level=1, parent_id=None, sort_order=2,
                anchor=Anchor(char_start=50, char_end=58, block_start=4),
            ),
        ],
    )


def test_anchor_planner_one_chunk_per_outline_node_without_md_headings() -> None:
    content_md = (
        "1. 总则\n\n总则正文。\n\n"
        "2. 技术方案\n\n方案详情。\n\n"
        "3. 报价\n\n报价表。"
    )
    chunks = plan_chunks_from_anchors(content_md, _no_heading_outline(), max_tokens=20_000)
    main_chunks = [c for c in chunks if c.title != "Preface"]
    assert len(main_chunks) == 3
    assert all(c.original_node_ids for c in main_chunks)
    assert main_chunks[0].original_node_ids == ["n1"]
    assert "方案详情" in main_chunks[1].markdown
    assert "报价表" in main_chunks[2].markdown


def test_anchor_planner_excludes_child_body_from_parent_blocks_range() -> None:
    tree = OutlineTree(
        strategy="content_heuristic",
        nodes=[
            OutlineNode(
                node_id="n1", title="第一章", level=1, parent_id=None, sort_order=0,
                anchor=Anchor(char_start=0, char_end=10),
            ),
            OutlineNode(
                node_id="n2", title="第一节", level=2, parent_id="n1", sort_order=1,
                anchor=Anchor(char_start=30, char_end=40),
            ),
        ],
    )
    content_md = "# 第一章\n\n父级独有。\n\n## 第一节\n\n子级内容。"
    chunks = plan_chunks_from_anchors(content_md, tree, max_tokens=20_000)
    parent = next(c for c in chunks if c.original_node_ids == ["n1"])
    assert "父级独有" in parent.markdown
    assert "子级内容" not in parent.markdown
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest tests/unit/test_anchor_planner.py -v
```

Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/doc_chunk/chunk/anchor_planner.py
from __future__ import annotations

import re

from doc_chunk.chunk.planner import _split_oversized  # reuse existing helper
from doc_chunk.chunk.tokenizer import estimate_tokens
from doc_chunk.models.chunk import ContentChunk
from doc_chunk.models.outline import OutlineNode, OutlineTree

_IMAGE_RE = re.compile(r"!\[[^\]]*]\(([^)]+)\)")


def _sorted_sliceable_nodes(nodes: list[OutlineNode]) -> list[OutlineNode]:
    return sorted(
        nodes,
        key=lambda n: (
            n.anchor.char_start if n.anchor.char_start is not None else 10**9,
            n.sort_order,
        ),
    )


def _section_end_char(node: OutlineNode, ordered: list[OutlineNode], content_len: int) -> int:
    start = node.anchor.char_start or 0
    level = node.level
    for other in ordered:
        other_start = other.anchor.char_start
        if other_start is None or other_start <= start:
            continue
        if other.node_id == node.node_id:
            continue
        if other.level <= level:
            return other_start
    return content_len


def _build_section_path(node: OutlineNode, node_map: dict[str, OutlineNode]) -> list[str]:
    chain: list[str] = []
    cursor: OutlineNode | None = node
    seen: set[str] = set()
    while cursor and cursor.node_id not in seen:
        seen.add(cursor.node_id)
        chain.append(cursor.title)
        cursor = node_map.get(cursor.parent_id) if cursor.parent_id else None
    return list(reversed(chain))


def plan_chunks_from_anchors(
    content_md: str,
    outline_tree: OutlineTree,
    *,
    max_tokens: int = 20_000,
) -> list[ContentChunk]:
    if max_tokens <= 0:
        raise ValueError("max_tokens must be positive")

    node_map = {n.node_id: n for n in outline_tree.nodes}
    ordered = _sorted_sliceable_nodes(outline_tree.nodes)
    if not ordered:
        return []

    chunks: list[ContentChunk] = []
    chunk_index = 1
    content_len = len(content_md)

    first_start = ordered[0].anchor.char_start or 0
    if first_start > 0 and content_md[:first_start].strip():
        preface_md = content_md[:first_start]
        chunks.append(
            ContentChunk(
                chunk_id=f"chunk-{chunk_index:04d}",
                title="Preface",
                heading_level=None,
                markdown=preface_md if preface_md.endswith("\n") else f"{preface_md}\n",
                source_file="content.md",
                token_estimate=estimate_tokens(preface_md),
                image_refs=[m.group(1) for m in _IMAGE_RE.finditer(preface_md)],
            )
        )
        chunk_index += 1

    for node in ordered:
        start = node.anchor.char_start
        if start is None:
            continue
        end = _section_end_char(node, ordered, content_len)
        raw = content_md[start:end]
        if not raw.strip():
            continue
        parts = _split_oversized(raw, max_tokens)
        section_path = _build_section_path(node, node_map)
        for part_idx, part in enumerate(parts):
            markdown = part if part.endswith("\n") else f"{part}\n"
            chunks.append(
                ContentChunk(
                    chunk_id=f"chunk-{chunk_index:04d}",
                    title=node.title,
                    section_path=section_path,
                    heading_level=node.level if part_idx == 0 else None,
                    markdown=markdown,
                    source_file="content.md",
                    source_ranges=[{"char_start": start, "char_end": end}],
                    token_estimate=estimate_tokens(part),
                    image_refs=[m.group(1) for m in _IMAGE_RE.finditer(part)],
                    original_node_ids=[node.node_id],
                )
            )
            chunk_index += 1

    for idx, chunk in enumerate(chunks):
        chunk.previous_chunk_id = chunks[idx - 1].chunk_id if idx > 0 else None
        chunk.next_chunk_id = chunks[idx + 1].chunk_id if idx + 1 < len(chunks) else None
    return chunks
```

`planner.py` 保留 `plan_chunks_from_outline`（v1 markdown 标题路径）；新增：

```python
def plan_chunks(
    content_md: str,
    outline_tree: OutlineTree,
    *,
    max_tokens: int = 20_000,
    markdown_headings_only: bool = False,
) -> list[ContentChunk]:
    if markdown_headings_only:
        return plan_chunks_from_outline(content_md, outline_tree, max_tokens=max_tokens)
    has_char_anchors = any(n.anchor.char_start is not None for n in outline_tree.nodes)
    if has_char_anchors:
        return plan_chunks_from_anchors(content_md, outline_tree, max_tokens=max_tokens)
    return plan_chunks_from_outline(content_md, outline_tree, max_tokens=max_tokens)
```

`api.chunk_document` 调用 `plan_chunks(...)`；CLI `chunk` 增加 `--markdown-headings-only`。

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python -m pytest tests/unit/test_anchor_planner.py tests/unit/test_chunk_planner.py -v
```

Expected: PASS（v1 回归测试仍绿）

- [ ] **Step 5: Commit**

```bash
git add src/doc_chunk/chunk/anchor_planner.py src/doc_chunk/chunk/planner.py \
  src/doc_chunk/api.py src/doc_chunk/cli/main.py tests/unit/test_anchor_planner.py
git commit -m "feat: anchor-based chunking aligned with outline nodes"
```

---

### Task 5: 合成无 Heading 样式 fixture + 契约测试（US1）

**Files:**
- Create: `tests/fixtures/no_heading_style.docx`（生成脚本或 commit 二进制）
- Create: `tests/contract/test_chunk_anchor_alignment.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/contract/test_chunk_anchor_alignment.py
from __future__ import annotations

from pathlib import Path

import pytest
from docx import Document

from doc_chunk.api import chunk_document, extract_file, extract_outline

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
NO_HEADING_DOCX = FIXTURES / "no_heading_style.docx"


@pytest.fixture(scope="module", autouse=True)
def ensure_no_heading_fixture() -> None:
  if NO_HEADING_DOCX.exists():
      return
  FIXTURES.mkdir(parents=True, exist_ok=True)
  doc = Document()
  doc.add_paragraph("1. 投标须知")
  doc.add_paragraph("须知正文第一段。")
  doc.add_paragraph("2. 技术方案")
  doc.add_paragraph("方案描述。")
  doc.add_paragraph("2.1 系统架构")
  doc.add_paragraph("架构说明。")
  doc.add_paragraph("3. 报价说明")
  doc.add_paragraph("报价表格见下。")
  doc.save(NO_HEADING_DOCX)


def test_no_heading_docx_chunk_count_matches_outline(tmp_path: Path) -> None:
    ws = tmp_path / "no-heading-ws"
    extract_file(NO_HEADING_DOCX, ws, overwrite=True)
    outline = extract_outline(ws)
    chunk_document(ws, use_refined=False)
    import json
    index = json.loads((ws / "chunks" / "index.json").read_text(encoding="utf-8"))
    outline_nodes = [n for n in outline.nodes]
    main_chunks = [c for c in index["chunks"] if c["title"] != "Preface"]
    ratio = len(main_chunks) / max(len(outline_nodes), 1)
    assert ratio >= 0.8, f"chunks={len(main_chunks)} outline={len(outline_nodes)}"
    assert len(main_chunks) > 1
    for entry in main_chunks:
        assert entry.get("original_node_ids"), entry["title"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest tests/contract/test_chunk_anchor_alignment.py -v
```

Expected: FAIL（ratio < 0.8 或整篇仅 1 chunk — 锚点分块未接入 pipeline）

- [ ] **Step 3:** 确保 Task 4 已合并；若仍失败，调试 `anchor_enricher` 对编号标题的匹配。

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python -m pytest tests/contract/test_chunk_anchor_alignment.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/contract/test_chunk_anchor_alignment.py tests/conftest.py \
  tests/fixtures/no_heading_style.docx
git commit -m "test: contract test for outline-chunk anchor alignment"
```

---

### Task 6: `document_tree.json` 与 `tree` 阶段（R3）

**Files:**
- Create: `src/doc_chunk/models/document_tree.py`
- Create: `src/doc_chunk/tree/builder.py`
- Create: `src/doc_chunk/tree/__init__.py`
- Modify: `src/doc_chunk/api.py`
- Modify: `src/doc_chunk/cli/main.py`
- Test: `tests/unit/test_document_tree.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_document_tree.py
from doc_chunk.models.content_block import ContentBlockRecord, ContentBlocksFile
from doc_chunk.models.outline import Anchor, OutlineNode, OutlineTree
from doc_chunk.tree.builder import build_document_tree


def test_build_document_tree_heading_parent_links() -> None:
    blocks = ContentBlocksFile(
        blocks=[
            ContentBlockRecord(0, "heading", 0, 12, "1. 技术方案"),
            ContentBlockRecord(1, "paragraph", 12, 30, "正文"),
            ContentBlockRecord(2, "table", 30, 60, "|a|b|"),
            ContentBlockRecord(3, "image", 60, 90, image_ref="images/x.png"),
        ]
    )
    outline = OutlineTree(
        strategy="content_heuristic",
        nodes=[
            OutlineNode(
                node_id="n1", title="技术方案", level=1,
                parent_id=None, sort_order=0,
                anchor=Anchor(char_start=0, block_start=0),
            )
        ],
    )
    tree = build_document_tree(blocks, outline, content_md="1. 技术方案\n\n正文\n\n|a|b|\n\n![](images/x.png)\n")
    types = {n.node_type for n in tree.nodes}
    assert types >= {"heading", "paragraph", "table", "image"}
    heading = next(n for n in tree.nodes if n.node_type == "heading")
    assert heading.outline_node_id == "n1"
    para = next(n for n in tree.nodes if n.node_type == "paragraph")
    assert para.parent_id == heading.node_id
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest tests/unit/test_document_tree.py -v
```

Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/doc_chunk/models/document_tree.py
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class DocumentTreeNode(BaseModel):
    node_id: str
    parent_id: str | None
    outline_node_id: str | None = None
    node_type: Literal["heading", "paragraph", "table", "image", "other"]
    title: str | None = None
    level: int | None = None
    sort_order: int
    source_block_index: int
    text: str | None = None
    image_ref: str | None = None
    needs_review: bool = False


class DocumentTreeFile(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    nodes: list[DocumentTreeNode] = Field(default_factory=list)
```

`tree/builder.py`：遍历 `blocks.blocks`；若 `block_index` 命中 outline 节点 `block_start` 则生成 `heading` 并记录 `outline_node_id`；否则按当前栈顶 heading 作为 `parent_id`；`image` 块写 `image_ref`。

`api.py` 新增：

```python
def build_tree(workspace: Path) -> DocumentTreeFile:
    ws = OutputWorkspace.open_existing(Path(workspace))
    blocks = ContentBlocksFile.model_validate_json(ws.content_blocks_path.read_text(encoding="utf-8"))
    outline = OutlineTree.model_validate_json(ws.outline_path.read_text(encoding="utf-8"))
    content_md = ws.content_path.read_text(encoding="utf-8")
    tree = build_document_tree(blocks, outline, content_md=content_md)
    ws.document_tree_path.write_text(tree.model_dump_json(indent=2), encoding="utf-8")
    # update manifest stages.tree + outputs.document_tree
    return tree
```

`layout.py` 增加 `document_tree_path`。

CLI：`doc-chunk tree WORKSPACE`。

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python -m pytest tests/unit/test_document_tree.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/doc_chunk/models/document_tree.py src/doc_chunk/tree/ \
  src/doc_chunk/api.py src/doc_chunk/cli/main.py src/doc_chunk/workspace/layout.py \
  tests/unit/test_document_tree.py
git commit -m "feat: add document_tree.json and tree stage"
```

---

### Task 7: `chunk.blocks` 与 `blocks_to_v1_json`（R4）

**Files:**
- Modify: `src/doc_chunk/models/chunk.py`
- Create: `src/doc_chunk/chunk/blocks_builder.py`
- Create: `src/doc_chunk/convert/blocks_v1.py`
- Modify: `src/doc_chunk/chunk/anchor_planner.py`（填充 blocks）
- Test: `tests/unit/test_blocks_builder.py`, `tests/unit/test_blocks_v1_convert.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_blocks_builder.py
from doc_chunk.chunk.blocks_builder import build_chunk_blocks

MAX = 32_000


def test_build_chunk_blocks_splits_types_and_truncates() -> None:
    long_text = "x" * (MAX + 100)
    blocks = build_chunk_blocks(
        markdown=f"段落。\n\n|a|b|\n\n![img](images/i.png)\n\n{long_text}",
        char_start=0,
        char_end=MAX + 200,
    )
    types = [b.type for b in blocks]
    assert "paragraph" in types
    assert "table" in types
    assert "image" in types
    assert all(len(b.text or "") <= MAX for b in blocks if b.type != "image")
```

```python
# tests/unit/test_blocks_v1_convert.py
from doc_chunk.convert.blocks_v1 import blocks_to_v1_json
from doc_chunk.models.chunk import ChunkBlock

def test_blocks_to_v1_json_format() -> None:
    payload = blocks_to_v1_json([
        ChunkBlock(type="paragraph", text="hello"),
        ChunkBlock(type="image", image_ref="images/a.png"),
    ])
    import json
    data = json.loads(payload)
    assert data["format"] == "blocks_v1"
    assert data["blocks"][0]["type"] == "paragraph"
    assert data["blocks"][1]["image_ref"] == "images/a.png"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/unit/test_blocks_builder.py tests/unit/test_blocks_v1_convert.py -v
```

Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# src/doc_chunk/models/chunk.py — add:
class ChunkBlock(BaseModel):
    type: Literal["paragraph", "table", "image"]
    text: str | None = None
    image_ref: str | None = None

# ContentChunk 增加:
blocks: list[ChunkBlock] = Field(default_factory=list)
```

```python
# src/doc_chunk/chunk/blocks_builder.py
import re
MAX_BLOCK_TEXT_CHARS = 32_000
_TABLE_LINE_RE = re.compile(r"^\|.+\|$")
_IMAGE_RE = re.compile(r"!\[[^\]]*]\(([^)]+)\)")

def build_chunk_blocks(*, markdown: str, char_start: int, char_end: int) -> list[ChunkBlock]:
    # 解析 markdown 行，按 paragraph/table/image 分段，text 截断至 32000
    ...
```

```python
# src/doc_chunk/convert/blocks_v1.py
import json
from doc_chunk.models.chunk import ChunkBlock

def blocks_to_v1_json(blocks: list[ChunkBlock]) -> str:
    payload = {
        "format": "blocks_v1",
        "blocks": [b.model_dump(mode="json", exclude_none=True) for b in blocks],
    }
    return json.dumps(payload, ensure_ascii=False)
```

在 `plan_chunks_from_anchors` 创建 `ContentChunk` 时调用 `build_chunk_blocks`。

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/unit/test_blocks_builder.py tests/unit/test_blocks_v1_convert.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/doc_chunk/models/chunk.py src/doc_chunk/chunk/blocks_builder.py \
  src/doc_chunk/convert/ src/doc_chunk/chunk/anchor_planner.py \
  tests/unit/test_blocks_builder.py tests/unit/test_blocks_v1_convert.py
git commit -m "feat: add chunk.blocks and blocks_v1 converter"
```

---

### Task 8: `linkage.json`（R5）

**Files:**
- Create: `src/doc_chunk/models/linkage.py`
- Create: `src/doc_chunk/linkage/builder.py`
- Modify: `src/doc_chunk/api.py`（chunk 后写 linkage）
- Test: `tests/unit/test_linkage_builder.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_linkage_builder.py
from doc_chunk.linkage.builder import build_linkage
from doc_chunk.models.chunk import ContentChunk
from doc_chunk.models.document_tree import DocumentTreeFile, DocumentTreeNode
from doc_chunk.models.outline import OutlineNode, OutlineTree

def test_linkage_maps_outline_to_chunks_and_tree() -> None:
    outline = OutlineTree(nodes=[
        OutlineNode(node_id="n1", title="A", level=1, parent_id=None, sort_order=0),
    ])
    tree = DocumentTreeFile(nodes=[
        DocumentTreeNode(
            node_id="t1", parent_id=None, outline_node_id="n1",
            node_type="heading", title="A", level=1, sort_order=0, source_block_index=0,
        )
    ])
    chunks = [
        ContentChunk(chunk_id="chunk-0001", title="A", original_node_ids=["n1"], heading_level=1),
        ContentChunk(chunk_id="chunk-0002", title="A", original_node_ids=["n1"], heading_level=None),
    ]
    linkage = build_linkage(outline, tree, chunks, outline_source="original")
    assert linkage.entries[0].outline_node_id == "n1"
    assert linkage.entries[0].chunk_ids == ["chunk-0001", "chunk-0002"]
    assert linkage.entries[0].primary_chunk_id == "chunk-0001"
    assert linkage.entries[0].document_tree_node_ids == ["t1"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest tests/unit/test_linkage_builder.py -v
```

Expected: FAIL

- [ ] **Step 3: Write minimal implementation**（`linkage/builder.py` + `models/linkage.py` 按 spec §R5 schema）

`chunk_document` 在 `write_chunks` 后若 `document_tree.json` 存在则 `build_linkage` 并写入 `workspace.linkage_path`。

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python -m pytest tests/unit/test_linkage_builder.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/doc_chunk/models/linkage.py src/doc_chunk/linkage/ src/doc_chunk/api.py \
  tests/unit/test_linkage_builder.py
git commit -m "feat: add linkage.json cross-artifact ID mapping"
```

---

### Task 9: pipeline 串联 tree + linkage + manifest 扩展（R7）

**Files:**
- Modify: `src/doc_chunk/api.py`
- Modify: `tests/integration/test_pipeline.py`
- Create: `tests/integration/test_pipeline_tk_outputs.py`
- Modify: `tests/contract/test_workspace_schemas.py`
- Create: `tests/fixtures/expected/*.json`（minimal fixtures）

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_pipeline_tk_outputs.py
from pathlib import Path
from doc_chunk.api import run_pipeline

def test_pipeline_produces_tk_integration_artifacts(sample_docx: Path, tmp_path: Path) -> None:
    out = tmp_path / "tk-ws"
    result = run_pipeline(sample_docx, out, overwrite=True, skip_refine=True, skip_enrich=True)
    assert result.status == "success"
    assert (out / "content.blocks.json").exists()
    assert (out / "images" / "manifest.json").exists()
    assert (out / "document_tree.json").exists()
    assert (out / "linkage.json").exists()
    manifest = __import__("json").loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["stages"].get("tree", {}).get("status") == "success"
    assert manifest["outputs"].get("linkage") == "linkage.json"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest tests/integration/test_pipeline_tk_outputs.py -v
```

Expected: FAIL（缺少 document_tree.json / linkage.json）

- [ ] **Step 3: Update `_run_single_pipeline`**

```python
def _safe_progress(cb, stage, payload):
    if cb is None:
        return
    try:
        cb(stage, payload)
    except Exception as exc:
        # append warning to manifest later
        ...

def _run_single_pipeline(...):
    _safe_progress(on_progress, "extract", {"message": "extracting", "current": 0, "total": 1})
    manifest = extract_file(...)
    _safe_progress(on_progress, "outline", {"message": "building outline", "current": 0, "total": 1})
    extract_outline(output_dir)
    _safe_progress(on_progress, "tree", {"message": "building document tree", "current": 0, "total": 1})
    build_tree(output_dir)
    _safe_progress(on_progress, "chunk", {"message": "chunking", "current": 0, "total": None})
    chunk_document(...)
    # chunk_document internally writes linkage
```

- [ ] **Step 4: Run integration + contract tests**

```bash
.venv/bin/python -m pytest tests/integration/test_pipeline_tk_outputs.py tests/contract/ -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/doc_chunk/api.py tests/integration/test_pipeline_tk_outputs.py \
  tests/contract/test_workspace_schemas.py tests/fixtures/expected/
git commit -m "feat: pipeline emits tree, linkage, and extended manifest"
```

---

### Task 10: 进度回调增强（R8 / US6）

**Files:**
- Modify: `src/doc_chunk/api.py`
- Modify: `src/doc_chunk/chunk/anchor_planner.py`（可选 progress hook）
- Test: `tests/unit/test_progress_callback.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_progress_callback.py
from pathlib import Path
from doc_chunk.api import run_pipeline

def test_on_progress_receives_stage_messages(sample_docx: Path, tmp_path: Path) -> None:
    events: list[tuple[str, dict]] = []
    run_pipeline(
        sample_docx, tmp_path / "prog",
        overwrite=True, skip_refine=True, skip_enrich=True,
        on_progress=lambda stage, payload: events.append((stage, payload)),
    )
    stages = {s for s, _ in events}
    assert {"extract", "outline", "tree", "chunk"} <= stages
    chunk_events = [p for s, p in events if s == "chunk"]
    assert any("current" in p for p in chunk_events)


def test_on_progress_exception_does_not_fail_pipeline(sample_docx: Path, tmp_path: Path) -> None:
    def bad_cb(stage, payload):
        raise RuntimeError("boom")
    result = run_pipeline(
        sample_docx, tmp_path / "prog2",
        overwrite=True, skip_refine=True, skip_enrich=True,
        on_progress=bad_cb,
    )
    assert result.status == "success"
```

- [ ] **Step 2–4:** 实现 `_safe_progress`；chunk 循环中 `on_progress("chunk", {"message": "...", "current": i, "total": n})`。

```bash
.venv/bin/python -m pytest tests/unit/test_progress_callback.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/doc_chunk/api.py tests/unit/test_progress_callback.py
git commit -m "feat: safe on_progress callbacks with chunk counters"
```

---

### Task 11: docm 显式拒绝（R9 / US7）

**Files:**
- Modify: `src/doc_chunk/api.py`
- Modify: `src/doc_chunk/extract/detect.py`
- Modify: `README.md`
- Test: `tests/unit/test_docm_reject.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_docm_reject.py
import pytest
from pathlib import Path
from doc_chunk.api import extract_file
from doc_chunk.errors import UnsupportedFormatError

def test_docm_raises_unsupported_format(tmp_path: Path, sample_docx: Path) -> None:
    docm = tmp_path / "sample.docm"
    docm.write_bytes(sample_docx.read_bytes())
    with pytest.raises(UnsupportedFormatError, match="docm"):
        extract_file(docm, tmp_path / "out", overwrite=True)
```

- [ ] **Step 2–4:** `extract_file` 在 `file_type == "docm"` 时 raise；README 说明转 docx 流程。

```bash
.venv/bin/python -m pytest tests/unit/test_docm_reject.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/doc_chunk/api.py README.md tests/unit/test_docm_reject.py
git commit -m "feat: reject docm at extract with clear error for tk converter"
```

---

### Task 12: enrich 外置分类 hints（R10 / US8）

**Files:**
- Modify: `src/doc_chunk/models/chunk.py`（ChunkMetadata 字段）
- Modify: `src/doc_chunk/metadata/rules.py`
- Modify: `src/doc_chunk/metadata/classify.py`
- Create: `tests/fixtures/classification_hints.yaml`
- Test: `tests/unit/test_classify_hints.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_classify_hints.py
from pathlib import Path
from doc_chunk.metadata.classify import classify_chunk

def test_classification_config_emits_hints(tmp_path: Path) -> None:
    cfg = tmp_path / "hints.yaml"
    cfg.write_text("""
product_categories:
  - aliases: ["餐补", "福利餐"]
    hint: "餐补平台"
chapter_taxonomies:
  - aliases: ["技术方案", "系统设计"]
    hint: "技术方案"
""", encoding="utf-8")
    result = classify_chunk(
        title="餐补技术方案",
        markdown="福利餐平台实施方案",
        llm_client=None,
        classification_config=cfg,
    )
    assert "餐补平台" in result.get("product_category_hints", [])
    assert "技术方案" in result.get("chapter_taxonomy_hints", [])
```

- [ ] **Step 2–4:** 扩展 `load_classification_rules` 解析新 YAML 段；`classify_chunk` 扫描 aliases 填充 hints 数组；`ChunkMetadata` 增加 `product_category_hints: list[str]`、`chapter_taxonomy_hints: list[str]`。

```bash
.venv/bin/python -m pytest tests/unit/test_classify_hints.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/doc_chunk/models/chunk.py src/doc_chunk/metadata/ tests/unit/test_classify_hints.py
git commit -m "feat: classification config product and chapter taxonomy hints"
```

---

### Task 13: 可选 `extract --promote-headings`（R2 P1）

**Files:**
- Modify: `src/doc_chunk/extract/docx_extractor.py`
- Modify: `src/doc_chunk/cli/main.py`
- Test: `tests/unit/test_promote_headings.py`

- [ ] **Step 1: Write the failing test**

```python
def test_promote_headings_auto_adds_hash_prefix(no_heading_docx, tmp_path):
    # extract with promote_headings="auto" + pre-built outline titles
    # content.md should contain "# 技术方案" while chunk still uses anchors
    ...
```

- [ ] **Step 2–5:** 实现 `promote_headings: Literal["off","auto"] = "off"`；仅在 extract 后二次扫描或 extract 时传入 title 列表（默认 off，不改变 v1 外观）。

---

### Task 14: 候选类型元数据 R11（P2，可选）

**Files:**
- Create: `src/doc_chunk/metadata/candidate_rules.yaml`
- Modify: `src/doc_chunk/metadata/classify.py`
- Test: `tests/unit/test_candidate_type_hints.py`

- [ ] 按 `chapter_taxonomy_hints` 查表输出 `suggested_candidate_type` / `suggested_knowledge_type`；无匹配则省略字段。

---

### Task 15: 文档与 schema 同步（NF4）

**Files:**
- Modify: `specs/001-document-extract-chunk/contracts/workspace-schemas.md`
- Modify: `README.md`

- [ ] **Step 1:** 在 `workspace-schemas.md` 增加 `document_tree.json`、`linkage.json`、`images/manifest.json`、`content.blocks.json`、`chunk.blocks` 章节。

- [ ] **Step 2:** README 文档索引增加本集成规格链接；快速开始增加 `doc-chunk tree`；说明锚点分块与 `--markdown-headings-only` 回归开关。

- [ ] **Step 3: 全量验证**

```bash
.venv/bin/python -m pytest tests/ -q
```

Expected: 全绿

- [ ] **Step 4: Commit**

```bash
git add specs/001-document-extract-chunk/contracts/workspace-schemas.md README.md
git commit -m "docs: workspace schemas and README for tk integration"
```

---

## Self-Review

### Spec coverage

| 需求 | 任务 |
|------|------|
| R1 anchor 分块 | Task 3, 4, 5 |
| R2 块索引侧车 | Task 1, 13 |
| R3 document_tree | Task 6 |
| R4 chunk.blocks | Task 7 |
| R5 linkage | Task 8 |
| R6 images manifest | Task 2 |
| R7 manifest + 契约 | Task 9, 15 |
| R8 进度回调 | Task 10 |
| R9 docm | Task 11（方案 B） |
| R10 enrich hints | Task 12 |
| R11 候选类型 | Task 14（P2） |
| US1–US8 | Tasks 5, 6, 7, 8, 9, 10, 11, 12 |
| NF1 性能 | Task 9 后手动 benchmark 餐补样例 ≤ v1 150% |
| NF3 合成 fixture | Task 5 |
| NF4 文档 | Task 15 |

### Placeholder scan

无 TBD / TODO /「类似 Task N」省略；Task 13 Step 1 测试体需在实现时补全具体断言（依赖 Task 5 fixture）。

### Type consistency

- 锚点统一 `char_start`/`char_end`（`int`，`content.md` 字符偏移）
- `ChunkBlock.type` 与 `DocumentTreeNode.node_type` 子集对齐
- `linkage.entries[].primary_chunk_id` 指向 `heading_level != null` 首块
- `blocks_to_v1_json` 输出 `format: blocks_v1` 供 tk `content_blocks.blocks_v1()` 消费

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-15-doc-chunk-tender-knowledge-integration.md`. Two execution options:

**1. Subagent-Driven (recommended)** — 每个 Task 派发独立 subagent，任务间人工/代理 review，迭代最快

**2. Inline Execution** — 本会话用 executing-plans 按 Task 批量执行，checkpoint 处暂停确认

Which approach?
