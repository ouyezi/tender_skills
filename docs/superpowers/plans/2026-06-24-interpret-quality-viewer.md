# interpret Quality & Viewer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix tender interpret scoring extraction (empty scoring shells + mixed mega-segments) and render full schema 1.2 results in the Viewer, with full LLM prompt logging for debugging.

**Architecture:** Keep interpret v2 full-segment extraction. Add `scoring_segments.py` helpers for table detection, anchor injection (B), and dedicated scoring segments (C, max 5). Strengthen `prompts.py` appendices for mixed format+scoring segments. Centralize prompt logging in `llm_logging.py`. Viewer `interpret.js` renders `children[]`, directory `structure` trees, and `overview` summaries.

**Tech Stack:** Python 3.11+, Pydantic v2, pytest, FastAPI viewer (static JS), `doc_chunk` table sidecars (`content.blocks.json`, `tables/*.json`)

**Spec:** `docs/superpowers/specs/2026-06-24-interpret-quality-viewer-requirements.md` (v1.1)

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `src/tender_insights/common/scoring_segments.py` | Create | Detect scoring tables; inject llm_text into short scoring sections; build dedicated segments |
| `src/tender_insights/common/segment_planner.py` | Modify | Wire B+A injection + append C segments in `plan_segments` |
| `src/tender_insights/interpret/llm_logging.py` | Create | `log_llm_prompt()` with env gate + optional file dump |
| `src/tender_insights/interpret/extractor.py` | Modify | Log each segment + overview progress callback |
| `src/tender_insights/interpret/overview.py` | Modify | Log overview messages |
| `src/tender_insights/interpret/prompts.py` | Modify | Mixed-segment + scoring-table appendices |
| `viewer/viewer/static/interpret.js` | Modify | Render `children`, `structure`, `overview` |
| `viewer/viewer/static/interpret.html` | Modify | Overview panel container |
| `viewer/viewer/static/style.css` | Modify | Child list + tree indent styles |
| `viewer/viewer/__main__.py` | Modify | `logging.basicConfig` for stderr INFO |
| `tests/tender_insights/unit/test_scoring_segments.py` | Create | Table detection + injection + dedicated segments |
| `tests/tender_insights/unit/test_segment_planner.py` | Modify | Integration via `plan_segments` |
| `tests/tender_insights/unit/test_interpret_llm_logging.py` | Create | caplog assertions |
| `tests/tender_insights/unit/test_interpret_prompts.py` | Modify | Mixed + scoring-table appendix tests |
| `viewer/tests/unit/test_interpret_static_assets.py` | Create | Assert JS contains children renderer hooks |
| `viewer/README.md` | Modify | `INTERPRET_LOG_PROMPTS` docs |
| `.cursor/skills/tender-interpret/SKILL.md` | Modify | Scoring segments + logging |

---

### Task 1: Viewer — render scoring `children`

**Files:**
- Modify: `viewer/viewer/static/interpret.js`
- Modify: `viewer/viewer/static/style.css`
- Create: `viewer/tests/unit/test_interpret_static_assets.py`

- [ ] **Step 1: Write the failing test**

Create `viewer/tests/unit/test_interpret_static_assets.py`:

```python
from pathlib import Path

STATIC = Path(__file__).resolve().parents[2] / "viewer" / "static"


def test_interpret_js_renders_scoring_children() -> None:
    js = (STATIC / "interpret.js").read_text(encoding="utf-8")
    assert "renderScoringChildren" in js
    assert "item.children" in js
    assert "score_range" in js


def test_style_has_scoring_child_classes() -> None:
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    assert ".scoring-child" in css
    assert ".scoring-children" in css
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest viewer/tests/unit/test_interpret_static_assets.py::test_interpret_js_renders_scoring_children -v`

Expected: FAIL (`renderScoringChildren` not in interpret.js)

- [ ] **Step 3: Implement children rendering**

In `viewer/viewer/static/interpret.js`, add before `renderCards`:

```javascript
function renderScoringChildren(children) {
  if (!children?.length) {
    return "";
  }
  const rows = children
    .map((child) => {
      const score =
        child.max_score != null
          ? `${child.max_score}${child.score_range ? `（${child.score_range}）` : ""}`
          : child.score_range || "";
      let html = `<li class="scoring-child">`;
      html += `<strong>${escapeHtml(child.title || "细则")}</strong>`;
      if (score) {
        html += ` <span class="child-score">${escapeHtml(score)}</span>`;
      }
      if (child.criteria) {
        html += `<p class="child-criteria">${escapeHtml(child.criteria)}</p>`;
      }
      if (child.source_excerpt) {
        html += `<details class="child-excerpt"><summary>原文摘录</summary>`;
        html += `<blockquote>${escapeHtml(child.source_excerpt)}</blockquote></details>`;
      }
      html += `</li>`;
      return html;
    })
    .join("");
  return `<ul class="scoring-children">${rows}</ul>`;
}
```

Inside `renderCards`, after the parent `item.criteria` block, add:

