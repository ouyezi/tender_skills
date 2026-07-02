# Outline Anchor 与 Viewer Section 对齐 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

> **需求来源**: [`specs/2026-07-02-anchor-viewer-alignment.md`](../specs/2026-07-02-anchor-viewer-alignment.md)（v1.0）

**Goal:** 使 `outline.json` 中每个节点的 `anchor.char_start` 与 viewer `slice_section()` 对同 session 同 `node_id` 返回的 `char_start` 完全一致，并跳过文首内嵌目录区。

**Architecture:** 从 `viewer/viewer/services/section_slice.py` 抽出标题定位逻辑到 `src/doc_chunk/locate/heading_starts.py` 作为单一真相源；viewer 与 `anchor_enricher` 均调用该模块。enricher 保留 image/table 锚点迁移，但 `char_start` 以 `build_node_heading_starts` 结果为准。

**Tech Stack:** Python 3.11+、`doc_chunk` 包、pytest、Pydantic v2、`doc_chunk.extract.promote_headings.is_toc_entry_line`

---

## File Map

| 文件 | 职责 | 操作 |
|------|------|------|
| `src/doc_chunk/locate/__init__.py` | 包入口 | Create |
| `src/doc_chunk/locate/heading_starts.py` | 共享标题解析、normalize、贪心匹配、section 范围 | Create |
| `viewer/viewer/services/section_slice.py` | viewer 切片；改为调用共享模块 | Modify |
| `src/doc_chunk/outline/anchor_enricher.py` | anchor 填充；改用 heading_starts | Modify |
| `tests/unit/test_heading_starts_shared.py` | 共享模块单测 + viewer 一致性 | Create |
| `tests/unit/test_anchor_enricher_toc_bid.py` | TOC 标书场景 enricher 单测 | Create |
| `tests/unit/test_anchor_enricher.py` | 现有 image/table 迁移回归 | 不变，须全绿 |
| `viewer/tests/unit/test_section_slice.py` | viewer 切片回归 | 不变，须全绿 |
| `docs/CHANGELOG.md` | 破坏性变更说明 | Create |
| `pyproject.toml` | minor version bump `0.1.0` → `0.2.0` | Modify |

---

### Task 1: 创建 `doc_chunk/locate/heading_starts.py` 核心模块

**Files:**
- Create: `src/doc_chunk/locate/__init__.py`
- Create: `src/doc_chunk/locate/heading_starts.py`
- Test: `tests/unit/test_heading_starts_shared.py`

- [ ] **Step 1: Write the failing test**

创建 `tests/unit/test_heading_starts_shared.py`：

