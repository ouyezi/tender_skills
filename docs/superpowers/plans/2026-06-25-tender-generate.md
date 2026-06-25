# tender-generate 投标目录生成 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在招标文件已解读的前提下，生成投标响应目录方案（树状结构 + 概要 + 撰写规范 + 废标/评分/模板引用），支持按步/一次性模式、预览 accept 落盘，并提供 Viewer 测试页。

**Architecture:** 在 `tender_insights/gen_catalog/` 新增独立模块；每步 LLM 输入/输出均为完整 `BidOutline` 树；`gen_catalog/session.json` 驱动按步状态机；复用 `common.llm_extractor` 与 `interpret.llm_logging` 追加 `llm_calls.jsonl`；Viewer 复用 interpret 会话与 job 轮询模式。

**Tech Stack:** Python 3.11+、Pydantic v2、Typer、FastAPI、pytest、FakeLLMClient、现有 `tender_insights` / `viewer` 模式

**Spec:** `docs/superpowers/specs/2026-06-25-tender-generate-design.md`

---

## File Map

| File | Responsibility |
|------|----------------|
| `src/tender_insights/gen_catalog/__init__.py` | 包入口 |
| `src/tender_insights/gen_catalog/models.py` | `BidOutlineNode`、`BidOutlineFile`、`GenCatalogSession`、LLM 响应模型 |
| `src/tender_insights/gen_catalog/queue.py` | 前序遍历、`node_queue` 计算、跳过已完成节点 |
| `src/tender_insights/gen_catalog/session.py` | 读写 `gen_catalog/session.json`、restart |
| `src/tender_insights/gen_catalog/prerequisites.py` | 前置校验与降级警告 |
| `src/tender_insights/gen_catalog/excerpt.py` | 节点相关摘录（≤2000 字，<200 拼接） |
| `src/tender_insights/gen_catalog/context.py` | 组装 initial/refine user prompt 块 |
| `src/tender_insights/gen_catalog/prompts.py` | 固定 `GEN_CATALOG_INITIAL_SYSTEM` / `GEN_CATALOG_REFINE_SYSTEM` |
| `src/tender_insights/gen_catalog/extractor.py` | `gen_catalog_workspace()` 主流程 |
| `src/tender_insights/gen_catalog/accept.py` | draft → `bid_outline.json` |
| `src/tender_insights/gen_catalog/render.py` | draft → `bid_outline.md` |
| `src/tender_insights/api.py` | 暴露 `run_gen_catalog_job()` / `continue_gen_catalog()` / `accept_gen_catalog()` |
| `src/tender_insights/cli/main.py` | `gen-catalog` 子命令 |
| `src/tender_insights/config.py` | `gen_catalog_excerpt_max_chars` 等 |
| `tests/helpers/gen_catalog_fake_llm.py` | FakeLLM 按 call_type 返回 JSON |
| `tests/tender_insights/contract/test_bid_outline_schema.py` | schema 契约 |
| `tests/tender_insights/unit/test_gen_catalog.py` | 核心单元/集成测试 |
| `viewer/viewer/services/gen_catalog_pipeline.py` | 后台 job + 进度 |
| `viewer/viewer/routes/gen_catalog.py` | REST + 静态页路由 |
| `viewer/viewer/static/gen-catalog.html` | 测试页 |
| `viewer/viewer/static/gen-catalog.js` | 树预览、进度、按钮 |
| `viewer/viewer/models.py` | 扩展 `job_kind="gen_catalog"` |
| `viewer/viewer/main.py` | 注册 gen-catalog 路由与页面 |

---

### Task 1: BidOutline 数据模型与契约测试

**Files:**
- Create: `src/tender_insights/gen_catalog/__init__.py`
- Create: `src/tender_insights/gen_catalog/models.py`
- Create: `tests/tender_insights/contract/test_bid_outline_schema.py`

- [ ] **Step 1: Write the failing contract test**

```python
# tests/tender_insights/contract/test_bid_outline_schema.py
import jsonschema

from tender_insights.gen_catalog.models import BidOutlineFile


def test_bid_outline_schema_accepts_fixture() -> None:
    schema = BidOutlineFile.model_json_schema()
    fixture = {
        "schema_version": "1.0",
        "source_workspace": "/tmp/ws",
        "generated_at": "2026-06-25T00:00:00+00:00",
        "accepted_at": None,
        "interpretation_schema": "1.2",
        "mode": "step",
        "status": "paused",
        "step_index": 1,
        "step_total": 3,
        "overview_snapshot": {"summary": "概要"},
        "brief_snapshot": {"summary_text": "brief"},
        "root": {
            "id": "bid-root",
            "title": "投标文件",
            "level": 0,
            "order": 0,
            "mandatory": True,
            "number": None,
            "summary": "",
            "writing_spec": "",
            "template_ref": None,
            "scoring_refs": ["sc-001"],
            "disqualification_refs": ["dq-001"],
            "bid_risk_refs": [],
            "source_refs": [],
            "children": [
                {
                    "id": "bid-001",
                    "title": "投标函",
                    "level": 1,
                    "order": 1,
                    "mandatory": True,
                    "number": "1",
                    "summary": "投标承诺",
                    "writing_spec": "须法定代表人签字盖章",
                    "template_ref": {
                        "template_id": "tpl-001",
                        "file": "templates/tpl-001.md",
                        "type": "commitment",
                    },
                    "scoring_refs": [],
                    "disqualification_refs": ["dq-001"],
                    "bid_risk_refs": [],
                    "source_refs": [
                        {
                            "section_path": ["格式"],
                            "char_start": 10,
                            "char_end": 50,
                            "excerpt": "投标函格式见附件",
                        }
                    ],
                    "children": [],
                }
            ],
        },
    }
    jsonschema.validate(fixture, schema)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/tender_insights/contract/test_bid_outline_schema.py -v`  
