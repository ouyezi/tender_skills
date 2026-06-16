# doc_chunk tender_knowledge 集成修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **需求来源**: [`specs/2026-06-15-doc-chunk-tk-integration-fixes.md`](../specs/2026-06-15-doc-chunk-tk-integration-fixes.md)（v1.1，已澄清）

**Goal:** 修复 `document_tree` 节点 ID 碰撞与 outline→tree heading 缺口，实现 linkage 全覆盖与 `chunks/index.json` 三联映射，补齐 blocks_v1 / enrich 元数据，使 tender_knowledge 适配层可安全落库。

**Architecture:** P0 按数据流顺序推进：`anchor_enricher`（方案 B 前移锚点）→ `tree/builder`（R1 单计数器 + 方案 A 合成 heading）→ `linkage/builder`（全覆盖 entry）→ `api.chunk_document`（index `document_tree_node_id` + manifest warnings）。P1 扩展 `blocks_v1` 与 `classify_chunk` 默认规则。契约测试用双 fixture；餐补样例作可选集成门禁 + NF1 耗时断言。

**Tech Stack:** Python 3.11+、`doc_chunk` 包、pytest、`python-docx`（fixture 生成）、Pydantic v2 模型。

---

## File Map

| 文件 | 职责 | 关联需求 |
|------|------|----------|
| `src/doc_chunk/outline/anchor_enricher.py` | 锚点从 image/table 前移到 paragraph | R2 方案 B |
| `src/doc_chunk/tree/builder.py` | 单计数器 node_id、合成 heading、重复锚点检测 | R1, R2 方案 A |
| `src/doc_chunk/linkage/builder.py` | 每个 outline 一条 linkage entry | R3 |
| `src/doc_chunk/api.py` | manifest warnings、`document_tree_node_id` 回填 index | R3 |
| `src/doc_chunk/convert/blocks_v1.py` | `image_ref_to_asset_id` 双字段输出 | R4 |
| `src/doc_chunk/metadata/default_classification.yaml` | 默认 `chapter_taxonomies` | R5 |
| `src/doc_chunk/metadata/candidate_rules.yaml` | `ignore` 规则 [Partially Completed in 002 / 003 Refactored] | R5 |
| `src/doc_chunk/metadata/classify.py` | 关键词直映射 `suggested_*` [Partially Completed in 002 / 003 Refactored] | R5 |
| `tests/fixtures/outline_anchor_on_image.docx` | 图片锚点 fixture | R6 |
| `tests/fixtures/outline_anchor_on_table.docx` | 表格锚点 fixture | R6 |
| `tests/contract/test_document_tree_outline_coverage.py` | R1+R2+R6 契约 | R6 |
| `tests/integration/test_canbu_regression.py` | 餐补可选回归 + NF1 计时 | R7, NF1 |
| `specs/001-document-extract-chunk/contracts/workspace-schemas.md` | blocks_v1 / linkage / index 契约文档 | R4, R3 |

**共享辅助函数（建议放 `src/doc_chunk/tree/builder.py` 或 `src/doc_chunk/outline/utils.py`）：**

```python
def is_flat_fallback_exempt(outline: OutlineTree) -> bool:
    return outline.strategy == "flat_fallback" and len(outline.nodes) == 1
```

---

## Task 1: 统一 document_tree node_id（R1）

**Files:**
- Modify: `src/doc_chunk/tree/builder.py`
- Test: `tests/unit/test_document_tree.py`

- [ ] **Step 1: Write the failing test**

在 `tests/unit/test_document_tree.py` 追加：

```python
def test_document_tree_node_ids_unique_with_image_before_heading() -> None:
    """复现餐补撞号：heading 与 body 各用 counter 时会生成重复 t0001。"""
    blocks = ContentBlocksFile(
        blocks=[
            ContentBlockRecord(
                block_index=0, block_type="image", char_start=0, char_end=10, image_ref="images/cover.png"
            ),
            ContentBlockRecord(
                block_index=1, block_type="paragraph", char_start=10, char_end=30, text_preview="1. 封面"
            ),
        ]
    )
    outline = OutlineTree(
        strategy="toc",
        nodes=[
            OutlineNode(
                node_id="n1",
                title="封面",
                level=1,
                parent_id=None,
                sort_order=0,
                anchor=Anchor(char_start=0, block_start=0),
            ),
            OutlineNode(
                node_id="n2",
                title="正文",
                level=1,
                parent_id=None,
                sort_order=1,
                anchor=Anchor(char_start=10, block_start=1),
            ),
        ],
    )
    tree = build_document_tree(blocks, outline, content_md="![](images/cover.png)\n\n1. 封面\n\n")
    ids = [n.node_id for n in tree.nodes]
    assert len(ids) == len(set(ids)), f"duplicate node_id: {ids}"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/tongqianni/xlab/tender_skills
.venv/bin/python -m pytest tests/unit/test_document_tree.py::test_document_tree_node_ids_unique_with_image_before_heading -v
```