```python
from __future__ import annotations

from doc_chunk.locate.heading_starts import (
    build_node_heading_starts,
    fallback_char_start,
    normalize_outline_title,
    parse_body_headings,
    section_char_range,
)
from doc_chunk.models.outline import Anchor, OutlineNode, OutlineTree

TOC_BID_CONTENT_MD = (
    "2025年生日福利预算\n\n投标/响应文件\n\n"
    "# 投标函\t1\n"
    "# 合同条款偏离表\t12\n"
    "## 服务偏离表\t3\n"
    "# 服务偏离表\n\n"
    "服务偏离概述\n\n"
    "### 2.1合同条款偏离表\n\n"
    "| 序号 | 条款 |\n|---|---|\n| 1 | foo |\n\n"
    "### 2.2技术条款偏离表\n\n"
    "技术偏离正文\n"
)


def _toc_bid_tree() -> OutlineTree:
    return OutlineTree(
        strategy="toc",
        nodes=[
            OutlineNode(
                node_id="n1",
                title="投标函11",
                level=1,
                parent_id=None,
                sort_order=0,
                anchor=Anchor(block_index=0),
            ),
            OutlineNode(
                node_id="n2",
                title="2.1合同条款偏离表12",
                level=3,
                parent_id="n1",
                sort_order=1,
                anchor=Anchor(block_index=1),
            ),
            OutlineNode(
                node_id="n3",
                title="2.2技术条款偏离表",
                level=3,
                parent_id="n1",
                sort_order=2,
                anchor=Anchor(block_index=2),
            ),
        ],
    )


def test_parse_body_headings_skips_toc_entries() -> None:
    headings = parse_body_headings(TOC_BID_CONTENT_MD)
    titles = [h.title for h in headings]
    assert "投标函\t1" not in titles
    assert "合同条款偏离表\t12" not in titles
    assert "2.1合同条款偏离表" in titles


def test_normalize_outline_title_strips_glue_page_and_prefix() -> None:
    assert normalize_outline_title("2.1合同条款偏离表12") == normalize_outline_title("2.1合同条款偏离表")
    assert normalize_outline_title("1投标函11") == normalize_outline_title("投标函")


def test_build_node_heading_starts_skips_toc_for_section_2_1() -> None:
    tree = _toc_bid_tree()
    starts = build_node_heading_starts(tree, TOC_BID_CONTENT_MD, use_existing_anchor_fallback=False)
    body_headings = parse_body_headings(TOC_BID_CONTENT_MD)
    first_body = min(h.char_start for h in body_headings)
    assert starts["n2"] >= first_body
    assert "2.1合同条款偏离表" in TOC_BID_CONTENT_MD[starts["n2"] : starts["n2"] + 40]


def test_section_char_range_parent_includes_child_body() -> None:
    tree = _toc_bid_tree()
    start, end = section_char_range(tree, TOC_BID_CONTENT_MD, "n1")
    section_md = TOC_BID_CONTENT_MD[start:end]
    assert "2.1合同条款偏离表" in section_md


def test_fallback_char_start_finds_first_body_match() -> None:
    pos = fallback_char_start(TOC_BID_CONTENT_MD, "2.1合同条款偏离表12", level=3)
    assert pos is not None
    assert TOC_BID_CONTENT_MD[pos : pos + 20].startswith("### 2.1")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/tongqianni/xlab/tender_skills
.venv/bin/python -m pytest tests/unit/test_heading_starts_shared.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'doc_chunk.locate'`

- [ ] **Step 3: Create package and implement heading_starts**

创建 `src/doc_chunk/locate/__init__.py`：

```python
"""Shared content.md location helpers for outline anchors and viewer slicing."""
```

创建 `src/doc_chunk/locate/heading_starts.py`（从 `section_slice.py` 迁移并增强 normalize）：

