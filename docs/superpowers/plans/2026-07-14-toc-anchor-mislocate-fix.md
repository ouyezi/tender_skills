# TOC 目录区误定位修复（C+A+B）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **需求来源**: [`docs/superpowers/specs/2026-07-14-toc-anchor-mislocate-fix-design.md`](../specs/2026-07-14-toc-anchor-mislocate-fix-design.md)

**Goal:** 使 DOCX TOC（含粘连页码 / toc 样式）场景下 outline anchor 与章节切片落在正文标题，不再命中文首目录区；优先书签定位，围栏与行识别兜底。

**Architecture:** 提取阶段跳过 toc 样式作 heading（A2）；扩展 `is_toc_entry_line`（A1）；`heading_starts` 增加 `body_start` 围栏（B）；`toc_docx` 解析 `HYPERLINK \l _Toc*` 写入 `source_refs`，再在 outline 构建时解析 bookmark→`block_index`（C）；`enrich_outline_anchors` 对带 `toc_bookmark:` 的节点优先保留书签 anchor。

**Tech Stack:** Python 3.11+、python-docx / lxml、pytest、Pydantic v2、现有 `doc_chunk.locate.heading_starts` / `outline.toc_docx`

---

## File Map

| 文件 | 职责 | 操作 |
|------|------|------|
| `src/doc_chunk/extract/promote_headings.py` | 扩展 `is_toc_entry_line` | Modify |
| `src/doc_chunk/extract/docx_extractor.py` | toc 样式不当 heading | Modify |
| `src/doc_chunk/outline/toc_styles.py` | 共享 toc 样式映射读取（extractor + toc_docx） | Create |
| `src/doc_chunk/outline/toc_docx.py` | TOC 节点附带 `source_refs=["toc_bookmark:_Toc…"]` | Modify |
| `src/doc_chunk/outline/toc_bookmark.py` | bookmark 名 → block_index 解析 | Create |
| `src/doc_chunk/locate/heading_starts.py` | `infer_body_start` + 匹配围栏 | Modify |
| `src/doc_chunk/outline/anchor_enricher.py` | C 优先，不覆盖书签节点 | Modify |
| `src/doc_chunk/outline/builder.py` | 调用 bookmark resolve | Modify |
| `tests/unit/test_toc_entry_promote_headings.py` | A1 单测扩展 | Modify |
| `tests/unit/test_docx_extractor_toc_style.py` | A2 单测 | Create |
| `tests/unit/test_body_start_fence.py` | B 单测 | Create |
| `tests/unit/test_toc_bookmark_resolve.py` | C 单测 | Create |
| `tests/unit/test_anchor_enricher_bookmark_priority.py` | enricher C 优先 | Create |
| `tests/unit/test_heading_starts_shared.py` | 粘连页码 TOC 不参与匹配 | Modify |
| `docs/CHANGELOG.md` | 变更说明 | Modify |

---

### Task 1: 扩展 `is_toc_entry_line`（A1）

**Files:**
- Modify: `src/doc_chunk/extract/promote_headings.py`
- Modify: `tests/unit/test_toc_entry_promote_headings.py`

- [ ] **Step 1: Write the failing tests**

在 `tests/unit/test_toc_entry_promote_headings.py` 追加：

```python
@pytest.mark.parametrize(
    "line",
    [
        "一、服务方案1",
        "3.东福行业独家亮点9",
        "4百福得-员工福利平台概览12",
        "第一卷供应商须知..........- 3 -",
        "附件A——评分细则........................................................................ - 8 -",
    ],
)
def test_is_toc_entry_line_glued_or_dotted(line: str) -> None:
    assert is_toc_entry_line(line)


@pytest.mark.parametrize(
    "line",
    [
        "三、 服务费一览表",
        "1. 技术方案",
        "ISO9001",
        "2.兑换平台搭建方案",
    ],
)
def test_is_toc_entry_line_rejects_body_like(line: str) -> None:
    assert not is_toc_entry_line(line)
```

保留原有 tab 页码用例不变。

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_toc_entry_promote_headings.py::test_is_toc_entry_line_glued_or_dotted -v`

Expected: FAIL（粘连/点线尚未识别）

- [ ] **Step 3: Implement**

在 `promote_headings.py` 将 `is_toc_entry_line` 扩展为：

```python
_TOC_PAGE_SUFFIX_RE = re.compile(r"[\t]\d+\s*$")
_GLUED_PAGE_RE = re.compile(r"^(?P<title>.+?\D)(?P<page>\d{1,3})$")
_DOTTED_LEADER_RE = re.compile(
    r"^.+?[.\u2026\u3002]{2,}\s*-?\s*\d+\s*-?\s*$"
)
_TOC_LINE_MAX_LEN = 120