Expected: FAIL（当前 `heading_counter` 与 `node_counter` 可能撞号）

- [ ] **Step 3: Implement single counter**

修改 `src/doc_chunk/tree/builder.py`：删除 `heading_counter`，仅保留 `node_counter`；每次 `append` 节点前 `node_counter += 1`，`node_id=f"t{node_counter:04d}"`。

```python
# 循环内统一模式（heading 与 body 分支共用）
node_counter += 1
node_id = f"t{node_counter:04d}"
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/python -m pytest tests/unit/test_document_tree.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/doc_chunk/tree/builder.py tests/unit/test_document_tree.py
git commit -m "fix(tree): use single node_counter for unique document_tree node_id"
```

---

## Task 2: anchor_enricher 前移非段落锚点（R2 方案 B）

**Files:**
- Modify: `src/doc_chunk/outline/anchor_enricher.py`
- Test: `tests/unit/test_anchor_enricher.py`

- [ ] **Step 1: Write the failing test**

在 `tests/unit/test_anchor_enricher.py` 追加：

```python
def test_relocate_anchor_from_image_to_following_paragraph() -> None:
    blocks = ContentBlocksFile(
        blocks=[
            ContentBlockRecord(
                block_index=0, block_type="image", char_start=0, char_end=10, image_ref="images/cover.png"
            ),
            ContentBlockRecord(
                block_index=1, block_type="paragraph", char_start=10, char_end=25, text_preview="封面"
            ),
            ContentBlockRecord(
                block_index=2, block_type="paragraph", char_start=25, char_end=40, text_preview="第二章"
            ),
        ]
    )
    tree = OutlineTree(
        strategy="toc",
        nodes=[
            OutlineNode(
                node_id="n1", title="封面", level=1, parent_id=None, sort_order=0,
                anchor=Anchor(block_index=0, block_start=0),
            ),
            OutlineNode(
                node_id="n2", title="第二章", level=1, parent_id=None, sort_order=1,
                anchor=Anchor(block_index=2, block_start=2),
            ),
        ],
    )
    enriched = enrich_outline_anchors(tree, blocks, content_md="![](x)\n\n封面\n\n第二章\n\n")
    assert enriched.nodes[0].anchor.block_start == 1
    assert enriched.nodes[0].anchor.block_index == 1


def test_relocate_prefers_title_match_over_first_paragraph() -> None:
    """首个 paragraph 非标题时，应继续扫描至标题匹配块，而非短路到第一个 paragraph。"""
    blocks = ContentBlocksFile(
        blocks=[
            ContentBlockRecord(
                block_index=0, block_type="image", char_start=0, char_end=10, image_ref="images/cover.png"
            ),
            ContentBlockRecord(
                block_index=1, block_type="paragraph", char_start=10, char_end=25, text_preview="无关前言"
            ),
            ContentBlockRecord(
                block_index=2, block_type="paragraph", char_start=25, char_end=40, text_preview="封面"
            ),
        ]
    )
    tree = OutlineTree(
        strategy="toc",
        nodes=[
            OutlineNode(
                node_id="n1", title="封面", level=1, parent_id=None, sort_order=0,
                anchor=Anchor(block_index=0, block_start=0),
            ),
        ],
    )
    enriched = enrich_outline_anchors(tree, blocks, content_md="![](x)\n\n无关前言\n\n封面\n\n")
    assert enriched.nodes[0].anchor.block_start == 2
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest tests/unit/test_anchor_enricher.py::test_relocate_anchor_from_image_to_following_paragraph -v
```

Expected: FAIL（`block_start` 仍为 0）

- [ ] **Step 3: Implement relocation（两阶段退化，禁止首个 paragraph 短路）**

> **逻辑要点：** 强匹配（标题对上）立即返回；否则记录 `first_paragraph_index` 作兜底，**扫完整个搜索窗口**后再退化。禁止在首个 paragraph 未命中标题时 `return`。

在 `anchor_enricher.py` 增加：