```python
from __future__ import annotations

import re
from dataclasses import dataclass

from doc_chunk.extract.promote_headings import is_toc_entry_line
from doc_chunk.models.outline import OutlineNode, OutlineTree

_HEADING_RE = re.compile(r"^(#{1,8})[ \t]+(.+?)[ \t#]*$", re.MULTILINE)
_NUM_PREFIX_RE = re.compile(r"^(\d+(?:\.\d+)*[\s、.．]+)")
_CN_ENUM_PREFIX_RE = re.compile(r"^[一二三四五六七八九十百零]+、[ \t]*")
_TOC_PAGE_SUFFIX_RE = re.compile(r"[\t]\d+\s*$")
_GLUED_PAGE_RE = re.compile(r"^(?P<title>.+?\D)(?P<page>\d{1,3})$")


@dataclass(frozen=True, slots=True)
class Heading:
    char_start: int
    level: int
    title: str


def normalize_outline_title(text: str) -> str:
    stripped = _TOC_PAGE_SUFFIX_RE.sub("", text.strip())
    glued = _GLUED_PAGE_RE.match(stripped)
    if glued is not None:
        stripped = glued.group("title")
    stripped = _CN_ENUM_PREFIX_RE.sub("", stripped)
    stripped = _NUM_PREFIX_RE.sub("", stripped)
    return stripped.strip().lower()


def parse_body_headings(content_md: str) -> list[Heading]:
    headings: list[Heading] = []
    for match in _HEADING_RE.finditer(content_md):
        title = match.group(2).strip()
        if is_toc_entry_line(title):
            continue
        headings.append(
            Heading(
                char_start=match.start(),
                level=len(match.group(1)),
                title=title,
            )
        )
    return headings


def _titles_match(node: OutlineNode, heading: Heading) -> bool:
    return node.level == heading.level and normalize_outline_title(node.title) == normalize_outline_title(
        heading.title
    )


def fallback_char_start(content_md: str, title: str, *, level: int | None = None) -> int | None:
    for heading in parse_body_headings(content_md):
        if level is not None and heading.level != level:
            continue
        if normalize_outline_title(heading.title) == normalize_outline_title(title):
            return heading.char_start
    return None


def build_node_heading_starts(
    outline_tree: OutlineTree,
    content_md: str,
    *,
    use_existing_anchor_fallback: bool = True,
) -> dict[str, int]:
    headings = parse_body_headings(content_md)
    nodes = sorted(outline_tree.nodes, key=lambda n: (n.sort_order, n.node_id))
    mapping: dict[str, int] = {}
    heading_idx = 0

    for node in nodes:
        matched = False
        while heading_idx < len(headings):
            heading = headings[heading_idx]
            if _titles_match(node, heading):
                mapping[node.node_id] = heading.char_start
                heading_idx += 1
                matched = True
                break
            heading_idx += 1
        if matched:
            continue

        fb = fallback_char_start(content_md, node.title, level=node.level)
        if fb is None and use_existing_anchor_fallback and node.anchor.char_start is not None:
            fb = node.anchor.char_start
        if fb is not None:
            mapping[node.node_id] = fb

    return mapping


def section_end_by_heading(content_md: str, start: int, level: int) -> int:
    for match in _HEADING_RE.finditer(content_md):
        if match.start() <= start:
            continue
        if len(match.group(1)) <= level:
            return match.start()
    return len(content_md)


def section_char_range(tree: OutlineTree, content_md: str, node_id: str) -> tuple[int, int]:
    node_map = {n.node_id: n for n in tree.nodes}
    node = node_map.get(node_id)
    if node is None:
        raise KeyError(node_id)

    heading_starts = build_node_heading_starts(tree, content_md)
    start = heading_starts.get(node_id)
    if start is None:
        start = fallback_char_start(content_md, node.title, level=node.level) or 0
    end = section_end_by_heading(content_md, start, node.level)
    return start, end
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python -m pytest tests/unit/test_heading_starts_shared.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/doc_chunk/locate/__init__.py src/doc_chunk/locate/heading_starts.py tests/unit/test_heading_starts_shared.py
git commit -m "feat: add shared heading_starts module for anchor/viewer alignment"
```

---

### Task 2: Viewer `section_slice.py` 切换到共享模块

**Files:**
- Modify: `viewer/viewer/services/section_slice.py`
- Test: `viewer/tests/unit/test_section_slice.py`
- Test: `viewer/tests/unit/test_asset_navigation.py`

- [ ] **Step 1: Run viewer baseline tests (must pass before refactor)**

```bash
.venv/bin/python -m pytest viewer/tests/unit/test_section_slice.py viewer/tests/unit/test_asset_navigation.py -v
```

Expected: PASS

- [ ] **Step 2: Refactor section_slice to import shared module**

将 `viewer/viewer/services/section_slice.py` 替换为：