```javascript
    if (tab.key === "scoring" && item.children?.length) {
      body += renderScoringChildren(item.children);
    }
```

In `viewer/viewer/static/style.css`, append:

```css
.scoring-children {
  margin: 0.5rem 0 0 1rem;
  padding: 0;
  list-style: none;
  border-left: 2px solid var(--border, #ddd);
}

.scoring-child {
  padding: 0.5rem 0 0.5rem 0.75rem;
}

.scoring-child + .scoring-child {
  border-top: 1px dashed var(--border, #eee);
}

.child-score {
  color: var(--muted, #666);
  font-size: 0.9em;
}

.child-criteria {
  margin: 0.35rem 0 0;
  white-space: pre-wrap;
}

.child-excerpt summary {
  cursor: pointer;
  color: var(--link, #06c);
  font-size: 0.9em;
}
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest viewer/tests/unit/test_interpret_static_assets.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add viewer/viewer/static/interpret.js viewer/viewer/static/style.css viewer/tests/unit/test_interpret_static_assets.py
git commit -m "feat(viewer): render scoring_items children in interpret page"
```

---

### Task 2: Viewer — directory `structure` tree + `inferred` + overview panel

**Files:**
- Modify: `viewer/viewer/static/interpret.js`
- Modify: `viewer/viewer/static/interpret.html`
- Modify: `viewer/viewer/static/style.css`
- Modify: `viewer/tests/unit/test_interpret_static_assets.py`

- [ ] **Step 1: Write the failing tests**

Append to `viewer/tests/unit/test_interpret_static_assets.py`:

```python
def test_interpret_js_renders_directory_structure() -> None:
    js = (STATIC / "interpret.js").read_text(encoding="utf-8")
    assert "renderStructureTree" in js
    assert "item.inferred" in js


def test_interpret_js_renders_overview() -> None:
    js = (STATIC / "interpret.js").read_text(encoding="utf-8")
    assert "renderOverview" in js


def test_interpret_html_has_overview_panel() -> None:
    html = (STATIC / "interpret.html").read_text(encoding="utf-8")
    assert 'id="overview-panel"' in html
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest viewer/tests/unit/test_interpret_static_assets.py::test_interpret_js_renders_directory_structure -v`

Expected: FAIL

- [ ] **Step 3: Add overview panel to HTML**

In `viewer/viewer/static/interpret.html`, inside `#result-panel` before `#result-tabs`:

```html
      <section id="overview-panel" class="overview-panel" hidden>
        <details open>
          <summary>解读概要</summary>
          <div id="overview-content"></div>
        </details>
      </section>
```

- [ ] **Step 4: Add JS helpers**

In `interpret.js`, add:

```javascript
function renderStructureTree(nodes, depth = 0) {
  if (!nodes?.length) {
    return "";
  }
  return `<ul class="structure-tree depth-${depth}">${nodes
    .map((node) => {
      const mandatory = node.mandatory === false ? "（可选）" : "";
      const childHtml = node.children?.length ? renderStructureTree(node.children, depth + 1) : "";
      return `<li>${escapeHtml(node.title || "")}${mandatory ? ` <em>${mandatory}</em>` : ""}${childHtml}</li>`;
    })
    .join("")}</ul>`;
}

function renderOverview(overview) {
  const panel = document.getElementById("overview-panel");
  const content = document.getElementById("overview-content");
  if (!overview || !panel || !content) {
    return;
  }
  const fields = [
    ["summary", "总览"],
    ["disqualification_summary", "废标项"],
    ["scoring_summary", "得分项"],
    ["bid_risk_summary", "风险"],
    ["directory_summary", "目录"],
  ];
  const html = fields
    .filter(([key]) => overview[key])
    .map(([key, label]) => `<p><strong>${label}：</strong>${escapeHtml(overview[key])}</p>`)
    .join("");
  if (!html) {
    panel.hidden = true;
    return;
  }
  content.innerHTML = html;
  panel.hidden = false;
}
```

In `renderCards`, for directory tab after `required_sections` block:

```javascript
    if (tab.key === "directory") {
      if (item.inferred) {
        body += `<p><span class="inferred-badge">推断目录</span></p>`;
      }
      if (item.structure?.length) {
        body += renderStructureTree(item.structure);
      }
    }
```

In `loadResult`, after `state.result = result`:

```javascript
  renderOverview(result.interpretation?.overview);
```

In `style.css`, append:

```css
.overview-panel {
  margin-bottom: 1rem;
  padding: 0.75rem 1rem;
  background: var(--panel-bg, #f8f9fa);
  border-radius: 6px;
}

.structure-tree {
  margin: 0.25rem 0 0.5rem 1rem;
  padding-left: 0.75rem;
}

.inferred-badge {
  display: inline-block;
  padding: 0.1rem 0.4rem;
  border-radius: 4px;
  background: #fff3cd;
  font-size: 0.85em;
}
```

- [ ] **Step 5: Run tests**