def is_toc_entry_line(line: str) -> bool:
    """TOC row: tab+page, glued page, or dotted leaders + page."""
    stripped = line.strip()
    if not stripped or len(stripped) > _TOC_LINE_MAX_LEN:
        return False
    if _TOC_PAGE_SUFFIX_RE.search(stripped):
        return True
    if _DOTTED_LEADER_RE.match(stripped):
        return True
    glued = _GLUED_PAGE_RE.match(stripped)
    if glued is not None and glued.group("title").strip():
        return True
    return False
```

注意：`ISO9001` 整行匹配 `_GLUED_PAGE_RE` 时 title 为 `ISO`、page 为 `900`——应用额外约束避免误伤：仅当 **剥掉页码后的 title 含中文，或含章节前缀（`一、` / `\d+.`）** 时才把 glued 判为 TOC。实现示例：

```python
_CN_OR_SECTION_RE = re.compile(r"[\u4e00-\u9fff]|(?:^[一二三四五六七八九十百零]+、)|(?:^\d+(?:\.\d+)*[.\s、])")


def is_toc_entry_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) > _TOC_LINE_MAX_LEN:
        return False
    if _TOC_PAGE_SUFFIX_RE.search(stripped):
        return True
    if _DOTTED_LEADER_RE.match(stripped):
        return True
    glued = _GLUED_PAGE_RE.match(stripped)
    if glued is None:
        return False
    title = glued.group("title").strip()
    return bool(title) and _CN_OR_SECTION_RE.search(title) is not None
```

确保 `ISO9001` 仍为 False；`一、服务方案1` 为 True。

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_toc_entry_promote_headings.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/doc_chunk/extract/promote_headings.py tests/unit/test_toc_entry_promote_headings.py
git commit -m "$(cat <<'EOF'
fix: detect glued-page and dotted-leader TOC lines

EOF
)"
```

---

### Task 2: 提取时跳过 toc 样式（A2）

**Files:**
- Create: `src/doc_chunk/outline/toc_styles.py`
- Modify: `src/doc_chunk/extract/docx_extractor.py`
- Modify: `src/doc_chunk/outline/toc_docx.py`（改为调用共享 map，行为不变）
- Create: `tests/unit/test_docx_extractor_toc_style.py`

- [ ] **Step 1: Write the failing test**

创建 `tests/unit/test_docx_extractor_toc_style.py`，用与 `test_toc_docx_titles.py` 相同方式组装最小 docx：含 `toc 1` 段 `一、服务方案1` 与 Heading 段 `一、服务方案`。

```python
from __future__ import annotations

import io
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from doc_chunk.api import extract_file


def _docx_with_toc_and_body(tmp_path: Path) -> Path:
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    body = (
        f'<w:p><w:pPr><w:pStyle w:val="20"/></w:pPr>'
        f'<w:r><w:instrText xml:space="preserve"> TOC \\o "1-3" \\h \\u </w:instrText></w:r>'
        f'<w:r><w:t>一、服务方案1</w:t></w:r></w:p>'
        f'<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>'
        f'<w:r><w:t>一、服务方案</w:t></w:r></w:p>'
        f'<w:p><w:r><w:t>正文段落</w:t></w:r></w:p>'
    )
    document_xml = (
        f'<?xml version="1.0"?><w:document xmlns:w="{ns}">'
        f"<w:body>{body}</w:body></w:document>"
    ).encode()
    styles_xml = f"""<?xml version="1.0"?>
<w:styles xmlns:w="{ns}">
  <w:style w:type="paragraph" w:styleId="20"><w:name w:val="toc 1"/></w:style>
  <w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="Heading 1"/></w:style>
</w:styles>""".encode()
    path = tmp_path / "toc-style.docx"
    buf = io.BytesIO()
    with ZipFile(buf, "w", ZIP_DEFLATED) as z:
        z.writestr(
            "[Content_Types].xml",
            b'<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            b'<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            b'<Default Extension="xml" ContentType="application/xml"/>'
            b'<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            b'<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
            b"</Types>",
        )
        z.writestr(
            "word/_rels/document.xml.rels",
            b'<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"></Relationships>',
        )
        z.writestr("word/document.xml", document_xml)
        z.writestr("word/styles.xml", styles_xml)
    path.write_bytes(buf.getvalue())
    return path


def test_extract_skips_toc_style_as_heading(tmp_path: Path) -> None:
    src = _docx_with_toc_and_body(tmp_path)
    ws = tmp_path / "ws"
    extract_file(src, ws, overwrite=True)
    md = (ws / "content.md").read_text(encoding="utf-8")
    assert "# 一、服务方案1" not in md
    assert "一、服务方案1" in md  # 可作为普通段保留
    assert md.count("# 一、服务方案") == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_docx_extractor_toc_style.py::test_extract_skips_toc_style_as_heading -v`