Expected: FAIL `ModuleNotFoundError: tender_insights.gen_catalog`

- [ ] **Step 3: Implement models**

```python
# src/tender_insights/gen_catalog/__init__.py
"""Bid outline generation from interpretation artifacts."""

# src/tender_insights/gen_catalog/models.py
from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class TemplateRef(BaseModel):
    template_id: str
    file: str
    type: str


class SourceRef(BaseModel):
    section_path: list[str] = Field(default_factory=list)
    char_start: int | None = None
    char_end: int | None = None
    excerpt: str | None = None


class BidOutlineNode(BaseModel):
    id: str
    title: str
    level: int
    order: int
    mandatory: bool = True
    number: str | None = None
    summary: str = ""
    writing_spec: str = ""
    template_ref: TemplateRef | None = None
    scoring_refs: list[str] = Field(default_factory=list)
    disqualification_refs: list[str] = Field(default_factory=list)
    bid_risk_refs: list[str] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(default_factory=list)
    children: list[BidOutlineNode] = Field(default_factory=list)


class BidOutlineFile(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    source_workspace: str
    generated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    accepted_at: str | None = None
    interpretation_schema: str
    mode: Literal["step", "auto"]
    status: Literal["running", "paused", "awaiting_accept", "accepted", "failed"]
    step_index: int = 0
    step_total: int = 0
    overview_snapshot: dict
    brief_snapshot: dict | None = None
    root: BidOutlineNode


class BidOutlineLLMResponse(BaseModel):
    outline: BidOutlineNode
    changes_summary: str = ""


class GenCatalogSession(BaseModel):
    mode: Literal["step", "auto"]
    status: Literal["running", "paused", "awaiting_accept", "failed"]
    step_index: int = 0
    step_total: int = 0
    current_node_id: str | None = None
    current_node_title: str | None = None
    node_queue: list[str] = Field(default_factory=list)
    completed_steps: list[str] = Field(default_factory=list)
    job_id: str | None = None
    error: str | None = None
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/tender_insights/contract/test_bid_outline_schema.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tender_insights/gen_catalog/ tests/tender_insights/contract/test_bid_outline_schema.py
git commit -m "feat(gen-catalog): add BidOutline pydantic models and schema contract test"
```

---

### Task 2: 节点队列与前序遍历

**Files:**
- Create: `src/tender_insights/gen_catalog/queue.py`
- Create: `tests/tender_insights/unit/test_gen_catalog.py`（本节先写 queue 相关测试）

- [ ] **Step 1: Write failing tests**

```python
# append to tests/tender_insights/unit/test_gen_catalog.py
from tender_insights.gen_catalog.models import BidOutlineNode
from tender_insights.gen_catalog.queue import build_node_queue, find_node, next_pending_node_id


def _node(node_id: str, title: str, children: list | None = None) -> BidOutlineNode:
    return BidOutlineNode(
        id=node_id,
        title=title,
        level=1,
        order=1,
        children=children or [],
    )


def test_build_node_queue_preorder() -> None:
    root = BidOutlineNode(
        id="bid-root",
        title="root",
        level=0,
        order=0,
        children=[
            _node("bid-001", "A", [_node("bid-002", "A1")]),
            _node("bid-003", "B"),
        ],
    )
    assert build_node_queue(root) == ["bid-001", "bid-002", "bid-003"]


def test_next_pending_node_id_skips_completed() -> None:
    queue = ["bid-001", "bid-002", "bid-003"]
    completed = ["initial", "bid-001"]
    assert next_pending_node_id(queue, completed) == "bid-002"


def test_find_node_returns_subtree() -> None:
    child = _node("bid-002", "child")
    root = BidOutlineNode(id="bid-root", title="root", level=0, order=0, children=[child])
    found = find_node(root, "bid-002")
    assert found is not None
    assert found.title == "child"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/tender_insights/unit/test_gen_catalog.py::test_build_node_queue_preorder -v`  
Expected: FAIL `ImportError`

- [ ] **Step 3: Implement queue helpers**

```python
# src/tender_insights/gen_catalog/queue.py
from __future__ import annotations

from tender_insights.gen_catalog.models import BidOutlineNode


def build_node_queue(root: BidOutlineNode) -> list[str]:
    queue: list[str] = []

    def walk(node: BidOutlineNode) -> None:
        if node.id != "bid-root":
            queue.append(node.id)
        for child in node.children:
            walk(child)

    for child in root.children:
        walk(child)
    return queue


def find_node(root: BidOutlineNode, node_id: str) -> BidOutlineNode | None:
    if root.id == node_id:
        return root

    for child in root.children:
        found = find_node(child, node_id)
        if found is not None:
            return found
    return None


def next_pending_node_id(queue: list[str], completed_steps: list[str]) -> str | None:
    done = set(completed_steps)
    for node_id in queue:
        if node_id not in done:
            return node_id
    return None


def compute_step_total(root: BidOutlineNode) -> int:
    return 1 + len(build_node_queue(root))
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/tender_insights/unit/test_gen_catalog.py -k queue -v`  
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/tender_insights/gen_catalog/queue.py tests/tender_insights/unit/test_gen_catalog.py
git commit -m "feat(gen-catalog): add preorder node queue helpers"
```

---

### Task 3: 摘录选取（excerpt）

**Files:**
- Create: `src/tender_insights/gen_catalog/excerpt.py`
- Modify: `src/tender_insights/config.py`
- Modify: `tests/tender_insights/unit/test_gen_catalog.py`

- [ ] **Step 1: Write failing tests**

```python
from tender_insights.gen_catalog.excerpt import pick_node_excerpt