Run: `.venv/bin/pytest viewer/tests/unit/test_interpret_static_assets.py -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add viewer/viewer/static/interpret.js viewer/viewer/static/interpret.html viewer/viewer/static/style.css viewer/tests/unit/test_interpret_static_assets.py
git commit -m "feat(viewer): show directory structure, inferred badge, and overview"
```

---

### Task 3: LLM prompt logging module

**Files:**
- Create: `src/tender_insights/interpret/llm_logging.py`
- Create: `tests/tender_insights/unit/test_interpret_llm_logging.py`

- [ ] **Step 1: Write the failing test**

Create `tests/tender_insights/unit/test_interpret_llm_logging.py`:

```python
import json
import logging

import pytest

from tender_insights.interpret.llm_logging import log_llm_prompt


def test_log_llm_prompt_emits_full_messages(caplog, monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("INTERPRET_LOG_PROMPTS", raising=False)
    out_dir = tmp_path / "prompts"
    monkeypatch.setenv("INTERPRET_LOG_PROMPTS_DIR", str(out_dir))

    messages = [
        {"role": "system", "content": "SYSTEM TEXT"},
        {"role": "user", "content": "USER TEXT with 商品方案 0-2分"},
    ]
    with caplog.at_level(logging.INFO, logger="tender_insights.interpret.llm"):
        log_llm_prompt(
            call_type="segment",
            messages=messages,
            workspace="/tmp/ws",
            segment_id="seg-001",
            section_path=["第三章", "5.2 评分"],
            token_estimate=42,
        )

    assert any("SYSTEM TEXT" in r.message for r in caplog.records)
    assert any("USER TEXT with 商品方案" in r.message for r in caplog.records)
    dumped = json.loads((out_dir / "seg-001.json").read_text(encoding="utf-8"))
    assert dumped["call_type"] == "segment"
    assert dumped["messages"] == messages


def test_log_llm_prompt_disabled(monkeypatch, caplog) -> None:
    monkeypatch.setenv("INTERPRET_LOG_PROMPTS", "0")
    with caplog.at_level(logging.INFO, logger="tender_insights.interpret.llm"):
        log_llm_prompt(call_type="overview", messages=[{"role": "user", "content": "x"}])
    assert caplog.records == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/tender_insights/unit/test_interpret_llm_logging.py -v`

Expected: FAIL (`ModuleNotFoundError: llm_logging`)

- [ ] **Step 3: Implement logging module**

Create `src/tender_insights/interpret/llm_logging.py`:

```python
from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger("tender_insights.interpret.llm")


def _prompts_enabled() -> bool:
    raw = os.environ.get("INTERPRET_LOG_PROMPTS")
    if raw is None:
        return True
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def log_llm_prompt(
    *,
    call_type: str,
    messages: list[dict[str, str]],
    workspace: str | None = None,
    segment_id: str | None = None,
    section_path: list[str] | None = None,
    token_estimate: int | None = None,
) -> None:
    if not _prompts_enabled():
        return

    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "call_type": call_type,
        "workspace": workspace,
        "segment_id": segment_id,
        "section_path": section_path or [],
        "token_estimate": token_estimate,
        "messages": messages,
    }
    logger.info(
        "interpret_llm_prompt call_type=%s segment_id=%s section_path=%s messages=%s",
        call_type,
        segment_id or "-",
        " > ".join(section_path or []) or "-",
        json.dumps(messages, ensure_ascii=False),
    )

    dump_dir = os.environ.get("INTERPRET_LOG_PROMPTS_DIR")
    if not dump_dir:
        return
    out = Path(dump_dir)
    out.mkdir(parents=True, exist_ok=True)
    fname = segment_id or call_type
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in fname)
    (out / f"{safe}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/tender_insights/unit/test_interpret_llm_logging.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tender_insights/interpret/llm_logging.py tests/tender_insights/unit/test_interpret_llm_logging.py
git commit -m "feat(interpret): add LLM prompt logging with optional file dump"
```

---

### Task 4: Wire logging + overview progress in extractor

**Files:**
- Modify: `src/tender_insights/interpret/extractor.py`
- Modify: `src/tender_insights/interpret/overview.py`
- Modify: `viewer/viewer/__main__.py`
- Modify: `tests/tender_insights/unit/test_section_slice.py` (extend interpret test)

- [ ] **Step 1: Write the failing test**

Append to `tests/tender_insights/unit/test_section_slice.py`:

```python
def test_interpret_workspace_logs_segment_prompts(personnel_dual_row_docx, tmp_path, monkeypatch, caplog) -> None:
    monkeypatch.setenv("OCR_ENABLED", "false")
    monkeypatch.delenv("INTERPRET_LOG_PROMPTS", raising=False)

    ws_path = tmp_path / "ws"
    extract_file(personnel_dual_row_docx, ws_path, overwrite=True)
    extract_outline(ws_path)
    workspace = OutputWorkspace.open_existing(ws_path)
    outline = OutlineTree.model_validate_json(workspace.outline_path.read_text(encoding="utf-8"))
    workspace.outline_path.write_text(outline.model_dump_json(), encoding="utf-8")

    segment_json = json.dumps(
        {
            "disqualification_items": [],
            "scoring_items": [],
            "bid_risk_items": [],
            "directory_requirements": [],
        }
    )
    overview_json = json.dumps(
        {
            "summary": "概要",
            "disqualification_summary": "废标",
            "scoring_summary": "得分",
            "bid_risk_summary": "风险",
            "directory_summary": "目录",
        }
    )
    client = FakeLLMClient(responses=[segment_json, overview_json])

    with caplog.at_level(logging.INFO, logger="tender_insights.interpret.llm"):
        interpret_workspace(workspace, client)

    assert any("interpret_llm_prompt" in r.message for r in caplog.records)
```