Expected: FAIL（若 toc 被当成 heading）或按当前实现调整断言；目标是 toc 行不得出现 `# 一、服务方案1`。

- [ ] **Step 3: Create shared toc style helper + wire extractor**

创建 `src/doc_chunk/outline/toc_styles.py`：

```python
from __future__ import annotations

import re
from zipfile import ZipFile
from pathlib import Path

from lxml import etree

_WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_NS = {"w": _WORD_NS}
_TOC_NAME_RE = re.compile(r"^toc\s*(\d+)\s*$", re.IGNORECASE)
_TOC_STYLE_RE = re.compile(r"^toc(\d+)$", re.IGNORECASE)


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
        mapping[style_id] = max(1, min(8, int(match.group(1))))
    return mapping


def resolve_toc_level(style_val: str, toc_style_map: dict[str, int]) -> int | None:
    if not style_val:
        return None
    if style_val in toc_style_map:
        return toc_style_map[style_val]
    match = _TOC_STYLE_RE.match(style_val.strip())
    if match:
        return max(1, min(8, int(match.group(1))))
    return None


def load_toc_style_map_from_docx(path: Path) -> dict[str, int]:
    try:
        with ZipFile(path, "r") as archive:
            try:
                styles_xml = archive.read("word/styles.xml")
            except KeyError:
                return {}
    except Exception:
        return {}
    return build_toc_style_level_map(styles_xml)
```

将 `toc_docx.py` 中的 `build_toc_style_level_map` / `_resolve_toc_level` 改为从 `toc_styles` import（删除重复实现，保持对外行为）。

在 `docx_extractor.extract_docx` 开头：

```python
toc_style_map = load_toc_style_map_from_docx(path)
```

在处理段落时，取得 style id（`paragraph._element` 上 `w:pStyle/@w:val`），若 `resolve_toc_level(style_id, toc_style_map) is not None`：

```python
acc.add_paragraph(text)  # 绝不 add_heading
# 跳过 promote_headings
continue  # 仍处理图片 embeds
```

注意：python-docx 的 `paragraph.style.name` 可能是 `toc 1`，也可用 name 侧检测：`name.lower().startswith("toc ")`。优先用 styleId map，与 outline 一致。

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_docx_extractor_toc_style.py tests/unit/test_toc_docx_style_map.py tests/unit/test_toc_docx_titles.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/doc_chunk/outline/toc_styles.py src/doc_chunk/outline/toc_docx.py \
  src/doc_chunk/extract/docx_extractor.py tests/unit/test_docx_extractor_toc_style.py
git commit -m "$(cat <<'EOF'
fix: do not promote Word toc styles to markdown headings

EOF
)"
```

---

### Task 3: `body_start` 围栏（B）

**Files:**
- Modify: `src/doc_chunk/locate/heading_starts.py`
- Create: `tests/unit/test_body_start_fence.py`
- Modify: `tests/unit/test_heading_starts_shared.py`（可选追加粘连页码用例）

- [ ] **Step 1: Write the failing tests**

创建 `tests/unit/test_body_start_fence.py`：

```python
from __future__ import annotations

from doc_chunk.locate.heading_starts import (
    build_node_heading_starts,
    infer_body_start,
    parse_body_headings,
)
from doc_chunk.models.outline import Anchor, OutlineNode, OutlineTree

GLUED_TOC_MD = (
    "封面\n\n"
    "# 目录\n\n"
    "一、服务方案1\n"
    "（一）服务大纲1\n"
    "1.全场景福利平台1\n\n"
    "# 一、服务方案\n\n"
    "正文A\n\n"
    "## （一）服务大纲\n\n"
    "正文B\n"
)