```python
from __future__ import annotations

from dataclasses import dataclass

from doc_chunk.locate.heading_starts import (
    build_node_heading_starts,
    fallback_char_start,
    parse_body_headings,
    section_end_by_heading,
)
from doc_chunk.models.outline import OutlineNode, OutlineTree

from viewer.models import SectionResponse
from viewer.services.outline_tree import PREFACE_NODE_ID


@dataclass(frozen=True, slots=True)
class SectionCharRange:
    node_id: str
    char_start: int
    char_end: int


def _build_section_path(node: OutlineNode, node_map: dict[str, OutlineNode]) -> list[str]:
    chain: list[str] = []
    cursor: OutlineNode | None = node
    seen: set[str] = set()
    while cursor and cursor.node_id not in seen:
        seen.add(cursor.node_id)
        chain.append(cursor.title)
        cursor = node_map.get(cursor.parent_id) if cursor.parent_id else None
    return list(reversed(chain))


def _preface_end(content_md: str, heading_starts: dict[str, int]) -> int:
    headings = parse_body_headings(content_md)
    if headings:
        return headings[0].char_start
    if heading_starts:
        return min(heading_starts.values())
    return 0


def build_section_char_ranges(content_md: str, outline_tree: OutlineTree) -> list[SectionCharRange]:
    heading_starts = build_node_heading_starts(outline_tree, content_md)
    preface_end = _preface_end(content_md, heading_starts)
    ranges: list[SectionCharRange] = [
        SectionCharRange(PREFACE_NODE_ID, 0, preface_end),
    ]
    for node in outline_tree.nodes:
        start = heading_starts.get(node.node_id)
        if start is None:
            start = fallback_char_start(content_md, node.title, level=node.level) or 0
        end = section_end_by_heading(content_md, start, node.level)
        ranges.append(SectionCharRange(node.node_id, start, end))
    return ranges


def slice_section(content_md: str, outline_tree: OutlineTree, node_id: str) -> SectionResponse:
    heading_starts = build_node_heading_starts(outline_tree, content_md)
    node_map = {n.node_id: n for n in outline_tree.nodes}

    if node_id == PREFACE_NODE_ID:
        end = _preface_end(content_md, heading_starts)
        return SectionResponse(
            node_id=PREFACE_NODE_ID,
            title="前言",
            level=0,
            section_path=[],
            needs_review=False,
            char_start=0,
            char_end=end,
            markdown=content_md[:end],
        )

    node = node_map.get(node_id)
    if node is None:
        raise KeyError(node_id)

    start = heading_starts.get(node_id)
    if start is None:
        start = fallback_char_start(content_md, node.title, level=node.level) or 0

    end = section_end_by_heading(content_md, start, node.level)
    return SectionResponse(
        node_id=node.node_id,
        title=node.title,
        level=node.level,
        section_path=_build_section_path(node, node_map),
        needs_review=node.needs_review,
        char_start=start,
        char_end=end,
        markdown=content_md[start:end],
    )
```

- [ ] **Step 3: Run viewer regression tests**

```bash
.venv/bin/python -m pytest viewer/tests/unit/test_section_slice.py viewer/tests/unit/test_asset_navigation.py tests/unit/test_toc_entry_promote_headings.py -v
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add viewer/viewer/services/section_slice.py
git commit -m "refactor: viewer section_slice uses shared heading_starts"
```

---

### Task 3: `anchor_enricher.py` 写入 heading_starts 结果

**Files:**
- Modify: `src/doc_chunk/outline/anchor_enricher.py`
- Test: `tests/unit/test_anchor_enricher_toc_bid.py`（新建）
- Test: `tests/unit/test_anchor_enricher.py`（回归）

- [ ] **Step 1: Write failing TOC bid enricher tests**

创建 `tests/unit/test_anchor_enricher_toc_bid.py`：