Add `import logging` at top of test file.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/tender_insights/unit/test_section_slice.py::test_interpret_workspace_logs_segment_prompts -v`

Expected: FAIL (no log records)

- [ ] **Step 3: Wire extractor**

In `extractor.py`, add imports:

```python
from tender_insights.interpret.llm_logging import log_llm_prompt
```

Inside the segment loop, before `extract_json_model`:

```python
        call_type = "scoring_table" if seg.segment_id.startswith("seg-scoring-") else "segment"
        log_llm_prompt(
            call_type=call_type,
            messages=messages,
            workspace=str(workspace.root),
            segment_id=seg.segment_id,
            section_path=seg.section_path,
            token_estimate=seg.token_estimate,
        )
```

Before `overview = build_overview(...)`:

```python
    if on_progress:
        on_progress(
            "interpret",
            {
                "message": "正在生成概要…",
                "detail": "",
                "current": total_segments,
                "total": max(total_segments, 1),
            },
        )
```

In `overview.py`, before `extract_json_model`:

```python
from tender_insights.interpret.llm_logging import log_llm_prompt
```

```python
    log_llm_prompt(
        call_type="overview",
        messages=messages,
        workspace=None,
    )
```

In `viewer/viewer/__main__.py`:

```python
import logging

from viewer.config import ViewerSettings


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )
    settings = ViewerSettings.load()
    uvicorn.run("viewer.main:app", host=settings.host, port=settings.port, reload=False)
```

Add `import uvicorn` if missing (already present).

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/tender_insights/unit/test_section_slice.py::test_interpret_workspace_logs_segment_prompts tests/tender_insights/unit/test_interpret_llm_logging.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tender_insights/interpret/extractor.py src/tender_insights/interpret/overview.py viewer/viewer/__main__.py tests/tender_insights/unit/test_section_slice.py
git commit -m "feat(interpret): log prompts per segment/overview and show overview progress"
```

---

### Task 5: Scoring table detection helpers

**Files:**
- Create: `src/tender_insights/common/scoring_segments.py`
- Create: `tests/tender_insights/unit/test_scoring_segments.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/tender_insights/unit/test_scoring_segments.py`:

```python
import json

from doc_chunk.models.content_block import ContentBlockRecord, ContentBlocksFile
from doc_chunk.models.table_model import TableSidecar, TablesIndex, TablesIndexEntry
from doc_chunk.workspace.layout import OutputWorkspace

from tender_insights.common.scoring_segments import (
    build_scoring_table_segments,
    inject_scoring_tables_into_markdown,
    is_scoring_section_path,
    is_scoring_table_llm_text,
)


def test_is_scoring_section_path() -> None:
    assert is_scoring_section_path(["第三章 评审办法", "5.2 评分"])
    assert not is_scoring_section_path(["第一章 总则"])


def test_is_scoring_table_llm_text() -> None:
    text = "【表格: 评分表】\n评分说明 | 分值\n商品方案契合度 | 0-2分"
    assert is_scoring_table_llm_text(text)
    assert not is_scoring_table_llm_text("【表格: 人员表】\n姓名 | 职务")


def test_inject_scoring_tables_into_markdown(tmp_path) -> None:
    ws = OutputWorkspace.create(tmp_path / "ws", overwrite=True)
    table_dir = ws.root / "tables"
    table_dir.mkdir(parents=True, exist_ok=True)
    table_path = table_dir / "t-001.json"
    llm_text = "【表格: 评分表】\n商品方案 | 0-2分"
    sidecar = TableSidecar(
        block_index=1,
        layout_type="simple",
        grid_width=2,
        grid={},
        markdown="| 商品方案 | 0-2分 |",
        llm_text=llm_text,
    )
    table_path.write_text(sidecar.model_dump_json(), encoding="utf-8")

    content_md = "# 5.2 评分\n\n采购人：某某\n\n| placeholder |\n"
    ws.content_path.write_text(content_md, encoding="utf-8")
    blocks = ContentBlocksFile(
        blocks=[
            ContentBlockRecord(
                block_index=0,
                block_type="heading",
                char_start=0,
                char_end=10,
            ),
            ContentBlockRecord(
                block_index=1,
                block_type="table",
                char_start=20,
                char_end=40,
                table_ref="tables/t-001.json",
            ),
        ]
    )
    ws.content_blocks_path.write_text(blocks.model_dump_json(), encoding="utf-8")
    ws.tables_index_path.write_text(
        TablesIndex(tables=[TablesIndexEntry(block_index=1, path="tables/t-001.json")]).model_dump_json(),
        encoding="utf-8",
    )

    injected = inject_scoring_tables_into_markdown(
        ws,
        markdown="采购人：某某",
        char_start=10,
        char_end=40,
        blocks=blocks,
    )
    assert "商品方案" in injected
    assert "0-2分" in injected


def test_build_scoring_table_segments_caps_at_five(tmp_path) -> None:
    ws = OutputWorkspace.create(tmp_path / "ws", overwrite=True)
    table_dir = ws.root / "tables"
    table_dir.mkdir(parents=True, exist_ok=True)
    blocks_entries: list[ContentBlockRecord] = []
    index_entries: list[TablesIndexEntry] = []
    for i in range(7):
        ref = f"tables/t-{i:03d}.json"
        llm_text = f"【表格: 评分表{i}】\n评分说明 | 分值\n行 | 0-{i}分"
        (ws.root / ref).write_text(
            TableSidecar(
                block_index=i,
                layout_type="simple",
                grid_width=2,
                grid={},
                markdown="md",
                llm_text=llm_text,
            ).model_dump_json(),
            encoding="utf-8",
        )
        blocks_entries.append(
            ContentBlockRecord(
                block_index=i,
                block_type="table",
                char_start=i * 100,
                char_end=i * 100 + 50,
                table_ref=ref,
            )
        )
        index_entries.append(TablesIndexEntry(block_index=i, path=ref))

    blocks = ContentBlocksFile(blocks=blocks_entries)
    ws.content_blocks_path.write_text(blocks.model_dump_json(), encoding="utf-8")
    ws.tables_index_path.write_text(TablesIndex(tables=index_entries).model_dump_json(), encoding="utf-8")

    segments = build_scoring_table_segments(
        ws,
        blocks=blocks,
        host_section_path=["第六章 响应文件格式"],
        max_segments=5,
    )
    assert len(segments) == 5
    assert segments[0].segment_id == "seg-scoring-001"
    assert "0-0分" in segments[0].markdown
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/tender_insights/unit/test_scoring_segments.py -v`

Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: Implement scoring_segments.py**