def test_pick_node_excerpt_respects_max_chars() -> None:
    text = "a" * 3000
    excerpt = pick_node_excerpt(text, node_title="技术方案", max_chars=2000)
    assert len(excerpt) <= 2000


def test_pick_node_excerpt_merges_short_tail() -> None:
    text = "短段\n\n" + ("b" * 500)
    excerpt = pick_node_excerpt(text, node_title="短段", max_chars=2000, min_chars=200)
    assert "bbbb" in excerpt
    assert len(excerpt) >= 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/tender_insights/unit/test_gen_catalog.py -k excerpt -v`  
Expected: FAIL

- [ ] **Step 3: Add config + implement excerpt**

```python
# src/tender_insights/config.py — add fields:
    gen_catalog_excerpt_max_chars: int = 2000
    gen_catalog_excerpt_min_chars: int = 200

# in from_env():
            gen_catalog_excerpt_max_chars=_env_int("GEN_CATALOG_EXCERPT_MAX_CHARS", 2000),
            gen_catalog_excerpt_min_chars=_env_int("GEN_CATALOG_EXCERPT_MIN_CHARS", 200),
```

```python
# src/tender_insights/gen_catalog/excerpt.py
from __future__ import annotations


def _paragraphs(text: str) -> list[str]:
    parts = [p.strip() for p in text.split("\n\n") if p.strip()]
    return parts or [text.strip()]


def pick_node_excerpt(
    markdown: str,
    *,
    node_title: str,
    max_chars: int = 2000,
    min_chars: int = 200,
) -> str:
    paragraphs = _paragraphs(markdown)
    lowered_title = node_title.strip().lower()
    start_idx = 0
    for idx, para in enumerate(paragraphs):
        if lowered_title and lowered_title in para.lower():
            start_idx = idx
            break

    selected: list[str] = []
    total = 0
    idx = start_idx
    while idx < len(paragraphs) and total < max_chars:
        piece = paragraphs[idx]
        if not selected and len(piece) < min_chars and idx + 1 < len(paragraphs):
            combined = piece
            j = idx + 1
            while len(combined) < min_chars and j < len(paragraphs):
                combined = combined + "\n\n" + paragraphs[j]
                j += 1
            piece = combined[:max_chars]
            idx = j
        else:
            idx += 1
        if total + len(piece) > max_chars:
            piece = piece[: max_chars - total]
        if piece:
            selected.append(piece)
            total += len(piece)
        if total >= max_chars:
            break
    return "\n\n".join(selected).strip()
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/tender_insights/unit/test_gen_catalog.py -k excerpt -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tender_insights/gen_catalog/excerpt.py src/tender_insights/config.py tests/tender_insights/unit/test_gen_catalog.py
git commit -m "feat(gen-catalog): add node excerpt picker with min/max char limits"
```

---

### Task 4: 前置校验与 session 读写

**Files:**
- Create: `src/tender_insights/gen_catalog/prerequisites.py`
- Create: `src/tender_insights/gen_catalog/session.py`
- Modify: `tests/tender_insights/unit/test_gen_catalog.py`

- [ ] **Step 1: Write failing tests**

```python
import json
from pathlib import Path

import pytest
from doc_chunk.workspace.layout import OutputWorkspace

from tender_insights.gen_catalog.prerequisites import PrerequisiteReport, validate_prerequisites
from tender_insights.gen_catalog.session import load_session, save_session, clear_gen_catalog_artifacts
from tender_insights.gen_catalog.models import GenCatalogSession
from tender_insights.interpret.models import (
    DirectoryOutline,
    DirectoryOutlineNode,
    InterpretationFile,
    InterpretationOverview,
)