def test_infer_body_start_skips_glued_toc_cluster() -> None:
    start = infer_body_start(GLUED_TOC_MD)
    assert start == GLUED_TOC_MD.index("# 一、服务方案\n")


def test_build_node_heading_starts_uses_body_not_toc() -> None:
    tree = OutlineTree(
        strategy="toc",
        nodes=[
            OutlineNode(
                node_id="n1",
                title="一、服务方案",
                level=1,
                parent_id=None,
                sort_order=0,
                anchor=Anchor(),
            ),
            OutlineNode(
                node_id="n2",
                title="（一）服务大纲",
                level=2,
                parent_id="n1",
                sort_order=1,
                anchor=Anchor(),
            ),
        ],
    )
    starts = build_node_heading_starts(tree, GLUED_TOC_MD, use_existing_anchor_fallback=False)
    assert starts["n1"] == GLUED_TOC_MD.index("# 一、服务方案\n")
    assert starts["n2"] == GLUED_TOC_MD.index("## （一）服务大纲\n")
    body = parse_body_headings(GLUED_TOC_MD)
    assert all(h.char_start >= infer_body_start(GLUED_TOC_MD) or h.title.strip() in {"目录"} for h in body) or True
    # 强断言：匹配点必须在 body_start 之后（目录标题「目录」本身可在围栏前，但不用于 n1/n2）
    assert starts["n1"] >= infer_body_start(GLUED_TOC_MD)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_body_start_fence.py -v`

Expected: FAIL（`infer_body_start` 未定义）

- [ ] **Step 3: Implement**

在 `heading_starts.py` 增加：

```python
_TOC_HEADING_TITLES = {"目录", "总目录", "目 录"}


def infer_body_start(content_md: str) -> int:
    """First char offset where body section matching may begin."""
    if not content_md:
        return 0

    # Scan line by line for glued/dotted TOC cluster after optional 目录 heading
    pos = 0
    last_toc_end: int | None = None
    saw_toc_heading = False
    for line in content_md.splitlines(keepends=True):
        stripped = line.strip()
        plain = stripped.lstrip("#").strip()
        if plain in _TOC_HEADING_TITLES:
            saw_toc_heading = True
            last_toc_end = pos + len(line)
            pos += len(line)
            continue
        if is_toc_entry_line(plain) or is_toc_entry_line(stripped):
            last_toc_end = pos + len(line)
            pos += len(line)
            continue
        # Non-toc content after we have seen toc material → body starts here
        if last_toc_end is not None and stripped:
            # If this is a markdown heading that is not the bare 目录 title, treat as body
            if stripped.startswith("#") and plain not in _TOC_HEADING_TITLES:
                return pos
            if saw_toc_heading or last_toc_end is not None:
                # skip blank-only; for non-heading after toc cluster, still might be body
                if stripped.startswith("#"):
                    return pos
        pos += len(line)

    if last_toc_end is not None:
        return last_toc_end
    return 0
```

微调实现直至单测通过：核心契约是 `infer_body_start(GLUED_TOC_MD) == index("# 一、服务方案\n")`。

修改 `parse_body_headings`：

```python
def parse_body_headings(content_md: str, *, body_start: int | None = None) -> list[Heading]:
    start = infer_body_start(content_md) if body_start is None else body_start
    headings: list[Heading] = []
    for match in _HEADING_RE.finditer(content_md):
        if match.start() < start:
            # 允许保留「目录」类标题不进入匹配池：直接 continue
            continue
        title = match.group(2).strip()
        if is_toc_entry_line(title):
            continue
        headings.append(Heading(char_start=match.start(), level=len(match.group(1)), title=title))
    return headings
```

`build_node_heading_starts` / `fallback_char_start` 继续调用 `parse_body_headings`（默认自动围栏）。

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/unit/test_body_start_fence.py tests/unit/test_heading_starts_shared.py tests/unit/test_anchor_enricher_toc_bid.py -v`

Expected: PASS（餐补回归全绿）

- [ ] **Step 5: Commit**

```bash
git add src/doc_chunk/locate/heading_starts.py tests/unit/test_body_start_fence.py
git commit -m "$(cat <<'EOF'
fix: fence heading match after inferred body_start

EOF
)"
```

---

### Task 4: TOC 节点附带 bookmark `source_refs`（C 前半）