Create `src/tender_insights/common/scoring_segments.py`:

```python
from __future__ import annotations

import re

from doc_chunk.chunk.tokenizer import estimate_tokens
from doc_chunk.models.content_block import ContentBlocksFile
from doc_chunk.table.access import load_table_model
from doc_chunk.workspace.layout import OutputWorkspace

from tender_insights.common.segment_planner import Segment

_SCORING_PATH_KEYWORDS = ("评分", "评审办法", "评标", "评审", "分值", "得分")
_SCORING_TABLE_HEADER_KEYWORDS = ("评分说明", "分值", "得分")
_SCORE_PATTERN = re.compile(r"\d+\s*[-~–—]\s*\d+\s*分")
_INJECT_LOOKAHEAD_CHARS = 8000
_SHORT_SCORING_SECTION_CHARS = 200


def is_scoring_section_path(section_path: list[str]) -> bool:
    haystack = " ".join(section_path)
    return any(kw in haystack for kw in _SCORING_PATH_KEYWORDS)


def is_scoring_table_llm_text(llm_text: str) -> bool:
    if any(kw in llm_text for kw in _SCORING_TABLE_HEADER_KEYWORDS):
        return True
    return bool(_SCORE_PATTERN.search(llm_text))


def _iter_scoring_table_blocks(
    workspace: OutputWorkspace,
    blocks: ContentBlocksFile,
    *,
    char_start: int | None = None,
    char_end: int | None = None,
) -> list[tuple[ContentBlockRecord, str]]:
    found: list[tuple[ContentBlockRecord, str]] = []
    for block in blocks.blocks:
        if block.block_type != "table" or not block.table_ref:
            continue
        if char_start is not None and char_end is not None:
            window_end = char_end + _INJECT_LOOKAHEAD_CHARS
            if block.char_end <= char_start or block.char_start >= window_end:
                continue
        sidecar = load_table_model(workspace, block.table_ref)
        llm_text = sidecar.llm_text.strip()
        if is_scoring_table_llm_text(llm_text):
            found.append((block, llm_text))
    return found


def inject_scoring_tables_into_markdown(
    workspace: OutputWorkspace,
    *,
    markdown: str,
    char_start: int,
    char_end: int,
    blocks: ContentBlocksFile,
) -> str:
    tables = _iter_scoring_table_blocks(
        workspace, blocks, char_start=char_start, char_end=char_end
    )
    if not tables:
        return markdown
    parts = [markdown.rstrip(), ""]
    for _block, llm_text in tables:
        parts.append(llm_text)
    return "\n\n".join(p for p in parts if p)


def build_scoring_table_segments(
    workspace: OutputWorkspace,
    *,
    blocks: ContentBlocksFile,
    host_section_path: list[str] | None = None,
    max_segments: int = 5,
) -> list[Segment]:
    segments: list[Segment] = []
    seen_refs: set[str] = set()
    for block, llm_text in _iter_scoring_table_blocks(workspace, blocks):
        if not block.table_ref or block.table_ref in seen_refs:
            continue
        seen_refs.add(block.table_ref)
        seg_id = f"seg-scoring-{len(segments) + 1:03d}"
        md = f"# 评分表\n\n{llm_text}"
        segments.append(
            Segment(
                segment_id=seg_id,
                section_path=host_section_path or [],
                markdown=md,
                char_start=block.char_start,
                char_end=block.char_end,
                token_estimate=estimate_tokens(md),
            )
        )
        if len(segments) >= max_segments:
            break
    return segments
```