```python
def _next_block_start_limit(nodes: list[OutlineNode], sort_order: int) -> int | None:
    for node in nodes:
        if node.sort_order > sort_order and node.anchor.block_start is not None:
            return node.anchor.block_start
    return None


def _relocate_non_paragraph_anchor(
    node: OutlineNode,
    blocks: ContentBlocksFile,
    content_md: str,
    *,
    all_nodes: list[OutlineNode],
) -> int | None:
    idx = node.anchor.block_index
    if idx is None:
        return None
    block_by_index = {b.block_index: b for b in blocks.blocks}
    current = block_by_index.get(idx)
    if current is None or current.block_type in {"paragraph", "heading"}:
        return idx

    limit = _next_block_start_limit(all_nodes, node.sort_order)
    target_title = _normalize_title(node.title)
    first_paragraph_index: int | None = None

    for block in blocks.blocks:
        if block.block_index <= idx:
            continue
        if limit is not None and block.block_index >= limit:
            break
        if block.block_type != "paragraph":
            continue

        if first_paragraph_index is None:
            first_paragraph_index = block.block_index

        preview = (block.text_preview or content_md[block.char_start : block.char_end]).strip()
        normalized = _normalize_title(preview)
        if normalized == target_title or target_title in normalized or normalized in target_title:
            return block.block_index

    return first_paragraph_index if first_paragraph_index is not None else idx
```

在 `enrich_outline_anchors` 循环内，在写入 anchor 前调用 `_relocate_non_paragraph_anchor`。

- [ ] **Step 4: Run tests**

```bash
.venv/bin/python -m pytest tests/unit/test_anchor_enricher.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/doc_chunk/outline/anchor_enricher.py tests/unit/test_anchor_enricher.py
git commit -m "fix(outline): relocate anchors from image/table to paragraph blocks"
```

---

## Task 3: 合成缺失 heading + 重复锚点警告（R2 方案 A）

**Files:**
- Modify: `src/doc_chunk/tree/builder.py`
- Modify: `src/doc_chunk/api.py`（`build_tree` 写 manifest warnings）
- Test: `tests/unit/test_document_tree.py`

- [ ] **Step 1: Write the failing test**

```python
def test_synthesize_heading_when_anchor_on_image() -> None:
    blocks = ContentBlocksFile(
        blocks=[
            ContentBlockRecord(
                block_index=0, block_type="image", char_start=0, char_end=10, image_ref="images/cover.png"
            ),
            ContentBlockRecord(
                block_index=1, block_type="paragraph", char_start=10, char_end=30, text_preview="正文"
            ),
        ]
    )
    outline = OutlineTree(
        strategy="toc",
        nodes=[
            OutlineNode(
                node_id="n1", title="封面", level=1, parent_id=None, sort_order=0,
                anchor=Anchor(char_start=0, block_start=0),
            ),
        ],
    )
    tree = build_document_tree(blocks, outline, content_md="![](images/cover.png)\n\n正文\n\n")
    headings = [n for n in tree.nodes if n.node_type == "heading" and n.outline_node_id == "n1"]
    assert len(headings) == 1
    image_node = next(n for n in tree.nodes if n.node_type == "image")
    heading = headings[0]
    assert tree.nodes.index(heading) < tree.nodes.index(image_node)


def test_synthesized_headings_on_same_block_preserve_outline_order() -> None:
    """澄清 3：同 block_start 多个合成 heading 须保持 outline.sort_order 相对顺序。"""
    blocks = ContentBlocksFile(
        blocks=[
            ContentBlockRecord(
                block_index=0, block_type="image", char_start=0, char_end=10, image_ref="images/shared.png"
            ),
        ]
    )
    outline = OutlineTree(
        strategy="toc",
        nodes=[
            OutlineNode(
                node_id="n1", title="封面A", level=1, parent_id=None, sort_order=0,
                anchor=Anchor(char_start=0, block_start=0),
            ),
            OutlineNode(
                node_id="n2", title="封面B", level=1, parent_id=None, sort_order=1,
                anchor=Anchor(char_start=0, block_start=0),
            ),
        ],
    )
    tree = build_document_tree(blocks, outline, content_md="![](images/shared.png)\n\n")
    synth = [n for n in tree.nodes if n.node_type == "heading" and n.outline_node_id in {"n1", "n2"}]
    assert [n.outline_node_id for n in synth] == ["n1", "n2"]
    assert tree.nodes.index(synth[0]) < tree.nodes.index(synth[1])
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest tests/unit/test_document_tree.py::test_synthesize_heading_when_anchor_on_image -v
```

Expected: FAIL（无 heading）

- [ ] **Step 3: Implement `_synthesize_missing_headings`**

在 `tree/builder.py` 末尾、`return` 之前：