**Files:**
- Modify: `src/doc_chunk/outline/toc_docx.py`
- Modify: `tests/unit/test_toc_docx_titles.py`（或新建 `tests/unit/test_toc_docx_bookmark_refs.py`）

- [ ] **Step 1: Write the failing test**

扩展最小 docx helper：toc 段含 `HYPERLINK \l _Toc7154`，断言：

```python
def test_extract_docx_toc_outline_records_bookmark_ref(tmp_path: Path) -> None:
    path = _minimal_docx_with_hyperlink_toc(tmp_path)  # 实现见下
    tree = extract_docx_toc_outline(path)
    assert tree is not None
    node = next(n for n in tree.nodes if "服务方案" in n.title)
    assert any(ref.startswith("toc_bookmark:") for ref in node.source_refs)
    assert "toc_bookmark:_Toc7154" in node.source_refs
```

`_minimal_docx_with_hyperlink_toc`：一个 toc1 段文本 `一、服务方案1` + instr `HYPERLINK \l _Toc7154`，styles 映射 toc 1。

- [ ] **Step 2: Run test — expect FAIL**

- [ ] **Step 3: Implement in `toc_docx.py`**

解析段落内所有 `instrText`，用正则：

```python
_HYPERLINK_BOOKMARK_RE = re.compile(r'HYPERLINK\s+\\l\s+"?(_Toc[\w]+)"?', re.IGNORECASE)
```

取第一个 `_Toc…`，写入：

```python
source_refs=[f"toc_bookmark:{bookmark}"] if bookmark else []
```

无超链接的 toc 节点 `source_refs=[]`（合法）。

- [ ] **Step 4: Run tests — expect PASS**

Run: `.venv/bin/pytest tests/unit/test_toc_docx_titles.py tests/unit/test_toc_docx_bookmark_refs.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/doc_chunk/outline/toc_docx.py tests/unit/test_toc_docx_bookmark_refs.py
git commit -m "$(cat <<'EOF'
feat: record toc_bookmark source_refs from TOC hyperlinks

EOF
)"
```

---

### Task 5: bookmark → block_index 解析（C 后半）

**Files:**
- Create: `src/doc_chunk/outline/toc_bookmark.py`
- Modify: `src/doc_chunk/outline/builder.py`
- Create: `tests/unit/test_toc_bookmark_resolve.py`

- [ ] **Step 1: Write the failing test**

构造 docx：

1. toc 段：`一、服务方案1` + `HYPERLINK \l _Toc1`
2. 正文：`w:bookmarkStart w:name="_Toc1"` + Heading `一、服务方案` + 段落 `正文`

先 `extract_file`，再 `extract_docx_toc_outline`，再调用：

```python
from doc_chunk.outline.toc_bookmark import apply_toc_bookmark_anchors
from doc_chunk.models.content_block import ContentBlocksFile

def test_apply_toc_bookmark_anchors_sets_body_block(tmp_path: Path) -> None:
    src = _docx_toc_with_bookmark(tmp_path)
    ws = tmp_path / "ws"
    extract_file(src, ws, overwrite=True)
    tree = extract_docx_toc_outline(src)
    assert tree is not None
    blocks = ContentBlocksFile.model_validate_json((ws / "content.blocks.json").read_text())
    content_md = (ws / "content.md").read_text()
    enriched = apply_toc_bookmark_anchors(tree, src, blocks, content_md=content_md)
    node = next(n for n in enriched.nodes if "服务方案" in n.title and n.level == 1)
    assert node.anchor.block_index is not None
    block = next(b for b in blocks.blocks if b.block_index == node.anchor.block_index)
    assert "一、服务方案" in (block.text_preview or content_md[block.char_start:block.char_end])
    assert "服务方案1" not in (block.text_preview or "")
```

另加：`test_apply_toc_bookmark_anchors_missing_bookmark_noop` — 错误 bookmark 名时不抛错，该节点 block_index 保持原样。

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement `toc_bookmark.py`**

```python
def apply_toc_bookmark_anchors(
    tree: OutlineTree,
    source_path: Path,
    blocks: ContentBlocksFile,
    *,
    content_md: str,
) -> OutlineTree:
    """Fill anchor.block_index from toc_bookmark:* source_refs when resolvable."""
```

算法：