```python
from __future__ import annotations

from doc_chunk.locate.heading_starts import parse_body_headings
from doc_chunk.models.content_block import ContentBlockRecord, ContentBlocksFile
from doc_chunk.models.outline import Anchor, OutlineNode, OutlineTree
from doc_chunk.outline.anchor_enricher import enrich_outline_anchors
from tests.unit.test_heading_starts_shared import TOC_BID_CONTENT_MD, _toc_bid_tree
from viewer.services.section_slice import slice_section


def _toc_bid_blocks(content_md: str) -> ContentBlocksFile:
    blocks: list[ContentBlockRecord] = []
    offset = 0
    for block_index, line in enumerate(content_md.splitlines(keepends=True)):
        start = offset
        end = start + len(line)
        offset = end
        block_type = "heading" if line.lstrip().startswith("#") else "paragraph"
        blocks.append(
            ContentBlockRecord(
                block_index=block_index,
                block_type=block_type,
                char_start=start,
                char_end=end,
                text_preview=line.strip() or None,
            )
        )
    return ContentBlocksFile(blocks=blocks)


def test_enrich_skips_toc_for_section_2_1() -> None:
    tree = _toc_bid_tree()
    blocks = _toc_bid_blocks(TOC_BID_CONTENT_MD)
    enriched = enrich_outline_anchors(tree, blocks, content_md=TOC_BID_CONTENT_MD)
    node = next(n for n in enriched.nodes if n.node_id == "n2")
    first_body = min(h.char_start for h in parse_body_headings(TOC_BID_CONTENT_MD))
    assert node.anchor.char_start is not None
    assert node.anchor.char_start >= first_body
    assert "2.1合同条款偏离表" in TOC_BID_CONTENT_MD[node.anchor.char_start : node.anchor.char_start + 40]


def test_enrich_char_start_matches_viewer() -> None:
    tree = _toc_bid_tree()
    blocks = _toc_bid_blocks(TOC_BID_CONTENT_MD)
    enriched = enrich_outline_anchors(tree, blocks, content_md=TOC_BID_CONTENT_MD)
    for node in enriched.nodes:
        section = slice_section(TOC_BID_CONTENT_MD, enriched, node.node_id)
        assert node.anchor.char_start == section.char_start, node.node_id


def test_enrich_does_not_use_fuzzy_first_match_in_toc() -> None:
    tree = _toc_bid_tree()
    blocks = _toc_bid_blocks(TOC_BID_CONTENT_MD)
    enriched = enrich_outline_anchors(tree, blocks, content_md=TOC_BID_CONTENT_MD)
    toc_end = TOC_BID_CONTENT_MD.index("# 服务偏离表\n\n")
    for node in enriched.nodes:
        if node.anchor.char_start is None:
            continue
        assert node.anchor.char_start >= toc_end or node.node_id == "n1"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest tests/unit/test_anchor_enricher_toc_bid.py -v
```

Expected: FAIL（当前 enricher 将 n2 锚在目录区 char≈60 附近）

- [ ] **Step 3: Implement anchor_enricher with heading_starts**

替换 `src/doc_chunk/outline/anchor_enricher.py`：

```python
from __future__ import annotations

import re

from doc_chunk.locate.heading_starts import build_node_heading_starts
from doc_chunk.models.content_block import ContentBlockRecord, ContentBlocksFile
from doc_chunk.models.outline import Anchor, OutlineNode, OutlineTree

_NUM_PREFIX_RE = re.compile(r"^(\d+(?:\.\d+)*[\s、.．]+)")


def _normalize_title(text: str) -> str:
    return _NUM_PREFIX_RE.sub("", text).strip().lower()


def _find_block_for_char_start(blocks: ContentBlocksFile, char_start: int) -> ContentBlockRecord | None:
    candidates = [b for b in blocks.blocks if b.char_start <= char_start < b.char_end]
    if not candidates:
        return None
    for block in candidates:
        if block.block_type == "heading":
            return block
    return candidates[0]


def _find_block_for_title(title: str, blocks: ContentBlocksFile, content_md: str) -> int | None:
    target = _normalize_title(title)
    for block in blocks.blocks:
        if block.block_type not in {"paragraph", "heading"}:
            continue
        preview = (block.text_preview or content_md[block.char_start : block.char_end]).strip()
        normalized = _normalize_title(preview)
        if normalized == target or target in normalized or normalized in target:
            return block.block_index
    return None


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


def enrich_outline_anchors(
    tree: OutlineTree,
    blocks: ContentBlocksFile,
    *,
    content_md: str,
) -> OutlineTree:
    block_by_index = {b.block_index: b for b in blocks.blocks}
    heading_starts = build_node_heading_starts(tree, content_md, use_existing_anchor_fallback=False)
    new_nodes: list[OutlineNode] = []

    for node in tree.nodes:
        anchor = node.anchor.model_copy()
        needs_review = node.needs_review
        idx: int | None = anchor.block_index

        if node.node_id in heading_starts:
            char_start = heading_starts[node.node_id]
            block = _find_block_for_char_start(blocks, char_start)
            if block is not None:
                idx = block.block_index
                anchor.char_start = block.char_start
                anchor.char_end = block.char_end
                anchor.block_index = idx
                anchor.block_start = idx
            else:
                anchor.char_start = char_start
                anchor.char_end = char_start
        else:
            if idx is None or idx not in block_by_index:
                idx = _find_block_for_title(node.title, blocks, content_md)
            elif idx in block_by_index:
                relocated = _relocate_non_paragraph_anchor(
                    node.model_copy(update={"anchor": anchor}),
                    blocks,
                    content_md,
                    all_nodes=tree.nodes,
                )
                if relocated is not None:
                    idx = relocated
            if idx is not None and idx in block_by_index:
                block = block_by_index[idx]
                anchor.block_index = idx
                anchor.block_start = idx
                anchor.char_start = block.char_start
                anchor.char_end = block.char_end
            else:
                anchor.char_start = None
                anchor.char_end = None
                needs_review = True

        if idx is not None and idx in block_by_index:
            block = block_by_index[idx]
            if block.block_type not in {"paragraph", "heading"}:
                relocated = _relocate_non_paragraph_anchor(
                    node.model_copy(update={"anchor": anchor}),
                    blocks,
                    content_md,
                    all_nodes=tree.nodes,
                )
                if relocated is not None and relocated in block_by_index:
                    block = block_by_index[relocated]
                    anchor.block_index = relocated
                    anchor.block_start = relocated
                    anchor.char_start = block.char_start
                    anchor.char_end = block.char_end

        new_nodes.append(node.model_copy(update={"anchor": anchor, "needs_review": needs_review}))

    return tree.model_copy(update={"nodes": new_nodes})
```