1. 收集已有 `outline_node_id` 的 heading 集合；
2. 对缺失的 outline 节点合成 heading（`flat_fallback` 单节点例外跳过）；
3. `parent_id` 从 `outline.parent_id` → 已生成 heading 的 `node_id` 映射；
4. 按 `source_block_index` 插入到**同 block 第一个非 heading body 之前**；
5. **同 block 多合成 heading 顺序（澄清 2 & 3）**：待合成节点按 `outline.sort_order` **升序**处理；插入同一 `source_block_index` 时，后插入的 heading 必须排在先插入者**之后**（保持 outline 相对先后顺序，避免重算 `sort_order` 后拓扑倒置）；
6. 新 heading 使用递增 `node_counter` 分配 `node_id`；
7. 全部插入完成后重算全体 `sort_order` 为 `0..len-1`；
8. 返回 `(tree, warnings: list[str])`，对重复 `block_start` 写 `outline_duplicate_anchor:{block_start}`。

`build_document_tree` 签名改为返回 `tuple[DocumentTreeFile, list[str]]` 或新增 `build_document_tree_with_warnings`——**推荐**在 `api.build_tree` 把 warnings 合并进 manifest。

- [ ] **Step 4: Wire warnings in `api.build_tree`**

```python
tree, tree_warnings = build_document_tree(...)  # 或单独函数收集 warnings
if tree_warnings and ws.manifest_path.exists():
    manifest = load_manifest(ws.manifest_path)
    for w in tree_warnings:
        if w not in manifest.warnings:
            manifest.warnings.append(w)
    save_manifest(ws, manifest)
```

- [ ] **Step 5: Run tests**

```bash
.venv/bin/python -m pytest tests/unit/test_document_tree.py -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/doc_chunk/tree/builder.py src/doc_chunk/api.py tests/unit/test_document_tree.py
git commit -m "fix(tree): synthesize missing headings for non-paragraph outline anchors"
```

---

## Task 4: linkage 全覆盖 + manifest 警告（R3）

**Files:**
- Modify: `src/doc_chunk/linkage/builder.py`
- Modify: `src/doc_chunk/api.py`
- Test: `tests/unit/test_linkage_builder.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_linkage_entry_for_outline_without_chunk() -> None:
    outline = OutlineTree(
        nodes=[
            OutlineNode(node_id="n1", title="A", level=1, parent_id=None, sort_order=0),
            OutlineNode(node_id="n2", title="B", level=1, parent_id=None, sort_order=1),
        ]
    )
    tree = DocumentTreeFile(
        nodes=[
            DocumentTreeNode(
                node_id="t0001", parent_id=None, outline_node_id="n1",
                node_type="heading", title="A", level=1, sort_order=0, source_block_index=0,
            ),
            DocumentTreeNode(
                node_id="t0002", parent_id=None, outline_node_id="n2",
                node_type="heading", title="B", level=1, sort_order=1, source_block_index=1,
            ),
        ]
    )
    chunks = [
        ContentChunk(chunk_id="chunk-0001", title="A", original_node_ids=["n1"], heading_level=1),
    ]
    linkage = build_linkage(outline, tree, chunks, outline_source="original")
    assert len(linkage.entries) == 2
    n2 = next(e for e in linkage.entries if e.outline_node_id == "n2")
    assert n2.chunk_ids == []
    assert n2.primary_chunk_id is None
    assert n2.document_tree_node_ids == ["t0002"]


def test_linkage_collects_missing_tree_warnings() -> None:
    outline = OutlineTree(
        nodes=[OutlineNode(node_id="n1", title="A", level=1, parent_id=None, sort_order=0)]
    )
    tree = DocumentTreeFile(nodes=[])
    linkage, warnings = build_linkage(outline, tree, [], outline_source="original", collect_warnings=True)
    assert linkage.entries[0].document_tree_node_ids == []
    assert any("linkage_missing_tree_node:n1" in w for w in warnings)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/unit/test_linkage_builder.py -v
```

- [ ] **Step 3: Refactor `build_linkage`**

```python
def build_linkage(
    outline: OutlineTree,
    document_tree: DocumentTreeFile,
    chunks: list[ContentChunk],
    *,
    outline_source: str = "original",
    collect_warnings: bool = False,
) -> LinkageFile | tuple[LinkageFile, list[str]]:
    ...
    for node in outline.nodes:
        if is_flat_fallback_exempt(outline):
            # 单节点例外：允许空 tree ids
            ...
        node_chunks = chunks_by_outline.get(node.node_id, [])
        tree_ids = tree_by_outline.get(node.node_id, [])
        if not tree_ids and collect_warnings:
            warnings.append(f"linkage_missing_tree_node:{node.node_id}")
        entries.append(LinkageEntry(
            outline_node_id=node.node_id,
            document_tree_node_ids=tree_ids,
            chunk_ids=[c.chunk_id for c in node_chunks],
            primary_chunk_id=primary.chunk_id if node_chunks else None,
        ))
```