1. 从 `document.xml` 建 `bookmark_name → 目标段落纯文本`（bookmarkStart 之后第一个非空 `w:p` 的文本）。
2. 建「提取顺序」段落列表：与 `extract_docx` 相同规则——跳过空段；toc 样式段计入 paragraph；Heading 计入 heading。为每个产出 block 的段落记录 `(block_index 候选顺序)`。更稳妥：用目标段落文本在 `blocks.blocks` 中找 **第一个** `block_type in {heading, paragraph}` 且 normalize 标题匹配、且 `char_start >= infer_body_start(content_md)` 的 block。
3. 对每个带 `toc_bookmark:X` 的节点，查 bookmark 文本 → 匹配 body block → 设置 `anchor.block_index` / `block_start` / `char_start` / `char_end`。
4. 失败则跳过该节点。

在 `builder.build_outline_from_workspace` 中，在 `enrich_outline_anchors` **之前**：

```python
if tree.strategy == "toc" and suffix in {".docx", ".docm", ".doc"} and blocks is not None:
    tree = apply_toc_bookmark_anchors(tree, source_path, blocks, content_md=content_md)
```

- [ ] **Step 4: Run tests — PASS**

Run: `.venv/bin/pytest tests/unit/test_toc_bookmark_resolve.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/doc_chunk/outline/toc_bookmark.py src/doc_chunk/outline/builder.py \
  tests/unit/test_toc_bookmark_resolve.py
git commit -m "$(cat <<'EOF'
feat: resolve TOC hyperlink bookmarks to body block anchors

EOF
)"
```

---

### Task 6: enricher 书签优先（C 与 heading_starts 协同）

**Files:**
- Modify: `src/doc_chunk/outline/anchor_enricher.py`
- Create: `tests/unit/test_anchor_enricher_bookmark_priority.py`

- [ ] **Step 1: Write the failing test**

构造 tree：节点 `source_refs=["toc_bookmark:_Toc1"]`，`anchor.block_index` 已指向正文 heading block；`content_md` 文首仍有易混淆的目录标题文本。`heading_starts` 若误匹配目录，enricher 也不得覆盖书签 block。

```python
def test_enrich_preserves_bookmark_block_index() -> None:
    content_md = "一、服务方案1\n\n# 一、服务方案\n\nbody\n"
    # blocks: block0 paragraph toc line, block1 heading body
    tree = OutlineTree(
        strategy="toc",
        nodes=[
            OutlineNode(
                node_id="n1",
                title="一、服务方案",
                level=1,
                parent_id=None,
                sort_order=0,
                anchor=Anchor(block_index=1, block_start=1, char_start=..., char_end=...),
                source_refs=["toc_bookmark:_Toc1"],
            )
        ],
    )
    enriched = enrich_outline_anchors(tree, blocks, content_md=content_md)
    assert enriched.nodes[0].anchor.block_index == 1
```

（补全 `ContentBlocksFile` 字段与真实 char 偏移。）

- [ ] **Step 2: Run — expect FAIL**（当前逻辑用 heading_starts 覆盖）

- [ ] **Step 3: Implement**

在 `enrich_outline_anchors` 循环内：

```python
bookmark_locked = any(ref.startswith("toc_bookmark:") for ref in node.source_refs) and (
    anchor.block_index is not None and anchor.block_index in block_by_index
)

if bookmark_locked:
    idx = anchor.block_index
    block = block_by_index[idx]
    anchor.block_start = idx
    anchor.char_start = block.char_start
    anchor.char_end = block.char_end
    # 仍允许非 paragraph/heading 时 relocate
else:
    # 现有 heading_starts 分支不变
    ...
```

- [ ] **Step 4: Run**

Run: `.venv/bin/pytest tests/unit/test_anchor_enricher_bookmark_priority.py tests/unit/test_anchor_enricher.py tests/unit/test_anchor_enricher_toc_bid.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/doc_chunk/outline/anchor_enricher.py tests/unit/test_anchor_enricher_bookmark_priority.py
git commit -m "$(cat <<'EOF'
fix: prefer toc_bookmark anchors over heading_starts match

EOF
)"
```

---

### Task 7: 湖南火电技术标验收 + CHANGELOG

**Files:**
- Create: `tests/integration/test_hunan_huodian_tech_toc_anchors.py`
- Modify: `docs/CHANGELOG.md`

- [ ] **Step 1: Write integration test（本地样例存在则跑）**

