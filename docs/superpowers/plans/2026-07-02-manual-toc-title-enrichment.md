# Word TOC 字段 Outline 提取 Implementation Plan（numeric styleId）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

> **需求来源**: [`specs/2026-07-02-manual-toc-title-enrichment.md`](../specs/2026-07-02-manual-toc-title-enrichment.md)（v1.1 — Word TOC 字段，**非**文首手动目录）

**Goal:** 修复 `extract_docx_toc_outline`，使 pStyle 为数字 styleId（如 `16`/`17`，在 styles.xml 中命名为 `toc 1`/`toc 2`）的 Word TOC 字段文档能正确提取带序号的 outline。

**Architecture:** 从 docx 的 `word/styles.xml` 构建 `styleId → toc level` 映射，替换仅匹配字面量 `toc1` 的逻辑；保留原有 `_join_toc_text_parts` 与 `TOC` instrText 门禁。6.16 餐补模板将走 `strategy=toc` 而非 `heading_heuristic`。

**Tech Stack:** Python 3.11+、lxml、zipfile、pytest、python-docx（测试 fixture）

---

## File Map

| 文件 | 职责 | 操作 |
|------|------|------|
| `src/doc_chunk/outline/toc_docx.py` | TOC outline 提取 + styles 映射 | Modify |
| `tests/unit/test_toc_docx_titles.py` | 拼接与提取单测 | Modify |
| `tests/unit/test_toc_docx_style_map.py` | styles.xml 映射单测 | Create |
| `tests/integration/test_toc_docx_canbu.py` | 餐补 6.16 集成 | Create |

**不创建** `manual_toc.py`（v1.0 方案废弃）

---

### Task 1: `build_toc_style_level_map` + 单测

**Files:**
- Modify: `src/doc_chunk/outline/toc_docx.py`
- Create: `tests/unit/test_toc_docx_style_map.py`

- [ ] **Step 1: Write the failing test**

创建 `tests/unit/test_toc_docx_style_map.py`：

```python
from __future__ import annotations

from doc_chunk.outline.toc_docx import build_toc_style_level_map

SAMPLE_STYLES_XML = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:styleId="16">
    <w:name w:val="toc 1"/>
  </w:style>
  <w:style w:type="paragraph" w:styleId="17">
    <w:name w:val="toc 2"/>
  </w:style>
  <w:style w:type="paragraph" w:styleId="27">
    <w:name w:val="TOC 标题1"/>
  </w:style>
  <w:style w:type="paragraph" w:styleId="toc3">
    <w:name w:val="toc 3"/>
  </w:style>
</w:styles>
"""


def test_build_toc_style_level_map_numeric_style_ids() -> None:
    mapping = build_toc_style_level_map(SAMPLE_STYLES_XML)
    assert mapping["16"] == 1
    assert mapping["17"] == 2
    assert "27" not in mapping  # TOC 标题* 排除
    assert mapping["toc3"] == 3  # 字面量 styleId 也支持


def test_build_toc_style_level_map_empty_on_missing_styles() -> None:
    assert build_toc_style_level_map(b"<w:styles xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\"/>") == {}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/tongqianni/xlab/tender_skills
.venv/bin/python -m pytest tests/unit/test_toc_docx_style_map.py -v
```

Expected: FAIL `ImportError: cannot import name 'build_toc_style_level_map'`

- [ ] **Step 3: Implement style map**

在 `src/doc_chunk/outline/toc_docx.py` 追加（`_TOC_STYLE_RE` 附近）：

```python
_TOC_NAME_RE = re.compile(r"^toc\s*(\d+)\s*$", re.IGNORECASE)


def build_toc_style_level_map(styles_xml: bytes) -> dict[str, int]:
    try:
        root = etree.fromstring(styles_xml)
    except Exception:
        return {}
    mapping: dict[str, int] = {}
    for style in root.xpath(".//w:style[@w:type='paragraph']", namespaces=_NS):
        style_id = style.get(f"{{{_WORD_NS}}}styleId")
        if not style_id:
            continue
        name = style.xpath("string(./w:name/@w:val)", namespaces=_NS).strip()
        match = _TOC_NAME_RE.match(name)
        if not match:
            continue
        level = max(1, min(8, int(match.group(1))))
        mapping[style_id] = level
    return mapping


def _resolve_toc_level(style_val: str, toc_style_map: dict[str, int]) -> int | None:
    if not style_val:
        return None
    if style_val in toc_style_map:
        return toc_style_map[style_val]
    match = _TOC_STYLE_RE.match(style_val.strip().lower())
    if match:
        return max(1, min(8, int(match.group(1))))
    return None
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python -m pytest tests/unit/test_toc_docx_style_map.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/doc_chunk/outline/toc_docx.py tests/unit/test_toc_docx_style_map.py
git commit -m "feat: map numeric Word TOC styleIds from styles.xml"
```