更新既有测试 `document_tree_node_ids == ["t1"]` 为 `["t0001"]` 若 node_id 格式统一为四位。

- [ ] **Step 4: `_write_linkage` 合并 warnings 到 manifest**

- [ ] **Step 5: Run tests**

```bash
.venv/bin/python -m pytest tests/unit/test_linkage_builder.py -v
```

- [ ] **Step 6: Commit**

```bash
git add src/doc_chunk/linkage/builder.py src/doc_chunk/api.py tests/unit/test_linkage_builder.py
git commit -m "feat(linkage): full outline coverage with optional manifest warnings"
```

---

## Task 5: chunks/index.json 写入 document_tree_node_id（R3）

**Files:**
- Modify: `src/doc_chunk/api.py`
- Test: `tests/unit/test_chunk_index_tree_node.py`（新建）

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_chunk_index_tree_node.py
from doc_chunk.api import _populate_chunk_index_tree_nodes  # 或公开辅助函数


def test_populate_document_tree_node_id_from_linkage() -> None:
    index = ChunkIndex(
        chunks=[
            ChunkIndexEntry(
                chunk_id="chunk-0001", title="A", heading_level=1,
                original_node_ids=["n1"], path="chunk-0001.json",
            ),
        ]
    )
    linkage = LinkageFile(
        entries=[
            LinkageEntry(outline_node_id="n1", document_tree_node_ids=["t0003"], chunk_ids=["chunk-0001"]),
        ]
    )
    warnings = _populate_chunk_index_tree_nodes(index, linkage)
    assert index.chunks[0].document_tree_node_id == "t0003"
    assert warnings == []


def test_populate_emits_mismatch_warning() -> None:
    index = ChunkIndex(
        chunks=[
            ChunkIndexEntry(
                chunk_id="chunk-0001", title="A", heading_level=1,
                original_node_ids=["n1"], path="chunk-0001.json",
                document_tree_node_id="t0001",
            ),
        ]
    )
    linkage = LinkageFile(
        entries=[
            LinkageEntry(outline_node_id="n1", document_tree_node_ids=["t0003"], chunk_ids=["chunk-0001"]),
        ]
    )
    warnings = _populate_chunk_index_tree_nodes(index, linkage)
    assert warnings == ["chunk_tree_node_mismatch:chunk-0001"]
    assert index.chunks[0].document_tree_node_id == "t0003"
```

- [ ] **Step 2: Run test to verify it fails**

- [ ] **Step 3: Implement `_populate_chunk_index_tree_nodes` + `chunk_document` 管道**

> **Pydantic v2 Mutation Guard：** `ChunkIndexEntry` 若配置 `frozen=True`，禁止 `entry.document_tree_node_id = expected` 原地赋值。首选 `model_copy(update=...)` 替换列表项，或确认模型 `model_config` 允许可变后再赋值。

```python
def _populate_chunk_index_tree_nodes(index: ChunkIndex, linkage: LinkageFile) -> list[str]:
    warnings: list[str] = []
    by_outline = {e.outline_node_id: e for e in linkage.entries}
    updated: list[ChunkIndexEntry] = []
    for entry in index.chunks:
        if entry.heading_level is None:
            updated.append(entry)
            continue
        outline_id = entry.primary_outline_node_id or (
            entry.original_node_ids[0] if entry.original_node_ids else None
        )
        if not outline_id:
            updated.append(entry)
            continue
        link = by_outline.get(outline_id)
        if not link or not link.document_tree_node_ids:
            updated.append(entry)
            continue
        expected = link.document_tree_node_ids[0]
        if entry.document_tree_node_id and entry.document_tree_node_id != expected:
            warnings.append(f"chunk_tree_node_mismatch:{entry.chunk_id}")
        updated.append(entry.model_copy(update={"document_tree_node_id": expected}))
    index.chunks = updated
    return warnings
```

在 `chunk_document` 中，`_write_linkage` 之后、写 manifest 之前：

```python
linkage = LinkageFile.model_validate_json(ws.linkage_path.read_text(encoding="utf-8"))
index_warnings = _populate_chunk_index_tree_nodes(index, linkage)
(chunks_dir / "index.json").write_text(
    json.dumps(index.model_dump(mode="json"), ensure_ascii=False, indent=2),
    encoding="utf-8",
)
if index_warnings and ws.manifest_path.exists():
    manifest = load_manifest(ws.manifest_path)
    for w in index_warnings:
        if w not in manifest.warnings:
            manifest.warnings.append(w)
    save_manifest(ws, manifest)