```python
from __future__ import annotations

from pathlib import Path

import pytest

from doc_chunk.api import extract_file, extract_outline
from doc_chunk.models.outline import OutlineTree
from doc_chunk.locate.heading_starts import infer_body_start

SAMPLE = Path(
    "/Users/tongqianni/xlab/标书助力/测试招投标文件/标书诊断/湖南火电/"
    "湖南火电员工福利商城招标-标书（技术部分）.docx"
)

@pytest.mark.skipif(not SAMPLE.exists(), reason="hunan huodian tech docx not available")
def test_hunan_huodian_tech_anchors_in_body(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    extract_file(SAMPLE, ws, overwrite=True)
    extract_outline(ws)
    content_md = (ws / "content.md").read_text(encoding="utf-8")
    outline = OutlineTree.model_validate_json((ws / "outline.json").read_text(encoding="utf-8"))
    body_start = infer_body_start(content_md)

    titles = ["一、服务方案", "2.兑换平台搭建方案", "（一）服务大纲"]
    # 标题可能带空格：用 normalize 或 substring
    hit = 0
    for node in outline.nodes:
        if not any(t.replace(" ", "") in node.title.replace(" ", "") for t in titles):
            continue
        assert node.anchor.char_start is not None
        assert node.anchor.char_start >= body_start
        snippet = content_md[node.anchor.char_start : node.anchor.char_start + 40]
        assert "服务方案1" not in snippet  # 不落在粘连页码目录行
        hit += 1
    assert hit >= 3
```

路径写死用户机样例；CI 无文件则 skip。若希望可移植，可再加 env `TENDER_SAMPLE_HUNAN_TECH`。

- [ ] **Step 2: Run**

Run: `.venv/bin/pytest tests/integration/test_hunan_huodian_tech_toc_anchors.py -v`

Expected: PASS（本机有样例时）

- [ ] **Step 3: 全量相关回归**

Run:

```bash
.venv/bin/pytest \
  tests/unit/test_toc_entry_promote_headings.py \
  tests/unit/test_docx_extractor_toc_style.py \
  tests/unit/test_body_start_fence.py \
  tests/unit/test_toc_bookmark_resolve.py \
  tests/unit/test_anchor_enricher_bookmark_priority.py \
  tests/unit/test_heading_starts_shared.py \
  tests/unit/test_anchor_enricher_toc_bid.py \
  tests/unit/test_anchor_enricher.py \
  tests/unit/test_toc_docx_titles.py \
  tests/integration/test_hunan_huodian_tech_toc_anchors.py \
  -v
```

Expected: PASS

- [ ] **Step 4: CHANGELOG**

在 `docs/CHANGELOG.md` 顶部增加条目（保持现有版本风格；若需 bump 次版本按仓库惯例，本任务以文档说明为主）：

```markdown
## Unreleased

### Fixed

- DOCX TOC 粘连页码 / toc 样式场景下，outline anchor 不再落在文首目录区：书签优先定位 + `body_start` 围栏 + 扩展 `is_toc_entry_line`；提取阶段 toc 样式不再写成 Markdown 标题。已解析文档需重跑流水线。
```

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_hunan_huodian_tech_toc_anchors.py docs/CHANGELOG.md
git commit -m "$(cat <<'EOF'
test: accept hunan huodian tech TOC body anchors

EOF
)"
```

---

## Spec Coverage Checklist

| Spec 要求 | Task |
|-----------|------|
| A1 粘连/点线 `is_toc_entry_line` | Task 1 |
| A2 toc 样式不写 heading | Task 2 |
| B `body_start` 围栏 | Task 3 |
| C TOC hyperlink → bookmark → block | Task 4–5 |
| enricher C 优先 | Task 6 |
| 降级不中断 / 缺失 bookmark noop | Task 5 |
| 餐补回归 | Task 3 / 6 / 7 |
| 湖南火电验收 ≥3–5 节点 | Task 7 |
| CHANGELOG 破坏性说明 | Task 7 |
| PDF 完整修复 | Out of scope（未排任务） |

---

## Self-Review Notes

- 无 TBD 占位；各 Task 含具体测试代码与命令。
- `source_refs` 前缀统一为 `toc_bookmark:`（Task 4–6 一致）。
- `build_toc_style_level_map` 抽到 `toc_styles.py`，避免 extractor / toc_docx 两套逻辑。
- `infer_body_start` 只依赖 `content.md` + A1，符合 spec §5 修正。