Note: `build_scoring_table_segments` uses global scan (no char window) for dedicated segments — dedupe by `table_ref`.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/tender_insights/unit/test_scoring_segments.py -v`

Expected: PASS (adjust `content_blocks_path` / `tables_index_path` property names on `OutputWorkspace` if test setup differs — read `doc_chunk/workspace/layout.py` and fix paths in test to match actual workspace API)

- [ ] **Step 5: Commit**

```bash
git add src/tender_insights/common/scoring_segments.py tests/tender_insights/unit/test_scoring_segments.py
git commit -m "feat(interpret): add scoring table detection and segment builders"
```

---

### Task 6: Integrate B+A and C into `plan_segments`

**Files:**
- Modify: `src/tender_insights/common/segment_planner.py`
- Modify: `tests/tender_insights/unit/test_segment_planner.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/tender_insights/unit/test_segment_planner.py`:

```python
from doc_chunk.models.content_block import ContentBlockRecord, ContentBlocksFile
from doc_chunk.models.table_model import TableSidecar, TablesIndex, TablesIndexEntry

from tender_insights.common.scoring_segments import is_scoring_section_path


def test_plan_segments_injects_scoring_table_into_short_section(tmp_path) -> None:
    ws = OutputWorkspace.create(tmp_path / "ws", overwrite=True)
    table_dir = ws.root / "tables"
    table_dir.mkdir(parents=True, exist_ok=True)
    ref = "tables/t-001.json"
    llm_text = "【表格: 评分表】\n商品方案契合度 | 0-2分"
    (ws.root / ref).write_text(
        TableSidecar(
            block_index=1,
            layout_type="simple",
            grid_width=2,
            grid={},
            markdown="| md |",
            llm_text=llm_text,
        ).model_dump_json(),
        encoding="utf-8",
    )
    md = "# 第三章 评审办法\n\n## 5.2 评分\n\n采购人：测试\n\n| t |\n"
    ws.content_path.write_text(md, encoding="utf-8")
    blocks = ContentBlocksFile(
        blocks=[
            ContentBlockRecord(
                block_index=1,
                block_type="table",
                char_start=30,
                char_end=50,
                table_ref=ref,
            )
        ]
    )
    blocks_path = ws.root / "content.blocks.json"
    blocks_path.write_text(blocks.model_dump_json(), encoding="utf-8")
    (ws.root / "tables" / "index.json").write_text(
        TablesIndex(tables=[TablesIndexEntry(block_index=1, path=ref)]).model_dump_json(),
        encoding="utf-8",
    )
    _write_outline(ws)
    source = InterpretSource(markdown=md, source_path=ws.content_path, blocks=blocks, ocr_image_count=0)
    outline = OutlineTree.model_validate_json(ws.outline_path.read_text(encoding="utf-8"))

    segments = plan_segments(
        ws,
        source,
        outline,
        config=InsightsConfig(segment_min_tokens=10, segment_max_tokens=5000),
    )
    scoring_seg = next(
        s for s in segments if is_scoring_section_path(s.section_path) or "商品方案" in s.markdown
    )
    assert "商品方案" in scoring_seg.markdown
    assert "0-2分" in scoring_seg.markdown