```

确保 `chunk_tree_node_mismatch:*` 沉淀到物理 `manifest.json`，不在内存中静默丢失。

- [ ] **Step 4: Run test + contract**

```bash
.venv/bin/python -m pytest tests/unit/test_chunk_index_tree_node.py tests/contract/test_chunk_anchor_alignment.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/doc_chunk/api.py tests/unit/test_chunk_index_tree_node.py
git commit -m "feat(chunk): populate document_tree_node_id on index from linkage"
```

---

## Task 6: 双 fixture + 契约测试（R6）

**Files:**
- Create: `tests/fixtures/outline_anchor_on_image.docx`
- Create: `tests/fixtures/outline_anchor_on_table.docx`
- Create: `tests/contract/test_document_tree_outline_coverage.py`
- Modify: `tests/conftest.py` 或契约内 fixture 生成（参考 `test_chunk_anchor_alignment.py`）

- [ ] **Step 1: Add fixture generators**

`outline_anchor_on_image.docx`：插入图片段落 + TOC 域（或 `content_heuristic` 可识别的「封面」标题块在图片后）；outline 锚定在 block 0（image）。

`outline_anchor_on_table.docx`：首块 table，TOC 标题与 table 首行文本一致。

若 TOC 域生成复杂，可在测试中：`extract_file` → 手工 patch `outline.json` 将 `block_start` 设为 image/table index（契约测 tree/linkage，不测 TOC 解析器）。

- [ ] **Step 2: Write contract test**

```python
# tests/contract/test_document_tree_outline_coverage.py
import json
import pytest
from pathlib import Path
from doc_chunk.api import extract_file, extract_outline, build_tree, chunk_document

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

@pytest.mark.parametrize("docx_name", ["outline_anchor_on_image.docx", "outline_anchor_on_table.docx"])
def test_document_tree_covers_all_outline_nodes(tmp_path: Path, docx_name: str) -> None:
    src = FIXTURES / docx_name
    ws = tmp_path / docx_name.replace(".docx", "")
    extract_file(src, ws, overwrite=True)
    outline = extract_outline(ws)
    build_tree(ws)
    chunk_document(ws, use_refined=False)
    tree = json.loads((ws / "document_tree.json").read_text(encoding="utf-8"))
    outline_ids = {n["node_id"] for n in json.loads((ws / "outline.json").read_text())["nodes"]}
    heading_ids = {n["outline_node_id"] for n in tree["nodes"] if n["node_type"] == "heading" and n.get("outline_node_id")}
    node_ids = [n["node_id"] for n in tree["nodes"]]
    assert len(node_ids) == len(set(node_ids))
    assert heading_ids == outline_ids
    linkage = json.loads((ws / "linkage.json").read_text(encoding="utf-8"))
    assert len(linkage["entries"]) == len(outline_ids)
```

- [ ] **Step 3: Run contract tests**

```bash
.venv/bin/python -m pytest tests/contract/test_document_tree_outline_coverage.py -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/fixtures/ tests/contract/test_document_tree_outline_coverage.py
git commit -m "test(contract): document_tree outline coverage for image and table anchors"
```

---

## Task 7: blocks_v1 图片双字段映射（R4）

**Files:**
- Modify: `src/doc_chunk/convert/blocks_v1.py`
- Modify: `specs/001-document-extract-chunk/contracts/workspace-schemas.md`
- Test: `tests/unit/test_blocks_v1_convert.py`

- [ ] **Step 1: Write the failing test**

```python
def test_blocks_to_v1_json_image_with_asset_mapping() -> None:
    payload = blocks_to_v1_json(
        [ChunkBlock(type="image", image_ref="images/a.png")],
        image_ref_to_asset_id={"images/a.png": "uuid-123"},
    )
    block = json.loads(payload)["blocks"][0]
    assert block == {"type": "image", "asset_id": "uuid-123", "image_ref": "images/a.png"}


def test_blocks_to_v1_json_image_without_mapping() -> None:
    payload = blocks_to_v1_json([ChunkBlock(type="image", image_ref="images/a.png")])
    block = json.loads(payload)["blocks"][0]
    assert block == {"type": "image", "image_ref": "images/a.png"}
    assert "asset_id" not in block
```

- [ ] **Step 2: Run test to verify it fails**

- [ ] **Step 3: Implement**

```python
def _block_to_v1_dict(block: ChunkBlock, image_ref_to_asset_id: dict[str, str] | None) -> dict:
    data = block.model_dump(mode="json", exclude_none=True)
    if block.type == "image" and block.image_ref and image_ref_to_asset_id:
        asset_id = image_ref_to_asset_id.get(block.image_ref)
        if asset_id:
            data["asset_id"] = asset_id
    return data