def _minimal_interpretation(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    data = InterpretationFile(
        source_workspace=str(ws),
        overview=InterpretationOverview(
            summary="s",
            disqualification_summary="d",
            scoring_summary="sc",
            bid_risk_summary="b",
            directory_summary="dir",
        ),
        directory_outline=DirectoryOutline(
            nodes=[DirectoryOutlineNode(id="dir-001", title="投标函", level=1, order=1)]
        ),
    )
    path = ws / "interpretation.json"
    path.write_text(data.model_dump_json(), encoding="utf-8")
    return ws


def test_validate_prerequisites_requires_interpretation(tmp_path: Path) -> None:
    ws = OutputWorkspace(tmp_path / "empty")
    ws.root.mkdir(parents=True)
    with pytest.raises(FileNotFoundError):
        validate_prerequisites(ws)


def test_validate_prerequisites_warns_missing_brief(tmp_path: Path) -> None:
    ws_root = _minimal_interpretation(tmp_path)
    report = validate_prerequisites(OutputWorkspace(ws_root))
    assert isinstance(report, PrerequisiteReport)
    assert report.warnings


def test_session_roundtrip(tmp_path: Path) -> None:
    ws = OutputWorkspace(_minimal_interpretation(tmp_path))
    session = GenCatalogSession(mode="step", status="paused", step_index=1, step_total=3)
    save_session(ws, session)
    loaded = load_session(ws)
    assert loaded.step_index == 1
    clear_gen_catalog_artifacts(ws)
    assert not (ws.root / "gen_catalog" / "session.json").exists()
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `.venv/bin/pytest tests/tender_insights/unit/test_gen_catalog.py -k "prerequisites or session" -v`

- [ ] **Step 3: Implement**

```python
# src/tender_insights/gen_catalog/prerequisites.py
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from doc_chunk.workspace.layout import OutputWorkspace
from tender_insights.brief.models import TenderBriefFile
from tender_insights.interpret.models import InterpretationFile
from tender_insights.template.models import TemplatesIndexFile


@dataclass(slots=True)
class PrerequisiteReport:
    interpretation: InterpretationFile
    brief: TenderBriefFile | None = None
    templates: TemplatesIndexFile | None = None
    warnings: list[str] = field(default_factory=list)


def validate_prerequisites(
    workspace: OutputWorkspace,
    *,
    overwrite: bool = False,
) -> PrerequisiteReport:
    interpretation_path = workspace.root / "interpretation.json"
    if not interpretation_path.is_file():
        raise FileNotFoundError(f"interpretation.json not found in {workspace.root}")

    interpretation = InterpretationFile.model_validate_json(
        interpretation_path.read_text(encoding="utf-8")
    )
    if not interpretation.directory_requirements and not interpretation.directory_outline.nodes:
        raise ValueError("interpretation has no directory requirements or outline nodes")

    accepted = workspace.root / "bid_outline.json"
    if accepted.is_file() and not overwrite:
        raise FileExistsError("bid_outline.json already exists; pass overwrite=True")

    warnings: list[str] = []
    brief = None
    brief_path = workspace.root / "tender_brief.json"
    if brief_path.is_file():
        brief = TenderBriefFile.model_validate_json(brief_path.read_text(encoding="utf-8"))
    else:
        warnings.append("tender_brief.json missing; continuing without brief snapshot")

    templates = None
    templates_path = workspace.root / "templates" / "index.json"
    if templates_path.is_file():
        templates = TemplatesIndexFile.model_validate_json(templates_path.read_text(encoding="utf-8"))
    else:
        warnings.append("templates/index.json missing; template_ref will remain null")

    return PrerequisiteReport(
        interpretation=interpretation,
        brief=brief,
        templates=templates,
        warnings=warnings,
    )
```

```python
# src/tender_insights/gen_catalog/session.py
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from doc_chunk.workspace.layout import OutputWorkspace
from tender_insights.gen_catalog.models import GenCatalogSession

SESSION_REL = Path("gen_catalog") / "session.json"
DRAFT_NAME = "bid_outline.draft.json"


def session_path(workspace: OutputWorkspace) -> Path:
    return workspace.root / SESSION_REL


def load_session(workspace: OutputWorkspace) -> GenCatalogSession:
    path = session_path(workspace)
    if not path.is_file():
        raise FileNotFoundError("gen_catalog session not found")
    return GenCatalogSession.model_validate_json(path.read_text(encoding="utf-8"))


def save_session(workspace: OutputWorkspace, session: GenCatalogSession) -> None:
    session.updated_at = datetime.now(UTC).isoformat()
    path = session_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(session.model_dump_json(), encoding="utf-8")


def clear_gen_catalog_artifacts(workspace: OutputWorkspace) -> None:
    for rel in (SESSION_REL, Path(DRAFT_NAME)):
        target = workspace.root / rel
        if target.is_file():
            target.unlink()
```

- [ ] **Step 4: Run tests — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add src/tender_insights/gen_catalog/prerequisites.py src/tender_insights/gen_catalog/session.py tests/tender_insights/unit/test_gen_catalog.py
git commit -m "feat(gen-catalog): add prerequisite validation and session persistence"
```

---

### Task 5: 提示词与上下文组装

**Files:**
- Create: `src/tender_insights/gen_catalog/prompts.py`
- Create: `src/tender_insights/gen_catalog/context.py`
- Modify: `tests/tender_insights/unit/test_gen_catalog.py`

- [ ] **Step 1: Write failing test**

```python
from tender_insights.gen_catalog.context import build_initial_user_prompt, build_refine_user_prompt
from tender_insights.gen_catalog.prompts import GEN_CATALOG_INITIAL_SYSTEM, GEN_CATALOG_REFINE_SYSTEM


def test_prompts_are_static() -> None:
    assert "JSON" in GEN_CATALOG_INITIAL_SYSTEM
    assert "完整" in GEN_CATALOG_REFINE_SYSTEM


def test_build_initial_user_prompt_includes_overview() -> None:
    # use PrerequisiteReport from Task 4 fixture helpers
    ...
    user = build_initial_user_prompt(report)
    assert "概要" in user or "summary" in user.lower()
```

- [ ] **Step 2: Implement prompts + context**

```python
# src/tender_insights/gen_catalog/prompts.py
GEN_CATALOG_INITIAL_SYSTEM = """你是投标目录规划专家。根据招标文件解读结果，生成投标响应目录完整树。
只输出 JSON：{"outline": <BidOutlineNode>, "changes_summary": "..."}。
规则：
1. outline 为完整树，根节点 id 固定为 bid-root，children 为一级章节。
2. 每节点须含 summary、writing_spec；尽量填充 scoring_refs、disqualification_refs（使用输入中的 id）。
3. 有模板清单时，匹配节点设置 template_ref（template_id/file/type）。
4. 严格遵循 directory_requirements 与响应须知，不得遗漏 mandatory 章节。
5. 面向评标清晰度：评分项须在目录中有对应章节或子节。"""

GEN_CATALOG_REFINE_SYSTEM = """你是投标目录完善专家。输入包含当前完整目录树与目标节点 id。
只输出 JSON：{"outline": <完整BidOutlineNode树>, "changes_summary": "..."}。
规则：
1. 必须返回完整 outline 树（替换整棵树），根 id=bid-root。
2. 重点完善 target_node_id 对应节点及其子结构，可微调其他节点但勿破坏整体 mandatory 结构。
3. 补充 summary、writing_spec，关联 scoring_refs/disqualification_refs/template_ref/source_refs。
4. 引用 id 必须来自输入的废标/评分/模板表。"""
```

```python
# src/tender_insights/gen_catalog/context.py — build_initial_user_prompt / build_refine_user_prompt
# 将 overview、brief fields、directory_requirements JSON、废标/评分 id 表（静态块在前）、模板清单 拼成 user 字符串
# build_refine_user_prompt: 废标/评分表 + 当前 outline JSON + target_node_id + excerpt
```

- [ ] **Step 3: Run tests — PASS**

- [ ] **Step 4: Commit**

```bash
git add src/tender_insights/gen_catalog/prompts.py src/tender_insights/gen_catalog/context.py tests/tender_insights/unit/test_gen_catalog.py
git commit -m "feat(gen-catalog): add static prompts and user context builders"
```

---

### Task 6: FakeLLM 与初始目录生成

**Files:**
- Create: `tests/helpers/gen_catalog_fake_llm.py`
- Create: `src/tender_insights/gen_catalog/extractor.py`（initial 部分）
- Modify: `src/tender_insights/api.py`

- [ ] **Step 1: Write failing integration test**

```python
# tests/tender_insights/unit/test_gen_catalog.py
import json
from doc_chunk.llm.client import FakeLLMClient
from doc_chunk.workspace.layout import OutputWorkspace
from tests.helpers.gen_catalog_fake_llm import GenCatalogFakeLLM
from tender_insights.gen_catalog.extractor import run_gen_catalog_initial


def test_run_gen_catalog_initial_writes_draft(tmp_path: Path) -> None:
    ws_root = _minimal_interpretation(tmp_path)
    (ws_root / "interpret" / "source_content.md").mkdir(parents=True)
    (ws_root / "interpret" / "source_content.md").write_text("# 正文\n", encoding="utf-8")
    ws = OutputWorkspace(ws_root)
    client = GenCatalogFakeLLM()
    draft = run_gen_catalog_initial(ws, client, report=validate_prerequisites(ws))
    assert draft.root.id == "bid-root"
    assert (ws.root / "bid_outline.draft.json").is_file()
```

- [ ] **Step 2: Implement FakeLLM + initial step**

```python
# tests/helpers/gen_catalog_fake_llm.py
import json
from doc_chunk.llm.client import FakeLLMClient
from doc_chunk.llm.completion import LLMCompletionResult

_INITIAL = {
    "outline": {
        "id": "bid-root",
        "title": "投标文件",
        "level": 0,
        "order": 0,
        "mandatory": True,
        "summary": "",
        "writing_spec": "",
        "children": [
            {
                "id": "bid-001",
                "title": "投标函",
                "level": 1,
                "order": 1,
                "mandatory": True,
                "summary": "承诺函",
                "writing_spec": "签字盖章",
                "children": [],
            }
        ],
    },
    "changes_summary": "initial",
}


class GenCatalogFakeLLM(FakeLLMClient):
    def complete_with_meta(self, messages, *, response_format="text", timeout=None):
        user = " ".join(m.get("content", "") for m in messages if m.get("role") == "user")
        if "target_node_id" in user:
            payload = _INITIAL
        else:
            payload = _INITIAL
        text = json.dumps(payload, ensure_ascii=False)
        self.calls.append({"messages": messages})
        return LLMCompletionResult(text=text)
```

```python
# src/tender_insights/gen_catalog/extractor.py (partial)
def ensure_gen_catalog_llm_logging(workspace: OutputWorkspace) -> None:
    import os
    from tender_insights.interpret.llm_logging import LLM_CALLS_FILENAME
    os.environ["INTERPRET_LOG_JSONL"] = str(workspace.root / LLM_CALLS_FILENAME)

def run_gen_catalog_initial(workspace, client, *, report, config=None) -> BidOutlineFile:
    ...
    messages = [
        {"role": "system", "content": GEN_CATALOG_INITIAL_SYSTEM},
        {"role": "user", "content": build_initial_user_prompt(report)},
    ]
    log_llm_prompt(call_type="gen_catalog_initial", messages=messages, workspace=str(workspace.root), segment_id="initial")
    response = extract_json_model(client, messages, BidOutlineLLMResponse, log_context={"call_type": "gen_catalog_initial", "segment_id": "initial"})
    draft = _build_draft_file(report, response.outline, mode=..., status=...)
    (workspace.root / "bid_outline.draft.json").write_text(draft.model_dump_json(), encoding="utf-8")
    return draft
```

- [ ] **Step 3: Run test — PASS**

- [ ] **Step 4: Commit**

```bash
git add tests/helpers/gen_catalog_fake_llm.py src/tender_insights/gen_catalog/extractor.py tests/tender_insights/unit/test_gen_catalog.py
git commit -m "feat(gen-catalog): implement initial outline LLM step with draft persistence"
```

---

### Task 7: 节点完善与完整 gen_catalog_workspace 状态机

**Files:**
- Modify: `src/tender_insights/gen_catalog/extractor.py`
- Modify: `tests/helpers/gen_catalog_fake_llm.py`
- Modify: `tests/tender_insights/unit/test_gen_catalog.py`

- [ ] **Step 1: Write failing tests for step mode**

```python
def test_gen_catalog_workspace_step_pauses_after_initial(tmp_path: Path) -> None:
    ws = OutputWorkspace(_minimal_interpretation(tmp_path))
    client = GenCatalogFakeLLM()
    result = gen_catalog_workspace(ws, client, mode="step", run_limit=1)
    assert result.status == "paused"
    session = load_session(ws)
    assert "initial" in session.completed_steps


def test_gen_catalog_workspace_continue_next_node(tmp_path: Path) -> None:
    ...
    gen_catalog_workspace(ws, client, mode="step", run_limit=1)
    result = gen_catalog_workspace(ws, client, mode="step", continue_from_session=True, run_limit=1)
    assert result.step_index >= 2
```

- [ ] **Step 2: Implement `run_gen_catalog_node` + `gen_catalog_workspace`**

核心逻辑：

```python
def gen_catalog_workspace(
    workspace: OutputWorkspace,
    client: LLMClient,
    *,
    mode: Literal["step", "auto"] = "auto",
    continue_from_session: bool = False,
    restart: bool = False,
    overwrite: bool = False,
    on_progress: Callable[[str, dict], None] | None = None,
    config: InsightsConfig | None = None,
) -> BidOutlineFile:
    if restart:
        clear_gen_catalog_artifacts(workspace)
    report = validate_prerequisites(workspace, overwrite=overwrite)
    ensure_gen_catalog_llm_logging(workspace)
    # if no draft: run_gen_catalog_initial; elif continue: run_gen_catalog_node for next pending id
    # auto mode: loop until no pending nodes; step mode: run exactly one step per invocation
    # on completion: status=awaiting_accept, session.status=awaiting_accept
```

`run_gen_catalog_node` 使用 `GEN_CATALOG_REFINE_SYSTEM` + `build_refine_user_prompt`；`call_type="gen_catalog_node"`，`segment_id=node_id`。

- [ ] **Step 3: Run tests — PASS**

- [ ] **Step 4: Commit**

```bash
git add src/tender_insights/gen_catalog/extractor.py tests/helpers/gen_catalog_fake_llm.py tests/tender_insights/unit/test_gen_catalog.py
git commit -m "feat(gen-catalog): add per-node refine and step/auto orchestration"
```

---

### Task 8: Accept 落盘与 Markdown 渲染

**Files:**
- Create: `src/tender_insights/gen_catalog/accept.py`
- Create: `src/tender_insights/gen_catalog/render.py`
- Modify: `tests/tender_insights/unit/test_gen_catalog.py`

- [ ] **Step 1: Write failing tests**

```python
from tender_insights.gen_catalog.accept import accept_gen_catalog_draft
from tender_insights.gen_catalog.render import render_bid_outline_markdown


def test_accept_writes_final_artifacts(tmp_path: Path) -> None:
    ws_root = _minimal_interpretation(tmp_path)
    ws = OutputWorkspace(ws_root)
    # write draft with status awaiting_accept
    ...
    accept_gen_catalog_draft(ws)
    assert (ws.root / "bid_outline.json").is_file()
    assert (ws.root / "bid_outline.md").is_file()
    text = (ws.root / "bid_outline.md").read_text(encoding="utf-8")
    assert "投标函" in text
```

- [ ] **Step 2: Implement accept + render**

```python
# accept.py
def accept_gen_catalog_draft(workspace: OutputWorkspace) -> BidOutlineFile:
    draft_path = workspace.root / "bid_outline.draft.json"
    draft = BidOutlineFile.model_validate_json(draft_path.read_text(encoding="utf-8"))
    if draft.status != "awaiting_accept":
        raise ValueError("draft is not awaiting accept")
    draft.status = "accepted"
    draft.accepted_at = datetime.now(UTC).isoformat()
    write_json_artifact(workspace, "bid_outline.json", draft.model_dump(mode="json"), stage_name="gen_catalog", output_key="bid_outline")
    md = render_bid_outline_markdown(draft)
    (workspace.root / "bid_outline.md").write_text(md, encoding="utf-8")
    return draft

# render.py — recursive markdown with title, summary, writing_spec, refs
```

- [ ] **Step 3: Run tests — PASS**

- [ ] **Step 4: Commit**

```bash
git add src/tender_insights/gen_catalog/accept.py src/tender_insights/gen_catalog/render.py tests/tender_insights/unit/test_gen_catalog.py
git commit -m "feat(gen-catalog): add accept flow and markdown render"
```

---

### Task 9: API 层与 CLI

**Files:**
- Modify: `src/tender_insights/api.py`
- Modify: `src/tender_insights/cli/main.py`
- Modify: `tests/tender_insights/unit/test_cli.py`

- [ ] **Step 1: Write failing CLI test**

```python
def test_cli_gen_catalog_help() -> None:
    result = CliRunner().invoke(app, ["gen-catalog", "--help"])
    assert result.exit_code == 0
    assert "--step" in result.stdout
    assert "--accept" in result.stdout
```

- [ ] **Step 2: Wire API + CLI**

```python
# api.py additions
def run_gen_catalog_job(workspace, *, mode="auto", continue_from_session=False, restart=False, overwrite=False, on_progress=None, client=None):
    client = client or create_llm_client_from_env()
    from tender_insights.gen_catalog.extractor import gen_catalog_workspace
    return gen_catalog_workspace(workspace, client, mode=mode, continue_from_session=continue_from_session, restart=restart, overwrite=overwrite, on_progress=on_progress)

def continue_gen_catalog(workspace, **kwargs):
    return run_gen_catalog_job(workspace, mode="step", continue_from_session=True, **kwargs)

def accept_gen_catalog(workspace):
    from tender_insights.gen_catalog.accept import accept_gen_catalog_draft
    return accept_gen_catalog_draft(workspace)
```

```python
# cli/main.py
@app.command("gen-catalog")
def gen_catalog_cmd(
    path: Path,
    step: bool = False,
    once: bool = False,
    continue_: bool = typer.Option(False, "--continue"),
    accept: bool = False,
    restart: bool = False,
    overwrite: bool = False,
):
    ws = _resolve_workspace(path, None, overwrite=False)
    if accept:
        accept_gen_catalog(ws)
        typer.echo(f"Wrote {ws.root / 'bid_outline.json'}")
        return
    mode = "step" if step or once or continue_ else "auto"
    if once and not continue_:
        # internal run_limit=1 via gen_catalog_workspace step
        ...
    run_gen_catalog_job(ws, mode=mode, continue_from_session=continue_, restart=restart, overwrite=overwrite)
```

- [ ] **Step 3: Run tests**

Run: `.venv/bin/pytest tests/tender_insights/unit/test_cli.py -v`  
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/tender_insights/api.py src/tender_insights/cli/main.py tests/tender_insights/unit/test_cli.py
git commit -m "feat(gen-catalog): expose gen-catalog and accept via API and CLI"
```

---

### Task 10: Viewer — Job 模型与 Pipeline

**Files:**
- Modify: `viewer/viewer/models.py`
- Modify: `viewer/viewer/services/interpret_job_registry.py`
- Create: `viewer/viewer/services/gen_catalog_pipeline.py`
- Create: `viewer/tests/unit/test_gen_catalog_pipeline.py`

- [ ] **Step 1: Write failing unit test**

```python
# viewer/tests/unit/test_gen_catalog_pipeline.py
def test_gen_catalog_pipeline_progress_percent(viewer_data_dir) -> None:
    from viewer.services.gen_catalog_pipeline import GenCatalogPipelineService
    ...
    # mock on_progress updates job step_current/step_total
    assert job.progress_percent == 50
```

- [ ] **Step 2: Extend job_kind + pipeline**

```python
# viewer/viewer/models.py
class InterpretJobState(BaseModel):
    job_kind: Literal["interpret", "brief", "gen_catalog"] = "interpret"
    stage: Literal[..., "gen_catalog", "gen_catalog_accept", ...]
```

```python
# viewer/viewer/services/gen_catalog_pipeline.py
class GenCatalogPipelineService:
    def __init__(self, sessions, jobs):
        ...

    def run_gen_catalog(self, job_id, session_id, *, mode="step", continue_from_session=False, restart=False):
        def _progress(_stage, payload):
            percent = int(payload.get("current", 0) / max(payload.get("total", 1), 1) * 100)
            self._jobs.update(job_id, message=payload.get("message",""), detail=payload.get("detail",""), step_current=payload.get("current",0), step_total=payload.get("total",0), progress_percent=percent)
        run_gen_catalog_job(ws, mode=mode, continue_from_session=continue_from_session, restart=restart, on_progress=_progress)
```

- [ ] **Step 3: Run test — PASS**

- [ ] **Step 4: Commit**

```bash
git add viewer/viewer/models.py viewer/viewer/services/interpret_job_registry.py viewer/viewer/services/gen_catalog_pipeline.py viewer/tests/unit/test_gen_catalog_pipeline.py
git commit -m "feat(viewer): add gen-catalog pipeline service with progress tracking"
```

---

### Task 11: Viewer REST 路由与 API 测试

**Files:**
- Create: `viewer/viewer/routes/gen_catalog.py`
- Modify: `viewer/viewer/deps.py`
- Modify: `viewer/viewer/main.py`
- Create: `viewer/tests/api/test_gen_catalog_api.py`

- [ ] **Step 1: Write failing API tests**

```python
# viewer/tests/api/test_gen_catalog_api.py
def test_gen_catalog_page_served() -> None:
    client = TestClient(create_app())
    assert client.get("/gen-catalog").status_code == 200


def test_gen_catalog_start_requires_interpretation(viewer_data_dir) -> None:
    # session without interpretation.json -> 400
    ...


def test_gen_catalog_draft_endpoint(viewer_data_dir) -> None:
    # workspace with bid_outline.draft.json -> 200 tree
    ...
```

- [ ] **Step 2: Implement routes**

```python
# viewer/viewer/routes/gen_catalog.py
router = APIRouter(prefix="/gen-catalog", tags=["gen-catalog"])

@router.post("/sessions/{session_id}/start")
def start_gen_catalog(session_id: str, mode: Literal["auto","step"] = Query("step"), background_tasks: BackgroundTasks):
    # 409 if running; 400 if no interpretation.json
    ...

@router.post("/sessions/{session_id}/continue")
@router.post("/sessions/{session_id}/accept")
@router.get("/jobs/{job_id}")
@router.get("/sessions/{session_id}/draft")
@router.get("/sessions/{session_id}/llm-calls")  # reuse _read_llm_calls filtering gen_catalog_*
```

```python
# viewer/viewer/main.py
from viewer.routes import gen_catalog
app.include_router(gen_catalog.router, prefix="/api")
@app.get("/gen-catalog")
def gen_catalog_page(): return FileResponse(STATIC_DIR / "gen-catalog.html")
```

```python
# viewer/viewer/deps.py
@lru_cache
def get_gen_catalog_pipeline_service() -> GenCatalogPipelineService:
    return GenCatalogPipelineService(sessions=get_interpret_session_store(), jobs=get_interpret_job_registry())
```

- [ ] **Step 3: Run tests**

Run: `.venv/bin/pytest viewer/tests/api/test_gen_catalog_api.py -v`  
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add viewer/viewer/routes/gen_catalog.py viewer/viewer/deps.py viewer/viewer/main.py viewer/tests/api/test_gen_catalog_api.py
git commit -m "feat(viewer): add gen-catalog REST API and page route"
```

---

### Task 12: 前端 gen-catalog 页与 interpret 入口

**Files:**
- Create: `viewer/viewer/static/gen-catalog.html`
- Create: `viewer/viewer/static/gen-catalog.js`
- Modify: `viewer/viewer/static/interpret.html`
- Modify: `viewer/viewer/static/interpret.js`
- Modify: `viewer/viewer/static/style.css`（树预览样式）
- Create: `viewer/tests/unit/test_gen_catalog_static_assets.py`

- [ ] **Step 1: Write failing static test**

```python
def test_gen_catalog_html_has_continue_button() -> None:
    html = (Path(__file__).resolve().parents[2] / "viewer/static/gen-catalog.html").read_text(encoding="utf-8")
    assert "continue-btn" in html
    assert "progress-panel" in html
```

- [ ] **Step 2: Implement UI**

`gen-catalog.html` 要素：
- 导航 Tab：切片预览 / 招标解读 / **目录生成**
- `session_id` 从 query string 读取
- 模式选择 `auto` / `step`（默认 step）
- 按钮：`#start-btn`、`#continue-btn`、`#accept-btn`、`#restart-btn`
- 进度面板（复用 interpret 的 `.progress-panel` 结构）
- 左侧树 `#outline-tree`，右侧节点详情 `#node-detail`
- 前置警告区 `#prerequisite-warnings`
- LLM 调用折叠区 `#llm-calls-panel`

`interpret.html` / `interpret.js`：
- 导航增加 `<a href="/gen-catalog">目录生成</a>`
- 解读成功且存在 `interpretation.json` 时显示 `#go-gen-catalog-btn`，跳转 `/gen-catalog?session_id=...`

`gen-catalog.js` 核心轮询：

```javascript
async function pollJob(jobId) {
  const res = await fetch(`/api/gen-catalog/jobs/${jobId}`);
  const job = await res.json();
  updateProgress(job);
  if (job.status === 'running') setTimeout(() => pollJob(jobId), 800);
  else await loadDraft();
}
```

- [ ] **Step 3: Run static + manual smoke**

Run: `.venv/bin/pytest viewer/tests/unit/test_gen_catalog_static_assets.py -v`

- [ ] **Step 4: Commit**

```bash
git add viewer/viewer/static/gen-catalog.html viewer/viewer/static/gen-catalog.js viewer/viewer/static/interpret.html viewer/viewer/static/interpret.js viewer/viewer/static/style.css viewer/tests/unit/test_gen_catalog_static_assets.py
git commit -m "feat(viewer): add gen-catalog test page and interpret navigation entry"
```

---

### Task 13: 文档更新

**Files:**
- Modify: `README.md`
- Create: `.cursor/skills/tender-gen-catalog/SKILL.md`（简要命令说明）

- [ ] **Step 1: Update README** — 在 tender-insights 章节增加 `gen-catalog` 命令、产物路径、前置依赖说明

- [ ] **Step 2: Add skill stub** — 触发词、前置、`tender-insights gen-catalog` 示例、`bid_outline.json` 字段说明

- [ ] **Step 3: Commit**

```bash
git add README.md .cursor/skills/tender-gen-catalog/SKILL.md
git commit -m "docs: document tender-insights gen-catalog workflow"
```

---

### Task 14: 全量回归

- [ ] **Step 1: Run tender_insights tests**

Run: `.venv/bin/pytest tests/tender_insights/ -v`  
Expected: all PASS

- [ ] **Step 2: Run viewer tests**

Run: `.venv/bin/pytest viewer/tests/ -v`  
Expected: all PASS

- [ ] **Step 3: Fix any failures and commit**

```bash
git commit -m "test: fix gen-catalog integration regressions"
```

---

## Spec Coverage Self-Review

| Spec 要求 | 对应 Task |
|-----------|-----------|
| 产物 A：目录方案非正文 | Task 1, 8 |
| 前置 C：interpret 必须，brief/template 降级 | Task 4 |
| 节点级整树替换，无合并 | Task 7 |
| step / auto 模式 | Task 7, 9, 11 |
| preview + accept | Task 8, 11 |
| 进度回调 | Task 7, 10, 12 |
| llm_calls.jsonl | Task 6, 7 |
| 双提示词 + cache 前置 | Task 5 |
| excerpt ≤2000、<200 拼接 | Task 3 |
| Viewer 绑定 session | Task 11, 12 |
| 并发 409 / accept 校验 | Task 11 |
| 契约测试 scoring_refs | Task 1 + Task 14 补充引用校验测试 |

**Gap fixed in Task 14:** 在 `test_bid_outline_schema.py` 或 `test_gen_catalog.py` 增加 `validate_ref_ids(draft, interpretation)` 测试，确保 refs 指向存在的 id。

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-25-tender-generate.md`. Two execution options:

**1. Subagent-Driven (recommended)** — 每个 Task 派发独立 subagent，任务间做代码审查，迭代快

**2. Inline Execution** — 在本会话用 executing-plans 按 Task 批量执行，检查点处暂停供你审阅

你想用哪种方式？