- [ ] **Step 4: Run enricher tests**

```bash
.venv/bin/python -m pytest tests/unit/test_anchor_enricher_toc_bid.py tests/unit/test_anchor_enricher.py -v
```

Expected: PASS（6 tests total）

- [ ] **Step 5: Commit**

```bash
git add src/doc_chunk/outline/anchor_enricher.py tests/unit/test_anchor_enricher_toc_bid.py
git commit -m "fix: align outline anchor char_start with viewer heading_starts"
```

---

### Task 4: 共享模块与 viewer 一致性断言

**Files:**
- Modify: `tests/unit/test_heading_starts_shared.py`

- [ ] **Step 1: Add viewer parity test**

在 `tests/unit/test_heading_starts_shared.py` 追加：

```python
from viewer.services.section_slice import slice_section


def test_build_node_heading_starts_matches_slice_section() -> None:
    tree = _toc_bid_tree()
    starts = build_node_heading_starts(tree, TOC_BID_CONTENT_MD)
    for node in tree.nodes:
        section = slice_section(TOC_BID_CONTENT_MD, tree, node.node_id)
        assert starts.get(node.node_id) == section.char_start, node.node_id
```

- [ ] **Step 2: Run test**

```bash
.venv/bin/python -m pytest tests/unit/test_heading_starts_shared.py::test_build_node_heading_starts_matches_slice_section -v
```

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_heading_starts_shared.py
git commit -m "test: assert heading_starts parity with viewer slice_section"
```

---

### Task 5: 全量回归 + Changelog

**Files:**
- Create: `docs/CHANGELOG.md`
- Modify: `pyproject.toml`（version `0.1.0` → `0.2.0`）

- [ ] **Step 1: Run full regression suite**

```bash
.venv/bin/python -m pytest \
  tests/unit/test_heading_starts_shared.py \
  tests/unit/test_anchor_enricher_toc_bid.py \
  tests/unit/test_anchor_enricher.py \
  viewer/tests/unit/test_section_slice.py \
  viewer/tests/unit/test_asset_navigation.py \
  tests/contract/test_chunk_anchor_alignment.py \
  -v
```

Expected: PASS

- [ ] **Step 2: Create CHANGELOG entry**

创建 `docs/CHANGELOG.md`：

```markdown
# Changelog

## [0.2.0] - 2026-07-02

### Changed (Breaking)