```

- [ ] **Step 4: Update workspace-schemas.md**（blocks_v1 双字段说明 + 推荐适配层注入映射）

- [ ] **Step 5: Run tests**

```bash
.venv/bin/python -m pytest tests/unit/test_blocks_v1_convert.py -v
```

- [ ] **Step 6: Commit**

```bash
git add src/doc_chunk/convert/blocks_v1.py specs/001-document-extract-chunk/contracts/workspace-schemas.md tests/unit/test_blocks_v1_convert.py
git commit -m "feat(convert): blocks_v1 image asset_id mapping with image_ref traceability"
```

---

## Task 8: enrich 候选类型默认 + 直映射 + ignore（R5）

> Task 5.1–5.2 [Partially Completed in 002 / 003 Refactored]：`candidate_rules.yaml` 与 `suggest_candidate_types()` 已存在；本 Task 扩展行为。

**Files:**
- Modify: `src/doc_chunk/metadata/default_classification.yaml`
- Modify: `src/doc_chunk/metadata/candidate_rules.yaml`
- Modify: `src/doc_chunk/metadata/classify.py`
- Test: `tests/unit/test_candidate_type_hints.py`（已有）、`tests/unit/test_classify_suggested_direct.py`（新建）

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_classify_suggested_direct.py
def test_keyword_rule_maps_suggested_candidate_type_without_taxonomy_hints() -> None:
    result = classify_chunk(title="技术方案", markdown="本章描述系统架构", llm_client=None)
    assert result.get("suggested_candidate_type") == "scheme"


def test_ignore_rule_sets_null_knowledge_type() -> None:
    result = classify_chunk(title="目录", markdown="........", llm_client=None)
    assert result.get("suggested_candidate_type") == "ignore"
    assert result.get("suggested_knowledge_type") is None
```

- [ ] **Step 2: Extend `default_classification.yaml`**

追加 `chapter_taxonomies`（技术方案/产品能力/资质证明/服务方案等通用 aliases）。

- [ ] **Step 3: Add ignore rule to `candidate_rules.yaml`**

```yaml
  - taxonomy_hints: ["目录", "封面"]
    suggested_candidate_type: ignore
    suggested_knowledge_type: null
```

- [ ] **Step 4: Direct mapping in `classify.py`**

在 `_match_rule` 命中后，若 `label in {"scheme","product","qualification"}`，直接设置 `suggested_candidate_type` / `suggested_knowledge_type`（在 `_attach_candidate_suggestions` 之前或之内，taxonomy 可覆盖）。

- [ ] **Step 5: Run tests**

```bash
.venv/bin/python -m pytest tests/unit/test_candidate_type_hints.py tests/unit/test_classify_suggested_direct.py -v
```

- [ ] **Step 6: Commit**

```bash
git add src/doc_chunk/metadata/ tests/unit/test_classify_suggested_direct.py
git commit -m "feat(enrich): default taxonomy hints and direct suggested_candidate_type mapping"
```

---

## Task 9: 餐补可选回归 + NF1 耗时（R7, NF1）

**Files:**
- Create: `tests/integration/test_canbu_regression.py`
- Modify: `README.md`

- [ ] **Step 1: Write integration test**

```python
import os
import time
import json
import statistics
import pytest
from pathlib import Path
from doc_chunk.api import run_pipeline

CANBU = os.environ.get("DOC_CHUNK_CANBU_FIXTURE")
T_BASE = os.environ.get("DOC_CHUNK_CANBU_T_BASE")  # 秒，main 分支 3 次中位数


@pytest.mark.skipif(not CANBU, reason="set DOC_CHUNK_CANBU_FIXTURE to run canbu regression")
def test_canbu_document_tree_and_linkage_invariants(tmp_path: Path) -> None:
    src = Path(CANBU)
    ws = tmp_path / "canbu"
    run_pipeline(src, ws, overwrite=True, skip_enrich=True)
    outline = json.loads((ws / "outline.json").read_text())["nodes"]
    tree = json.loads((ws / "document_tree.json").read_text())["nodes"]
    linkage = json.loads((ws / "linkage.json").read_text())["entries"]
    ids = [n["node_id"] for n in tree]
    assert len(ids) == len(set(ids))
    heading_outline = {n["outline_node_id"] for n in tree if n["node_type"] == "heading" and n.get("outline_node_id")}
    assert heading_outline == {n["node_id"] for n in outline}
    assert len(linkage) == len(outline)
    assert all(e["document_tree_node_ids"] for e in linkage)


@pytest.mark.skipif(not CANBU or not T_BASE, reason="needs DOC_CHUNK_CANBU_FIXTURE and DOC_CHUNK_CANBU_T_BASE")
def test_canbu_pipeline_wall_time_within_budget(tmp_path: Path) -> None:
    src = Path(CANBU)
    times: list[float] = []
    for i in range(3):
        ws = tmp_path / f"canbu-{i}"
        start = time.perf_counter()
        run_pipeline(src, ws, overwrite=True, skip_enrich=True)
        times.append(time.perf_counter() - start)
    t_003 = statistics.median(times)
    t_base = float(T_BASE)
    ratio = t_003 / t_base
    print(f"NF1 canbu timing: T_base={t_base:.1f}s T_003={t_003:.1f}s ratio={ratio:.2f}")
    assert t_003 <= 1.2 * t_base
```