---

### Task 2: 更新 `extract_docx_toc_outline`

**Files:**
- Modify: `src/doc_chunk/outline/toc_docx.py`
- Modify: `tests/unit/test_toc_docx_titles.py`

- [ ] **Step 1: Write failing synthetic docx test**

在 `tests/unit/test_toc_docx_titles.py` 追加：

```python
from zipfile import ZipFile, ZIP_DEFLATED
import io
from lxml import etree


def _minimal_docx_with_numeric_toc_styles(tmp_path) -> Path:
    """Build docx: TOC instr + pStyle=16/17 mapped to toc 1/2 in styles.xml."""
    NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    W = "{%s}" % NS

    def p(style: str, texts: list[str], instr: str | None = None) -> str:
        runs = ""
        if instr:
            runs += f'<w:r><w:instrText xml:space="preserve">{instr}</w:instrText></w:r>'
        for t in texts:
            runs += f"<w:r><w:t>{t}</w:t></w:r>"
        return f'<w:p><w:pPr><w:pStyle w:val="{style}"/></w:pPr>{runs}</w:p>'

    body = (
        p("16", ["一、 投标函", "1"], ' TOC \\o "1-3" \\h \\u ')
        + p("16", ["二、 服务偏离表", "2"], " HYPERLINK \\l _Toc1 ")
        + p("17", ["2.1 ", "合同条款偏离表", "2"], " HYPERLINK \\l _Toc2 ")
    )
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="{NS}"><w:body>{body}</w:body></w:document>""".encode()
    styles_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="{NS}">
  <w:style w:type="paragraph" w:styleId="16"><w:name w:val="toc 1"/></w:style>
  <w:style w:type="paragraph" w:styleId="17"><w:name w:val="toc 2"/></w:style>
</w:styles>""".encode()

    docx_path = tmp_path / "numeric-toc.docx"
    buf = io.BytesIO()
    with ZipFile(buf, "w", ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", b'<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/></Types>')
        z.writestr("_rels/.rels", b'<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        z.writestr("word/_rels/document.xml.rels", b'<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        z.writestr("word/document.xml", document_xml)
        z.writestr("word/styles.xml", styles_xml)
    docx_path.write_bytes(buf.getvalue())
    return docx_path


def test_extract_docx_toc_outline_numeric_style_ids(tmp_path: Path) -> None:
    docx_path = _minimal_docx_with_numeric_toc_styles(tmp_path)
    tree = extract_docx_toc_outline(docx_path)
    assert tree is not None
    assert tree.strategy == "toc"
    titles = [n.title for n in tree.nodes]
    assert titles[0] == "一、 投标函"
    assert titles[2].startswith("2.1")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest tests/unit/test_toc_docx_titles.py::test_extract_docx_toc_outline_numeric_style_ids -v
```

Expected: FAIL（`tree is None` 或标题不对）

- [ ] **Step 3: Update extractor to load styles.xml**

修改 `extract_docx_toc_outline`：