def test_plan_segments_appends_scoring_dedicated_segments(tmp_path) -> None:
    ws = OutputWorkspace.create(tmp_path / "ws", overwrite=True)
    ref = "tables/t-001.json"
    (ws.root / "tables").mkdir(parents=True, exist_ok=True)
    llm_text = "【表格: 评分表】\n评分说明 | 分值\n仓储方案 | 0-3分"
    (ws.root / ref).write_text(
        TableSidecar(
            block_index=1,
            layout_type="simple",
            grid_width=2,
            grid={},
            markdown="md",
            llm_text=llm_text,
        ).model_dump_json(),
        encoding="utf-8",
    )
    md = "# 第六章 响应文件格式\n\n正文混排\n\n| t |\n"
    ws.content_path.write_text(md, encoding="utf-8")
    blocks = ContentBlocksFile(
        blocks=[
            ContentBlockRecord(
                block_index=1,
                block_type="table",
                char_start=20,
                char_end=40,
                table_ref=ref,
            )
        ]
    )
    (ws.root / "content.blocks.json").write_text(blocks.model_dump_json(), encoding="utf-8")
    (ws.root / "tables" / "index.json").write_text(
        TablesIndex(tables=[TablesIndexEntry(block_index=1, path=ref)]).model_dump_json(),
        encoding="utf-8",
    )
    _write_outline(ws)
    source = InterpretSource(markdown=md, source_path=ws.content_path, blocks=blocks, ocr_image_count=0)
    outline = OutlineTree.model_validate_json(ws.outline_path.read_text(encoding="utf-8"))

    segments = plan_segments(ws, source, outline, config=InsightsConfig(segment_min_tokens=10, segment_max_tokens=5000))
    dedicated = [s for s in segments if s.segment_id.startswith("seg-scoring-")]
    assert len(dedicated) == 1
    assert "仓储方案" in dedicated[0].markdown
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/tender_insights/unit/test_segment_planner.py::test_plan_segments_injects_scoring_table_into_short_section -v`

Expected: FAIL

- [ ] **Step 3: Modify plan_segments**

In `segment_planner.py`, add imports:

```python
from tender_insights.common.scoring_segments import (
    build_scoring_table_segments,
    inject_scoring_tables_into_markdown,
    is_scoring_section_path,
)
```

Replace the tail of `plan_segments` (after building primary segments):

```python
    segments: list[Segment] = []
    for idx, seg in enumerate(raw, start=1):
        llm_md = slice_for_llm(
            workspace,
            source_md,
            seg.char_start,
            seg.char_end,
            blocks=source.blocks,
        )
        if not llm_md.strip():
            continue
        if (
            source.blocks is not None
            and is_scoring_section_path(seg.section_path)
            and len(llm_md.strip()) < 200
        ):
            llm_md = inject_scoring_tables_into_markdown(
                workspace,
                markdown=llm_md,
                char_start=seg.char_start,
                char_end=seg.char_end,
                blocks=source.blocks,
            )
        segments.append(
            Segment(
                segment_id=f"seg-{idx:03d}",
                section_path=seg.section_path,
                markdown=llm_md,
                char_start=seg.char_start,
                char_end=seg.char_end,
                token_estimate=estimate_tokens(llm_md),
            )
        )

    if source.blocks is not None:
        host_path = segments[-1].section_path if segments else []
        dedicated = build_scoring_table_segments(
            workspace,
            blocks=source.blocks,
            host_section_path=host_path,
            max_segments=5,
        )
        existing_markdown = {s.markdown.strip() for s in segments}
        for seg in dedicated:
            if seg.markdown.strip() in existing_markdown:
                continue
            segments.append(seg)
            existing_markdown.add(seg.markdown.strip())

    return segments
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/tender_insights/unit/test_segment_planner.py tests/tender_insights/unit/test_scoring_segments.py -v`

Expected: PASS (fix workspace path properties per `OutputWorkspace` if needed)

- [ ] **Step 5: Commit**

```bash
git add src/tender_insights/common/segment_planner.py tests/tender_insights/unit/test_segment_planner.py
git commit -m "feat(interpret): inject scoring tables into short sections and add dedicated scoring segments"
```

---

### Task 7: Prompt appendices for mixed segments and scoring-table segments

**Files:**
- Modify: `src/tender_insights/interpret/prompts.py`
- Modify: `tests/tender_insights/unit/test_interpret_prompts.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/tender_insights/unit/test_interpret_prompts.py`:

```python
def test_build_segment_prompt_mixed_format_and_scoring_table() -> None:
    md = "【表格: 评标表】\n评分说明 | 分值\n商品方案 | 0-2分\n\n一、投标函\n"
    prompt = build_segment_prompt(
        "seg-024",
        ["第六章 响应文件格式"],
        md,
    )
    assert "directory_requirements" in prompt
    assert "scoring_items" in prompt
    assert "禁止只提取目录" in prompt


def test_build_segment_prompt_scoring_table_segment() -> None:
    md = "【表格: 评标表】\n评分说明 | 分值\n商品方案 | 0-2分"
    prompt = build_segment_prompt("seg-scoring-001", ["第三章 评审办法"], md)
    assert "directory_requirements 返回 []" in prompt
    assert "完整提取全部 scoring_items" in prompt
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/tender_insights/unit/test_interpret_prompts.py::test_build_segment_prompt_mixed_format_and_scoring_table -v`

Expected: FAIL (`禁止只提取目录` not in prompt)

- [ ] **Step 3: Implement appendices**

In `prompts.py`, add constants:

```python
_MIXED_FORMAT_SCORING_APPENDIX = (
    "【分段提示】本段同时含投标文件格式与评分表，须同时提取 directory_requirements（structure 树）"
    "与 scoring_items（含 children 细则），禁止只提取目录而忽略评分表。"
)
_SCORING_TABLE_ONLY_APPENDIX = (
    "【分段提示】本段仅含评分表，须完整提取全部 scoring_items + children；directory_requirements 返回 []。"
)

_FORMAT_PATH_KEYWORDS = ("格式", "响应文件", "投标文件组成")
_TABLE_MARKER = "【表格:"
_SCORING_TABLE_COLUMN_HINTS = ("评分说明", "分值", "得分")
```

Add helpers:

```python
def _is_mixed_format_scoring_section(section_path: list[str], markdown: str) -> bool:
    path = " ".join(section_path)
    if not any(kw in path for kw in _FORMAT_PATH_KEYWORDS):
        return False
    if _TABLE_MARKER not in markdown:
        return False
    return any(hint in markdown for hint in _SCORING_TABLE_COLUMN_HINTS)