- [ ] **Step 2: Document in README**

```bash
# 餐补回归（可选）
export DOC_CHUNK_CANBU_FIXTURE=/path/to/canbu.docx
export DOC_CHUNK_CANBU_T_BASE=120  # main 分支 3 次 pipeline 中位数（秒）
.venv/bin/python -m pytest tests/integration/test_canbu_regression.py -v -s
```

- [ ] **Step 3: Run default CI suite（不含 canbu）**

```bash
.venv/bin/python -m pytest tests/unit tests/contract -q
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_canbu_regression.py README.md
git commit -m "test(integration): optional canbu regression and NF1 wall-time gate"
```

---

## Task 10: 文档收尾 + Plan Sync（验收 6–9）

**Files:**
- Modify: `README.md`（索引 003 spec、标注集成修复已完成）
- Modify: 本 plan 文件（完成后勾选 Task checkbox）
- Modify: `docs/superpowers/specs/2026-06-15-doc-chunk-tk-integration-fixes.md` 状态 → 已实现（PR 合并时）

- [ ] **Step 1: README 添加 003 spec 链接**（若 Task 9 未覆盖）

- [ ] **Step 2: 全量测试**

```bash
.venv/bin/python -m pytest tests/unit tests/contract tests/integration -q --ignore=tests/integration/test_canbu_regression.py
# 或显式 skip canbu
```

- [ ] **Step 3: PR 说明模板**

```markdown
## NF1 性能
- T_base: ___s（main, 3-run median）
- T_003: ___s（003 branch, 3-run median）
- Ratio: ___

## 验收
- [ ] document_tree 0 duplicate node_id（餐补）
- [ ] linkage len == outline len
- [ ] contract test_document_tree_outline_coverage 双 fixture
```

- [ ] **Step 4: Commit**

```bash
git add README.md docs/superpowers/plans/2026-06-15-doc-chunk-tk-integration-fixes.md
git commit -m "docs: finalize 003 integration fixes plan sync and README index"
```

---

## 建议执行顺序

```text
Task 1 (R1)
  → Task 2 (R2B)
  → Task 3 (R2A)
  → Task 4 (R3 linkage)
  → Task 5 (R3 index)
  → Task 6 (R6 contract)
  —— P0 完成，可启动 tk doc_chunk_import_service ——
  → Task 7 (R4)
  → Task 8 (R5)
  → Task 9 (R7 + NF1)
  → Task 10 (docs)
```

**P0 合并门禁：** Task 1–6 全部通过 + `pytest tests/unit tests/contract -q` 全绿。

---

## Spec Coverage Self-Review

| 需求 | Task |
|------|------|
| R1 node_id 唯一 | Task 1 |
| R2 方案 A+B | Task 2, 3 |
| R2 重复 block_start 警告 + 同 block 合成顺序 | Task 3 |
| R2 flat_fallback 例外 | Task 3, 4 (`is_flat_fallback_exempt`) |
| R3 linkage 全覆盖 | Task 4 |
| R3 index document_tree_node_id + manifest 合流 | Task 5 |
| R4 blocks_v1 双字段 | Task 7 |
| R5 默认 taxonomy + 直映射 + ignore | Task 8 |
| R6 双 fixture | Task 6 |
| R7 餐补回归 | Task 9 |
| NF1 耗时 | Task 9 |
| NF3 单测/契约全绿 | 各 Task + Task 10 |
| Plan Sync | Task 10, 本文件标注 |
| README 索引 | Task 9–10 |

**Placeholder scan:** 无 TBD；fixture 若 TOC 复杂允许 patch outline（已在 Task 6 说明）。

**类型一致性:** `build_linkage` 增加 `collect_warnings` 可选参数，不破坏现有三参数调用；`build_document_tree` warnings 通过 api 层合并，避免破坏仅返回 `DocumentTreeFile` 的对外约定时可新增 `build_document_tree_result` 命名。`_populate_chunk_index_tree_nodes` 使用 `ChunkIndexEntry.model_copy(update=...)` 以兼容 Pydantic v2 `frozen` 配置。