```python
_STYLES_XML_PATH = "word/styles.xml"


def extract_docx_toc_outline(source_path: Path) -> OutlineTree | None:
    try:
        with ZipFile(source_path, "r") as archive:
            document_xml = archive.read(_DOC_XML_PATH)
            styles_xml = archive.read(_STYLES_XML_PATH)
    except Exception:
        return None

    try:
        root = etree.fromstring(document_xml)
    except Exception:
        return None

    has_toc_field = any(
        "TOC" in ("".join(instr.itertext()) if instr is not None else "").upper()
        for instr in root.xpath(".//w:instrText", namespaces=_NS)
    )
    if not has_toc_field:
        return None

    toc_style_map = build_toc_style_level_map(styles_xml)

    nodes: list[OutlineNode] = []
    last_seen_by_level: dict[int, str] = {}
    sort_order = 0

    for paragraph in root.xpath(".//w:p", namespaces=_NS):
        style_val = paragraph.xpath("string(./w:pPr/w:pStyle/@w:val)", namespaces=_NS).strip()
        level = _resolve_toc_level(style_val, toc_style_map)
        if level is None:
            continue

        text_parts = paragraph.xpath(".//w:t/text()", namespaces=_NS)
        title = _join_toc_text_parts(text_parts)
        if not title:
            continue

        parent_id = None
        if level > 1:
            for parent_level in range(level - 1, 0, -1):
                parent_id = last_seen_by_level.get(parent_level)
                if parent_id:
                    break

        node_id = f"n{len(nodes) + 1}"
        nodes.append(
            OutlineNode(
                node_id=node_id,
                title=title,
                level=level,
                parent_id=parent_id,
                sort_order=sort_order,
                anchor=Anchor(block_index=sort_order),
            )
        )
        sort_order += 1
        last_seen_by_level[level] = node_id
        for stale_level in list(last_seen_by_level):
            if stale_level > level:
                last_seen_by_level.pop(stale_level, None)

    if not nodes:
        return None
    return OutlineTree(strategy="toc", nodes=nodes)
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/python -m pytest tests/unit/test_toc_docx_titles.py tests/unit/test_toc_docx_style_map.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/doc_chunk/outline/toc_docx.py tests/unit/test_toc_docx_titles.py
git commit -m "fix: extract Word TOC outline from numeric pStyle styleIds"
```

---

### Task 3: 餐补 6.16 集成 + pipeline 回归

**Files:**
- Create: `tests/integration/test_toc_docx_canbu.py`

- [ ] **Step 1: Write integration test**

```python
from __future__ import annotations

from pathlib import Path

import pytest
from doc_chunk.api import extract_file, extract_outline
from doc_chunk.outline.toc_docx import extract_docx_toc_outline

CANBU_DOCX = Path.home() / (
    ".doc-chunk-viewer/uploads/c00aa1f9-02e9-4216-927d-64935b99b1ec/【大纲】餐补标书大纲模板6.16.docx"
)


@pytest.mark.skipif(not CANBU_DOCX.exists(), reason="local canbu 6.16 docx not available")
def test_canbu_docx_uses_word_toc_outline() -> None:
    tree = extract_docx_toc_outline(CANBU_DOCX)
    assert tree is not None
    assert tree.strategy == "toc"
    titles = [n.title for n in tree.nodes[:5]]
    assert any("投标函" in t for t in titles)
    assert any(t.startswith("一、") or "一、" in t for t in titles)
    assert any("2.1" in t and "合同条款偏离表" in t for t in titles)


@pytest.mark.skipif(not CANBU_DOCX.exists(), reason="local canbu 6.16 docx not available")
def test_canbu_pipeline_outline_strategy_is_toc(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    extract_file(CANBU_DOCX, workspace, overwrite=True, promote_headings="auto")
    outline = extract_outline(workspace)
    assert outline.strategy == "toc"
    assert any(n.title.startswith("2.1") for n in outline.nodes)
```

- [ ] **Step 2: Run integration test**

```bash
.venv/bin/python -m pytest tests/integration/test_toc_docx_canbu.py -v
```

Expected: PASS

- [ ] **Step 3: Run anchor alignment regression**

```bash
.venv/bin/python -m pytest tests/integration/test_anchor_viewer_alignment_canbu.py -v
```

Expected: PASS（outline 改 toc 后 anchor enrich + heading_starts 仍对齐）

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_toc_docx_canbu.py
git commit -m "test: canbu 6.16 uses Word TOC field outline extraction"
```

---

## Self-Review

| 需求 | Task |
|------|------|
| G1 TOC 提取成功 | Task 2, 3 |
| G2 标题含序号 | Task 2 `_join_toc_text_parts` |
| G3 旧 toc1 兼容 | Task 2 `_resolve_toc_level` fallback |
| G4 无 TOC fallback 不变 | 未改 builder 顺序 |

无文首 manual toc 代码。无 TBD。

---

## Execution Handoff

Plan saved to `docs/superpowers/plans/2026-07-02-manual-toc-title-enrichment.md`（内容已修订为 Word TOC 方案）。

**1. Subagent-Driven (recommended)**  
**2. Inline Execution**

Which approach?