- **`outline.json` `anchor.char_start` 语义变更**：现与 viewer `GET /sections/{node_id}` 返回的 `char_start` 完全一致，跳过文首内嵌目录（`标题\t页码`）行。已解析文档需重新跑 doc-chunk 流水线；不自动回写历史 `outline.json`。
- 新增共享模块 `doc_chunk.locate.heading_starts`，viewer 与 `anchor_enricher` 共用标题定位逻辑。

### Fixed

- 修复 TOC 标书场景下 outline anchor 落在目录区、导致 tender_knowledge 章节预览 `content_md` 几乎为空的问题。
```

- [ ] **Step 3: Bump version in pyproject.toml**

```toml
version = "0.2.0"
```

- [ ] **Step 4: Commit**

```bash
git add docs/CHANGELOG.md pyproject.toml
git commit -m "chore: release 0.2.0 with anchor/viewer alignment breaking change"
```

---

### Task 6（可选）: 样例文档全量对比集成测试

**Files:**
- Create: `tests/integration/test_anchor_viewer_alignment_canbu.py`

仅当本地存在餐补样例 docx 时运行（与 `test_toc_entry_promote_headings.py` 相同 skip 模式）。

- [ ] **Step 1: Write optional integration test**

```python
from __future__ import annotations

from pathlib import Path

import pytest
from doc_chunk.api import extract_file, extract_outline
from doc_chunk.models.outline import OutlineTree
from viewer.services.section_slice import slice_section

CANBU_DOCX = Path.home() / (
    ".doc-chunk-viewer/uploads/61805407-9bde-4c4d-af88-f7dd91f1a661/【大纲】餐补标书大纲模板6.16.docx"
)


@pytest.mark.skipif(not CANBU_DOCX.exists(), reason="local tender sample docx not available")
def test_all_outline_anchors_match_viewer(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    extract_file(CANBU_DOCX, workspace, overwrite=True, promote_headings="auto")
    outline = extract_outline(workspace)
    content_md = (workspace / "content.md").read_text(encoding="utf-8")

    mismatches: list[str] = []
    for node in outline.nodes:
        section = slice_section(content_md, outline, node.node_id)
        if node.anchor.char_start != section.char_start:
            mismatches.append(
                f"{node.node_id} {node.title!r}: anchor={node.anchor.char_start} viewer={section.char_start}"
            )
    assert not mismatches, "\n".join(mismatches[:10])
```

- [ ] **Step 2: Run if fixture available**

```bash
.venv/bin/python -m pytest tests/integration/test_anchor_viewer_alignment_canbu.py -v
```

Expected: PASS or SKIPPED

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_anchor_viewer_alignment_canbu.py
git commit -m "test: optional canbu full outline anchor/viewer parity"
```

---

## Self-Review

### Spec coverage

| 需求 | 对应 Task |
|------|-----------|
| G1 anchor ≡ viewer char_start | Task 3 + Task 4 |
| G2 跳过 TOC 目录行 | Task 1 `parse_body_headings` + Task 3 |
| G3 单一真相源 | Task 1 + Task 2 |
| G4 image/table 迁移保留 | Task 3 `_relocate_non_paragraph_anchor` |
| G5 契约/单元测试 | Task 1, 3, 4, 5, 6 |
| §5.1 TOC bid enricher 测试 | Task 3 |
| §5.2 heading_starts 共享测试 | Task 1, 4 |
| §5.3 回归 | Task 5 |
| §7 Changelog + version | Task 5 |
| Out of scope: tender_knowledge 改动 | 无 Task |

### Placeholder scan

无 TBD / TODO / "implement later" / "Similar to Task N"。

### Type consistency

- `build_node_heading_starts(..., use_existing_anchor_fallback: bool)` — enricher 传 `False`，viewer 默认 `True`
- `Heading.char_start` / `anchor.char_start` / `SectionResponse.char_start` 均为 `int`
- `section_char_range` 返回 `tuple[int, int]` 与 viewer `char_start`/`char_end` 一致

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-02-anchor-viewer-alignment.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