def _is_scoring_table_segment(segment_id: str) -> bool:
    return segment_id.startswith("seg-scoring-")
```

Update `build_segment_appendix` to accept optional `segment_id` and `markdown`, or handle in `build_segment_prompt`:

```python
def build_segment_prompt(segment_id: str, section_path: list[str], markdown: str) -> str:
    path = " > ".join(section_path) if section_path else "(root)"
    appendix_parts: list[str] = []
    base_appendix = build_segment_appendix(section_path)
    if base_appendix:
        appendix_parts.append(base_appendix)
    if _is_scoring_table_segment(segment_id):
        appendix_parts.append(_SCORING_TABLE_ONLY_APPENDIX)
    elif _is_mixed_format_scoring_section(section_path, markdown):
        appendix_parts.append(_MIXED_FORMAT_SCORING_APPENDIX)
    appendix = "\n".join(appendix_parts)
    parts = [f"segment_id: {segment_id}", f"section_path: {path}"]
    if appendix:
        parts.append(appendix)
    parts.append(f"\n正文:\n{markdown}")
    return "\n".join(parts)
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/tender_insights/unit/test_interpret_prompts.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tender_insights/interpret/prompts.py tests/tender_insights/unit/test_interpret_prompts.py
git commit -m "feat(interpret): strengthen prompts for mixed and scoring-only segments"
```

---

### Task 8: Documentation + manual regression checklist

**Files:**
- Modify: `viewer/README.md`
- Modify: `.cursor/skills/tender-interpret/SKILL.md`

- [ ] **Step 1: Update viewer README**

Add section under configuration:

```markdown
### Interpret prompt logging

| Variable | Default | Description |
|----------|---------|-------------|
| `INTERPRET_LOG_PROMPTS` | `1` | Log full LLM messages to stderr (`0` to disable) |
| `INTERPRET_LOG_PROMPTS_DIR` | (unset) | If set, also write `{segment_id}.json` per call |

Example:

```bash
INTERPRET_LOG_PROMPTS=1 INTERPRET_LOG_PROMPTS_DIR=/tmp/interpret-prompts python -m viewer
```
```

- [ ] **Step 2: Update tender-interpret SKILL**

Document:
- `seg-scoring-*` dedicated segments (max 5 per document)
- `INTERPRET_LOG_PROMPTS` env vars
- Viewer renders `scoring_items[].children[]`

- [ ] **Step 3: Run full test suite**

Run:

```bash
.venv/bin/pytest tests/tender_insights/unit/test_segment_planner.py tests/tender_insights/unit/test_scoring_segments.py tests/tender_insights/unit/test_interpret_llm_logging.py tests/tender_insights/unit/test_interpret_prompts.py tests/tender_insights/contract/test_interpretation_schema.py viewer/tests/ -v
```

Expected: all PASS

- [ ] **Step 4: Manual regression (铁建样本)**

1. `INTERPRET_LOG_PROMPTS=1 python -m viewer`
2. Upload 铁建福利商城 docx → 等待完成
3. Terminal: confirm `interpret_llm_prompt` lines for each `seg-*` and `seg-scoring-*` plus `overview`
4. 得分项 Tab: 可见「商品方案」三条 0–2 分细则
5. `interpretation.json` 搜索「商品方案」「0-2分」非 missing

- [ ] **Step 5: Commit**

```bash
git add viewer/README.md .cursor/skills/tender-interpret/SKILL.md
git commit -m "docs: interpret quality viewer logging and scoring segment notes"
```

---

## Spec Coverage Self-Review

| Spec section | Task |
|--------------|------|
| §3.1 B+A 空壳段修复 | Task 5, 6 |
| §3.2 C 评分专段 + Prompt | Task 5, 6, 7 |
| §3.4 Viewer children/structure/overview | Task 1, 2 |
| §3.6 overview 进度 | Task 4 |
| §3.7 LLM 提示词日志 | Task 3, 4 |
| §3.8 .env 加载 | 已实现，Task 8 manual regression |
| §2.0 全分段提取（不恢复路由） | 无代码 change — preserved by design |
| §3.5 目录 P1 | Task 2 (Viewer tree) |
| 铁建样本验收 | Task 8 manual |

**Placeholder scan:** No TBD/TODO/similar-task references.

**Type consistency:** `Segment.segment_id` uses `seg-scoring-NNN`; extractor `call_type` and prompts `_is_scoring_table_segment` both key off `seg-scoring-` prefix.

**Note for implementer:** Verify `OutputWorkspace` property names for `content.blocks.json` and tables index in Task 5 tests — use `ws.content_blocks_path` from `doc_chunk/workspace/layout.py` if paths differ from test literals.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-24-interpret-quality-viewer.md`. Two execution options:

**1. Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
