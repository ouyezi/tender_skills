# doc_chunk Viewer 切片预览 UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在独立 `viewer/` 应用中实现本机调试 UI：上传/打开工作区、跑 doc_chunk pipeline、以左侧 outline 树 + 右侧章节 Markdown 浏览切片结果。

**Architecture:** 顶层 `viewer/` 包通过 editable install 依赖同仓库 `doc_chunk`；FastAPI 提供 REST API + 静态单页；会话与 pipeline 任务状态分别持久化到 `sessions.json` 与进程内 dict；章节截取在 viewer 内复制 `anchor_planner` 锚点逻辑，不修改核心库。

**Tech Stack:** Python 3.11+, FastAPI, uvicorn, python-multipart, pydantic v2, pytest, httpx (TestClient), marked.js (CDN), 原生 JavaScript

**设计来源:** [`docs/superpowers/specs/2026-06-16-doc-chunk-viewer-design.md`](../specs/2026-06-16-doc-chunk-viewer-design.md)

---

## File Structure

```text
viewer/
├── pyproject.toml
├── README.md
├── viewer/
│   ├── __init__.py
│   ├── __main__.py              # python -m viewer 入口
│   ├── main.py                  # FastAPI app 工厂 + 路由挂载
│   ├── config.py                # 端口、数据目录、会话上限
│   ├── models.py                # SessionRecord, JobState, API schemas
│   ├── services/
│   │   ├── session_store.py     # sessions.json CRUD，20 条上限
│   │   ├── outline_tree.py      # outline 扁平 nodes → 嵌套树 + 前言节点
│   │   ├── section_slice.py     # outline 节点 → markdown 片段
│   │   ├── workspace.py         # 工作区路径校验
│   │   ├── job_registry.py      # 内存 job 状态
│   │   └── pipeline.py          # asyncio.to_thread 包装 run_pipeline
│   ├── routes/
│   │   ├── sessions.py
│   │   ├── upload.py
│   │   ├── workspaces.py
│   │   ├── content.py
│   │   └── jobs.py
│   └── static/
│       ├── index.html
│       ├── app.js
│       └── style.css
└── tests/
    ├── conftest.py              # 临时数据目录 + 预制工作区 fixture
    ├── unit/
    │   ├── test_session_store.py
    │   ├── test_outline_tree.py
    │   └── test_section_slice.py
    ├── api/
    │   ├── test_sessions_api.py
    │   ├── test_content_api.py
    │   └── test_workspaces_api.py
    └── integration/
        └── test_upload_pipeline.py
```

**职责边界**

| 文件 | 职责 |
|------|------|
| `config.py` | 读取 `DOC_CHUNK_VIEWER_DATA`，暴露 `data_dir`、`host`、`port` |
| `session_store.py` | 唯一读写 `sessions.json` 的模块 |
| `outline_tree.py` | 只负责 JSON 树形转换，不读文件 |
| `section_slice.py` | 只负责 char 范围计算与 markdown 截取 |
| `pipeline.py` | 唯一调用 `doc_chunk.api.run_pipeline` 的模块 |
| `routes/*.py` | 薄路由层，调用 services |

---

### Task 1: Viewer 包脚手架与配置

**Files:**
- Create: `viewer/pyproject.toml`
- Create: `viewer/README.md`
- Create: `viewer/viewer/__init__.py`
- Create: `viewer/viewer/__main__.py`
- Create: `viewer/viewer/config.py`
- Create: `viewer/tests/unit/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# viewer/tests/unit/test_config.py
from __future__ import annotations

from pathlib import Path

import pytest

from viewer.config import ViewerSettings


def test_settings_use_env_data_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DOC_CHUNK_VIEWER_DATA", str(tmp_path))
    settings = ViewerSettings.load()
    assert settings.data_dir == tmp_path.resolve()
    assert settings.host == "127.0.0.1"
    assert settings.port == 8765
    assert settings.max_sessions == 20
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/tongqianni/xlab/tender_skills
pip install -e ".[dev]"
pip install -e "./viewer[dev]"
python -m pytest viewer/tests/unit/test_config.py -v
```

Expected: FAIL `ModuleNotFoundError: No module named 'viewer.config'`

- [ ] **Step 3: Write minimal implementation**

```toml
# viewer/pyproject.toml
[build-system]
requires = ["setuptools>=69", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "doc-chunk-viewer"
version = "0.1.0"
description = "Local debug UI for doc_chunk outline browsing"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
  "doc-chunk",
  "fastapi>=0.115.0",
  "uvicorn[standard]>=0.32.0",
  "python-multipart>=0.0.12",
  "pydantic>=2.10.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "httpx>=0.27.0"]

[tool.setuptools.packages.find]
where = ["."]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

```python
# viewer/viewer/__init__.py
__version__ = "0.1.0"
```

```python
# viewer/viewer/config.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ViewerSettings:
    data_dir: Path
    host: str = "127.0.0.1"
    port: int = 8765
    max_sessions: int = 20

    @property
    def workspaces_dir(self) -> Path:
        return self.data_dir / "workspaces"

    @property
    def sessions_file(self) -> Path:
        return self.data_dir / "sessions.json"

    @classmethod
    def load(cls) -> ViewerSettings:
        data_dir = Path.home() / ".doc-chunk-viewer"
        import os

        if custom := os.environ.get("DOC_CHUNK_VIEWER_DATA"):
            data_dir = Path(custom)
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "workspaces").mkdir(parents=True, exist_ok=True)
        return cls(data_dir=data_dir.resolve())
```

```python
# viewer/viewer/__main__.py
from __future__ import annotations

import uvicorn

from viewer.config import ViewerSettings


def main() -> None:
    settings = ViewerSettings.load()
    uvicorn.run("viewer.main:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    main()
```

```markdown
# doc-chunk-viewer

本机调试 UI：上传 Word/PDF → doc_chunk pipeline → 左侧 outline 树 + 右侧章节 Markdown。

## 安装

```bash
cd tender_skills
pip install -e ".[dev]"
pip install -e "./viewer[dev]"
```

## 启动

```bash
python -m viewer
# → http://127.0.0.1:8765
```

环境变量 `DOC_CHUNK_VIEWER_DATA` 可覆盖数据目录（默认 `~/.doc-chunk-viewer/`）。
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest viewer/tests/unit/test_config.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add viewer/
git commit -m "feat(viewer): scaffold package and config"
```

---

### Task 2: 数据模型与会话存储

**Files:**
- Create: `viewer/viewer/models.py`
- Create: `viewer/viewer/services/session_store.py`
- Create: `viewer/tests/unit/test_session_store.py`

- [ ] **Step 1: Write the failing test**

```python
# viewer/tests/unit/test_session_store.py
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from viewer.models import SessionRecord
from viewer.services.session_store import SessionStore


def _record(session_id: str, *, title: str = "demo") -> SessionRecord:
    now = datetime.now(UTC).isoformat()
    return SessionRecord(
        id=session_id,
        title=title,
        workspace_path="/tmp/ws",
        source_type="upload",
        status="success",
        created_at=now,
        opened_at=now,
        error=None,
    )


def test_session_store_persists_and_lists(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "sessions.json", max_sessions=20)
    store.add(_record("s1", title="first"))
    store.add(_record("s2", title="second"))

    sessions = store.list_sessions()
    assert [s.id for s in sessions] == ["s2", "s1"]


def test_session_store_trims_to_max(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "sessions.json", max_sessions=2)
    store.add(_record("s1"))
    store.add(_record("s2"))
    store.add(_record("s3"))

    assert [s.id for s in store.list_sessions()] == ["s3", "s2"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest viewer/tests/unit/test_session_store.py -v
```

Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# viewer/viewer/models.py
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SessionRecord(BaseModel):
    id: str
    title: str
    workspace_path: str
    source_type: Literal["upload", "open"]
    status: Literal["pending", "running", "success", "failed"]
    created_at: str
    opened_at: str
    error: str | None = None


class JobState(BaseModel):
    job_id: str
    session_id: str
    stage: Literal["extract", "outline", "tree", "chunk", "done", "failed"]
    message: str
    status: Literal["running", "done", "failed"]
    error: str | None = None


class OpenWorkspaceRequest(BaseModel):
    path: str


class UploadResponse(BaseModel):
    session_id: str
    job_id: str


class OutlineTreeNode(BaseModel):
    node_id: str
    title: str
    level: int
    needs_review: bool = False
    children: list[OutlineTreeNode] = Field(default_factory=list)


class OutlineTreeResponse(BaseModel):
    strategy: str
    nodes: list[OutlineTreeNode]


class SectionResponse(BaseModel):
    node_id: str
    title: str
    level: int
    section_path: list[str]
    needs_review: bool
    char_start: int
    char_end: int
    markdown: str
```

```python
# viewer/viewer/services/session_store.py
from __future__ import annotations

import json
from pathlib import Path

from viewer.models import SessionRecord


class SessionStore:
    def __init__(self, path: Path, *, max_sessions: int = 20) -> None:
        self._path = path
        self._max_sessions = max_sessions

    def _load(self) -> list[SessionRecord]:
        if not self._path.exists():
            return []
        data = json.loads(self._path.read_text(encoding="utf-8"))
        return [SessionRecord.model_validate(item) for item in data]

    def _save(self, sessions: list[SessionRecord]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = [s.model_dump() for s in sessions[: self._max_sessions]]
        self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def list_sessions(self) -> list[SessionRecord]:
        return self._load()

    def get(self, session_id: str) -> SessionRecord | None:
        return next((s for s in self._load() if s.id == session_id), None)

    def add(self, record: SessionRecord) -> SessionRecord:
        sessions = [r for r in self._load() if r.id != record.id]
        sessions.insert(0, record)
        self._save(sessions)
        return record

    def update(self, session_id: str, **fields: object) -> SessionRecord:
        sessions = self._load()
        updated: SessionRecord | None = None
        for idx, session in enumerate(sessions):
            if session.id == session_id:
                updated = session.model_copy(update=fields)
                sessions[idx] = updated
                break
        if updated is None:
            raise KeyError(session_id)
        self._save(sessions)
        return updated

    def delete(self, session_id: str) -> bool:
        sessions = self._load()
        kept = [s for s in sessions if s.id != session_id]
        if len(kept) == len(sessions):
            return False
        self._save(kept)
        return True
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest viewer/tests/unit/test_session_store.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add viewer/viewer/models.py viewer/viewer/services/session_store.py viewer/tests/unit/test_session_store.py
git commit -m "feat(viewer): add session models and JSON store"
```

---

### Task 3: Outline 嵌套树转换

**Files:**
- Create: `viewer/viewer/services/outline_tree.py`
- Create: `viewer/tests/unit/test_outline_tree.py`

- [ ] **Step 1: Write the failing test**

```python
# viewer/tests/unit/test_outline_tree.py
from __future__ import annotations

from doc_chunk.models.outline import Anchor, OutlineNode, OutlineTree

from viewer.services.outline_tree import build_outline_response


def test_build_outline_response_nests_by_parent_id() -> None:
    tree = OutlineTree(
        strategy="toc",
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
                title="Section 1.1",
                level=2,
                parent_id="n1",
                sort_order=1,
                anchor=Anchor(char_start=50),
            ),
        ],
    )
    response = build_outline_response(tree, content_md="# Chapter 1\n\nbody\n\n## Section 1.1\n\ntext")

    assert response.strategy == "toc"
    assert len(response.nodes) == 1
    assert response.nodes[0].node_id == "n1"
    assert response.nodes[0].children[0].node_id == "n2"


def test_build_outline_response_adds_preface_node() -> None:
    tree = OutlineTree(
        strategy="heading_heuristic",
        nodes=[
            OutlineNode(
                node_id="n1",
                title="Chapter 1",
                level=1,
                parent_id=None,
                sort_order=0,
                anchor=Anchor(char_start=20),
            ),
        ],
    )
    response = build_outline_response(tree, content_md="Preface text\n\n# Chapter 1\n\nbody")

    assert response.nodes[0].node_id == "__preface__"
    assert response.nodes[0].title == "前言"
    assert response.nodes[1].node_id == "n1"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest viewer/tests/unit/test_outline_tree.py -v
```

Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# viewer/viewer/services/outline_tree.py
from __future__ import annotations

from doc_chunk.models.outline import OutlineTree

from viewer.models import OutlineTreeNode, OutlineTreeResponse

PREFACE_NODE_ID = "__preface__"


def _sorted_nodes(tree: OutlineTree) -> list:
    return sorted(tree.nodes, key=lambda n: (n.sort_order, n.node_id))


def _build_section_path(node, node_map: dict) -> list[str]:
    chain: list[str] = []
    cursor = node
    seen: set[str] = set()
    while cursor and cursor.node_id not in seen:
        seen.add(cursor.node_id)
        chain.append(cursor.title)
        cursor = node_map.get(cursor.parent_id) if cursor.parent_id else None
    return list(reversed(chain))


def _first_anchor_start(tree: OutlineTree) -> int | None:
    starts = [n.anchor.char_start for n in tree.nodes if n.anchor.char_start is not None]
    return min(starts) if starts else None


def build_outline_response(tree: OutlineTree, content_md: str) -> OutlineTreeResponse:
    node_map = {n.node_id: n for n in tree.nodes}
    children_by_parent: dict[str | None, list] = {}
    for node in _sorted_nodes(tree):
        children_by_parent.setdefault(node.parent_id, []).append(node)

    def to_node(raw) -> OutlineTreeNode:
        return OutlineTreeNode(
            node_id=raw.node_id,
            title=raw.title,
            level=raw.level,
            needs_review=raw.needs_review,
            children=[to_node(child) for child in children_by_parent.get(raw.node_id, [])],
        )

    roots = [to_node(node) for node in children_by_parent.get(None, [])]
    nodes: list[OutlineTreeNode] = []

    first_start = _first_anchor_start(tree)
    if first_start and first_start > 0 and content_md[:first_start].strip():
        nodes.append(
            OutlineTreeNode(
                node_id=PREFACE_NODE_ID,
                title="前言",
                level=0,
                needs_review=False,
                children=[],
            )
        )
    nodes.extend(roots)
    return OutlineTreeResponse(strategy=tree.strategy, nodes=nodes)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest viewer/tests/unit/test_outline_tree.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add viewer/viewer/services/outline_tree.py viewer/tests/unit/test_outline_tree.py
git commit -m "feat(viewer): nest outline nodes for API response"
```

---

### Task 4: 章节 Markdown 截取

**Files:**
- Create: `viewer/viewer/services/section_slice.py`
- Create: `viewer/tests/unit/test_section_slice.py`

- [ ] **Step 1: Write the failing test**

```python
# viewer/tests/unit/test_section_slice.py
from __future__ import annotations

from doc_chunk.models.outline import Anchor, OutlineNode, OutlineTree

from viewer.services.outline_tree import PREFACE_NODE_ID
from viewer.services.section_slice import slice_section


def test_slice_section_uses_char_anchors() -> None:
    content_md = "Preface\n\n# Chapter 1\n\nAlpha\n\n## Section 1.1\n\nBeta\n\n# Chapter 2\n\nGamma"
    tree = OutlineTree(
        nodes=[
            OutlineNode(
                node_id="n1",
                title="Chapter 1",
                level=1,
                parent_id=None,
                sort_order=0,
                anchor=Anchor(char_start=content_md.index("# Chapter 1")),
            ),
            OutlineNode(
                node_id="n2",
                title="Section 1.1",
                level=2,
                parent_id="n1",
                sort_order=1,
                anchor=Anchor(char_start=content_md.index("## Section 1.1")),
            ),
        ]
    )

    preface = slice_section(content_md, tree, PREFACE_NODE_ID)
    assert preface.title == "前言"
    assert "Preface" in preface.markdown

    section = slice_section(content_md, tree, "n2")
    assert section.title == "Section 1.1"
    assert "Beta" in section.markdown
    assert "Gamma" not in section.markdown
    assert section.section_path == ["Chapter 1", "Section 1.1"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest viewer/tests/unit/test_section_slice.py -v
```

Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# viewer/viewer/services/section_slice.py
from __future__ import annotations

import re

from doc_chunk.models.outline import OutlineNode, OutlineTree

from viewer.models import SectionResponse
from viewer.services.outline_tree import PREFACE_NODE_ID

_HEADING_RE = re.compile(r"^(#{1,8})[ \t]+(.+?)[ \t#]*$", re.MULTILINE)


def _sorted_sliceable_nodes(nodes: list[OutlineNode]) -> list[OutlineNode]:
    return sorted(
        nodes,
        key=lambda n: (
            n.anchor.char_start if n.anchor.char_start is not None else 10**9,
            n.sort_order,
        ),
    )


def _is_descendant(node: OutlineNode, ancestor: OutlineNode, node_map: dict[str, OutlineNode]) -> bool:
    cursor_id = node.parent_id
    seen: set[str] = set()
    while cursor_id and cursor_id not in seen:
        if cursor_id == ancestor.node_id:
            return True
        seen.add(cursor_id)
        parent = node_map.get(cursor_id)
        cursor_id = parent.parent_id if parent else None
    return False


def _section_end_char(
    node: OutlineNode,
    ordered: list[OutlineNode],
    node_map: dict[str, OutlineNode],
    content_len: int,
) -> int:
    start = node.anchor.char_start or 0
    level = node.level
    for other in ordered:
        other_start = other.anchor.char_start
        if other_start is None or other_start <= start or other.node_id == node.node_id:
            continue
        if _is_descendant(other, node, node_map):
            return other_start
    for other in ordered:
        other_start = other.anchor.char_start
        if other_start is None or other_start <= start:
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


def _fallback_char_start(content_md: str, title: str) -> int | None:
    for match in _HEADING_RE.finditer(content_md):
        if match.group(2).strip() == title:
            return match.start()
    return None


def slice_section(content_md: str, outline_tree: OutlineTree, node_id: str) -> SectionResponse:
    if node_id == PREFACE_NODE_ID:
        ordered = _sorted_sliceable_nodes(outline_tree.nodes)
        first_start = ordered[0].anchor.char_start if ordered else None
        if first_start is None and ordered:
            first_start = _fallback_char_start(content_md, ordered[0].title)
        end = first_start or 0
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

    node_map = {n.node_id: n for n in outline_tree.nodes}
    node = node_map.get(node_id)
    if node is None:
        raise KeyError(node_id)

    ordered = _sorted_sliceable_nodes(outline_tree.nodes)
    start = node.anchor.char_start
    if start is None:
        start = _fallback_char_start(content_md, node.title)
    if start is None:
        start = 0
    end = _section_end_char(node, ordered, node_map, len(content_md))
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

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest viewer/tests/unit/test_section_slice.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add viewer/viewer/services/section_slice.py viewer/tests/unit/test_section_slice.py
git commit -m "feat(viewer): slice section markdown by outline anchors"
```

---

### Task 5: 工作区校验与 Job 注册表

**Files:**
- Create: `viewer/viewer/services/workspace.py`
- Create: `viewer/viewer/services/job_registry.py`
- Create: `viewer/tests/unit/test_workspace.py`
- Create: `viewer/tests/unit/test_job_registry.py`

- [ ] **Step 1: Write the failing tests**

```python
# viewer/tests/unit/test_workspace.py
from __future__ import annotations

from pathlib import Path

import pytest

from viewer.services.workspace import validate_workspace


def test_validate_workspace_requires_outline_and_content(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "content.md").write_text("# Title\n", encoding="utf-8")

    with pytest.raises(ValueError, match="outline.json"):
        validate_workspace(ws)


def test_validate_workspace_ok(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "content.md").write_text("# Title\n", encoding="utf-8")
    (ws / "outline.json").write_text(
        '{"schema_version":"1.0","strategy":"flat_fallback","nodes":[]}',
        encoding="utf-8",
    )
    assert validate_workspace(ws) == ws.resolve()
```

```python
# viewer/tests/unit/test_job_registry.py
from __future__ import annotations

from viewer.models import JobState
from viewer.services.job_registry import JobRegistry


def test_job_registry_tracks_progress() -> None:
    registry = JobRegistry()
    registry.create("job1", "sess1")
    registry.update("job1", stage="outline", message="building outline", status="running")

    job = registry.get("job1")
    assert isinstance(job, JobState)
    assert job.stage == "outline"
    assert job.status == "running"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest viewer/tests/unit/test_workspace.py viewer/tests/unit/test_job_registry.py -v
```

Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# viewer/viewer/services/workspace.py
from __future__ import annotations

from pathlib import Path

from doc_chunk.workspace.layout import OutputWorkspace


def validate_workspace(path: Path) -> Path:
    workspace = OutputWorkspace.open_existing(path.resolve())
    if not workspace.content_path.exists():
        raise ValueError(f"content.md not found in {path}")
    if not workspace.outline_path.exists():
        raise ValueError(f"outline.json not found in {path}")
    return workspace.root
```

```python
# viewer/viewer/services/job_registry.py
from __future__ import annotations

from viewer.models import JobState


class JobRegistry:
    def __init__(self) -> None:
        self._jobs: dict[str, JobState] = {}

    def create(self, job_id: str, session_id: str) -> JobState:
        job = JobState(
            job_id=job_id,
            session_id=session_id,
            stage="extract",
            message="starting pipeline",
            status="running",
            error=None,
        )
        self._jobs[job_id] = job
        return job

    def get(self, job_id: str) -> JobState | None:
        return self._jobs.get(job_id)

    def update(self, job_id: str, **fields: object) -> JobState:
        job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(job_id)
        updated = job.model_copy(update=fields)
        self._jobs[job_id] = updated
        return updated
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest viewer/tests/unit/test_workspace.py viewer/tests/unit/test_job_registry.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add viewer/viewer/services/workspace.py viewer/viewer/services/job_registry.py viewer/tests/unit/test_workspace.py viewer/tests/unit/test_job_registry.py
git commit -m "feat(viewer): add workspace validation and job registry"
```

---

### Task 6: Pipeline 后台执行服务

**Files:**
- Create: `viewer/viewer/services/pipeline.py`
- Create: `viewer/tests/unit/test_pipeline_service.py`

- [ ] **Step 1: Write the failing test**

```python
# viewer/tests/unit/test_pipeline_service.py
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from doc_chunk.api import run_pipeline

from viewer.models import JobState
from viewer.services.job_registry import JobRegistry
from viewer.services.pipeline import PipelineService
from viewer.services.session_store import SessionStore
from viewer.models import SessionRecord
from datetime import UTC, datetime


@pytest.mark.asyncio
async def test_pipeline_service_marks_session_success(sample_docx: Path, tmp_path: Path) -> None:
  # reuse root conftest sample_docx via symlink: add viewer/tests/conftest.py importing parent fixture
    sessions = SessionStore(tmp_path / "sessions.json")
    jobs = JobRegistry()
    now = datetime.now(UTC).isoformat()
    session = SessionRecord(
        id="sess1",
        title="sample.docx",
        workspace_path=str(tmp_path / "ws"),
        source_type="upload",
        status="running",
        created_at=now,
        opened_at=now,
    )
    sessions.add(session)
    jobs.create("job1", "sess1")

    service = PipelineService(sessions=sessions, jobs=jobs, run_pipeline_fn=run_pipeline)
    await service.run_upload_job(
        job_id="job1",
        session_id="sess1",
        input_path=sample_docx,
        workspace_dir=tmp_path / "ws",
    )

    updated = sessions.get("sess1")
    assert updated is not None
    assert updated.status == "success"
    job = jobs.get("job1")
    assert job is not None
    assert job.status == "done"
    assert (tmp_path / "ws" / "outline.json").exists()
```

Also create fixture bridge:

```python
# viewer/tests/conftest.py
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

# import sample_docx from parent tests
from tests.conftest import sample_docx  # noqa: F401


@pytest.fixture
def viewer_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("DOC_CHUNK_VIEWER_DATA", str(tmp_path))
    return tmp_path
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest viewer/tests/unit/test_pipeline_service.py -v
```

Expected: FAIL `ModuleNotFoundError: viewer.services.pipeline`

- [ ] **Step 3: Write minimal implementation**

```python
# viewer/viewer/services/pipeline.py
from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path

from doc_chunk.api import run_pipeline
from doc_chunk.models.document import PipelineResult

from viewer.services.job_registry import JobRegistry
from viewer.services.session_store import SessionStore

_STAGE_MAP = {
    "extract": "extract",
    "outline": "outline",
    "tree": "tree",
    "chunk": "chunk",
    "enrich": "chunk",
}


class PipelineService:
    def __init__(
        self,
        *,
        sessions: SessionStore,
        jobs: JobRegistry,
        run_pipeline_fn: Callable[..., PipelineResult] = run_pipeline,
    ) -> None:
        self._sessions = sessions
        self._jobs = jobs
        self._run_pipeline = run_pipeline_fn

    def _on_progress(self, job_id: str, stage: str, payload: dict) -> None:
        mapped = _STAGE_MAP.get(stage, "chunk")
        message = str(payload.get("message", stage))
        self._jobs.update(job_id, stage=mapped, message=message, status="running")

    async def run_upload_job(
        self,
        *,
        job_id: str,
        session_id: str,
        input_path: Path,
        workspace_dir: Path,
    ) -> None:
        def _progress(stage: str, payload: dict) -> None:
            self._on_progress(job_id, stage, payload)

        def _execute() -> PipelineResult:
            return self._run_pipeline(
                input_path,
                workspace_dir,
                overwrite=True,
                skip_refine=True,
                skip_enrich=True,
                on_progress=_progress,
            )

        try:
            result = await asyncio.to_thread(_execute)
            if result.status == "failed":
                error = result.errors[0]["error"] if result.errors else "pipeline failed"
                self._jobs.update(job_id, stage="failed", message=error, status="failed", error=error)
                self._sessions.update(session_id, status="failed", error=error)
                return
            self._jobs.update(job_id, stage="done", message="pipeline complete", status="done")
            self._sessions.update(session_id, status="success", error=None)
        except Exception as exc:  # noqa: BLE001
            message = str(exc)
            self._jobs.update(job_id, stage="failed", message=message, status="failed", error=message)
            self._sessions.update(session_id, status="failed", error=message)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest viewer/tests/unit/test_pipeline_service.py -v
```

Expected: PASS (may take ~10s for real pipeline)

- [ ] **Step 5: Commit**

```bash
git add viewer/viewer/services/pipeline.py viewer/tests/conftest.py viewer/tests/unit/test_pipeline_service.py
git commit -m "feat(viewer): run doc_chunk pipeline in background thread"
```

---

### Task 7: FastAPI 应用与依赖注入

**Files:**
- Create: `viewer/viewer/main.py`
- Create: `viewer/viewer/deps.py`
- Modify: `viewer/viewer/__main__.py` (no change needed)

- [ ] **Step 1: Write the failing test**

```python
# viewer/tests/api/test_app_boot.py
from __future__ import annotations

from fastapi.testclient import TestClient

from viewer.main import create_app


def test_app_serves_index(viewer_data_dir) -> None:
    client = TestClient(create_app())
    response = client.get("/")
    assert response.status_code == 200
    assert "doc-chunk viewer" in response.text.lower() or "viewer" in response.text.lower()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest viewer/tests/api/test_app_boot.py -v
```

Expected: FAIL `ModuleNotFoundError: viewer.main`

- [ ] **Step 3: Write minimal implementation**

```python
# viewer/viewer/deps.py
from __future__ import annotations

from functools import lru_cache

from viewer.config import ViewerSettings
from viewer.services.job_registry import JobRegistry
from viewer.services.pipeline import PipelineService
from viewer.services.session_store import SessionStore


@lru_cache
def get_settings() -> ViewerSettings:
    return ViewerSettings.load()


def get_session_store() -> SessionStore:
    settings = get_settings()
    return SessionStore(settings.sessions_file, max_sessions=settings.max_sessions)


def get_job_registry() -> JobRegistry:
    return JobRegistry()


def get_pipeline_service() -> PipelineService:
    return PipelineService(sessions=get_session_store(), jobs=get_job_registry())
```

```python
# viewer/viewer/main.py
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from viewer.deps import get_settings
from viewer.routes import content, jobs, sessions, upload, workspaces

STATIC_DIR = Path(__file__).parent / "static"


def create_app() -> FastAPI:
    app = FastAPI(title="doc-chunk-viewer")
    app.include_router(sessions.router, prefix="/api")
    app.include_router(upload.router, prefix="/api")
    app.include_router(workspaces.router, prefix="/api")
    app.include_router(content.router, prefix="/api")
    app.include_router(jobs.router, prefix="/api")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


app = create_app()
```

Create route package stubs (empty routers) so import succeeds:

```python
# viewer/viewer/routes/__init__.py
```

```python
# viewer/viewer/routes/sessions.py
from fastapi import APIRouter

router = APIRouter(tags=["sessions"])
```

(Same pattern for `upload.py`, `workspaces.py`, `content.py`, `jobs.py`)

Create minimal `static/index.html`:

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>doc-chunk viewer</title></head>
<body><h1>doc-chunk viewer</h1></body>
</html>
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest viewer/tests/api/test_app_boot.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add viewer/viewer/main.py viewer/viewer/deps.py viewer/viewer/routes/ viewer/viewer/static/index.html viewer/tests/api/test_app_boot.py
git commit -m "feat(viewer): add FastAPI app skeleton and static mount"
```

---

### Task 8: Sessions / Workspaces / Jobs API 路由

**Files:**
- Modify: `viewer/viewer/routes/sessions.py`
- Modify: `viewer/viewer/routes/workspaces.py`
- Modify: `viewer/viewer/routes/jobs.py`
- Create: `viewer/tests/api/test_sessions_api.py`
- Create: `viewer/tests/api/test_workspaces_api.py`

- [ ] **Step 1: Write the failing tests**

```python
# viewer/tests/api/test_sessions_api.py
from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from viewer.deps import get_session_store
from viewer.main import create_app
from viewer.models import SessionRecord


def test_list_and_get_sessions(viewer_data_dir) -> None:
    client = TestClient(create_app())
    store = get_session_store()
    now = datetime.now(UTC).isoformat()
    store.add(
        SessionRecord(
            id="s1",
            title="demo",
            workspace_path="/tmp/ws",
            source_type="open",
            status="success",
            created_at=now,
            opened_at=now,
        )
    )

    listed = client.get("/api/sessions")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == "s1"

    detail = client.get("/api/sessions/s1")
    assert detail.status_code == 200
    assert detail.json()["title"] == "demo"
```

```python
# viewer/tests/api/test_workspaces_api.py
from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from viewer.main import create_app


def test_open_workspace_registers_session(viewer_data_dir, tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "content.md").write_text("# Title\n\nBody", encoding="utf-8")
    (ws / "outline.json").write_text(
        json.dumps({"schema_version": "1.0", "strategy": "flat_fallback", "nodes": []}),
        encoding="utf-8",
    )

    client = TestClient(create_app())
    response = client.post("/api/workspaces/open", json={"path": str(ws)})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["session_id"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest viewer/tests/api/test_sessions_api.py viewer/tests/api/test_workspaces_api.py -v
```

Expected: FAIL (404 or empty routes)

- [ ] **Step 3: Implement routes**

```python
# viewer/viewer/routes/sessions.py
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from viewer.deps import get_session_store

router = APIRouter(tags=["sessions"])


@router.get("/sessions")
def list_sessions() -> list[dict]:
    return [s.model_dump() for s in get_session_store().list_sessions()]


@router.get("/sessions/{session_id}")
def get_session(session_id: str) -> dict:
    session = get_session_store().get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return session.model_dump()


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str) -> dict:
    deleted = get_session_store().delete(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="session not found")
    return {"deleted": True}
```

```python
# viewer/viewer/routes/workspaces.py
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException

from viewer.deps import get_session_store
from viewer.models import OpenWorkspaceRequest, SessionRecord
from viewer.services.workspace import validate_workspace

router = APIRouter(tags=["workspaces"])


@router.post("/workspaces/open")
def open_workspace(body: OpenWorkspaceRequest) -> dict:
    try:
        workspace = validate_workspace(Path(body.path))
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    now = datetime.now(UTC).isoformat()
    session_id = str(uuid.uuid4())
    record = SessionRecord(
        id=session_id,
        title=workspace.name,
        workspace_path=str(workspace),
        source_type="open",
        status="success",
        created_at=now,
        opened_at=now,
        error=None,
    )
    get_session_store().add(record)
    return {"session_id": session_id, "status": "success"}
```

```python
# viewer/viewer/routes/jobs.py
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from viewer.deps import get_job_registry

router = APIRouter(tags=["jobs"])


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = get_job_registry().get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job.model_dump()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest viewer/tests/api/test_sessions_api.py viewer/tests/api/test_workspaces_api.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add viewer/viewer/routes/sessions.py viewer/viewer/routes/workspaces.py viewer/viewer/routes/jobs.py viewer/tests/api/
git commit -m "feat(viewer): add sessions, workspaces, and jobs API routes"
```

---

### Task 9: Content API（outline / section / assets）

**Files:**
- Modify: `viewer/viewer/routes/content.py`
- Create: `viewer/tests/api/test_content_api.py`
- Create: `viewer/tests/conftest.py` (add `pipeline_workspace` fixture)

Add to `viewer/tests/conftest.py`:

```python
@pytest.fixture
def pipeline_workspace(sample_docx: Path, tmp_path: Path) -> Path:
    from doc_chunk.api import run_pipeline

    workspace = tmp_path / "workspace"
    result = run_pipeline(sample_docx, workspace, overwrite=True, skip_refine=True, skip_enrich=True)
    assert result.status == "success"
    return workspace
```

- [ ] **Step 1: Write the failing test**

```python
# viewer/tests/api/test_content_api.py
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from viewer.deps import get_session_store
from viewer.main import create_app
from viewer.models import SessionRecord


def _register_session(workspace: Path) -> str:
    now = datetime.now(UTC).isoformat()
    session_id = "test-session"
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


def test_outline_and_section_endpoints(pipeline_workspace: Path, viewer_data_dir) -> None:
    client = TestClient(create_app())
    session_id = _register_session(pipeline_workspace)

    outline = client.get(f"/api/sessions/{session_id}/outline")
    assert outline.status_code == 200
    nodes = outline.json()["nodes"]
    assert len(nodes) >= 1

    node_id = nodes[0]["node_id"]
    section = client.get(f"/api/sessions/{session_id}/sections/{node_id}")
    assert section.status_code == 200
    assert section.json()["markdown"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest viewer/tests/api/test_content_api.py -v
```

Expected: FAIL 404

- [ ] **Step 3: Implement content routes**

```python
# viewer/viewer/routes/content.py
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from doc_chunk.models.outline import OutlineTree

from viewer.deps import get_session_store
from viewer.services.outline_tree import build_outline_response
from viewer.services.section_slice import slice_section
from viewer.services.workspace import validate_workspace

router = APIRouter(tags=["content"])


def _load_workspace(session_id: str) -> Path:
    session = get_session_store().get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return validate_workspace(Path(session.workspace_path))


@router.get("/sessions/{session_id}/outline")
def get_outline(session_id: str) -> dict:
    workspace = _load_workspace(session_id)
    outline = OutlineTree.model_validate_json((workspace / "outline.json").read_text(encoding="utf-8"))
    content_md = (workspace / "content.md").read_text(encoding="utf-8")
    return build_outline_response(outline, content_md).model_dump()


@router.get("/sessions/{session_id}/sections/{node_id}")
def get_section(session_id: str, node_id: str) -> dict:
    workspace = _load_workspace(session_id)
    outline = OutlineTree.model_validate_json((workspace / "outline.json").read_text(encoding="utf-8"))
    content_md = (workspace / "content.md").read_text(encoding="utf-8")
    try:
        return slice_section(content_md, outline, node_id).model_dump()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="outline node not found") from exc


@router.get("/sessions/{session_id}/assets/{asset_path:path}")
def get_asset(session_id: str, asset_path: str) -> FileResponse:
    workspace = _load_workspace(session_id)
    target = (workspace / asset_path).resolve()
    if not str(target).startswith(str(workspace.resolve())):
        raise HTTPException(status_code=400, detail="invalid asset path")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="asset not found")
    return FileResponse(target)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest viewer/tests/api/test_content_api.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add viewer/viewer/routes/content.py viewer/tests/api/test_content_api.py viewer/tests/conftest.py
git commit -m "feat(viewer): add outline, section, and asset API routes"
```

---

### Task 10: Upload API 与后台任务

**Files:**
- Modify: `viewer/viewer/routes/upload.py`
- Create: `viewer/tests/integration/test_upload_pipeline.py`

- [ ] **Step 1: Write the failing integration test**

```python
# viewer/tests/integration/test_upload_pipeline.py
from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from viewer.main import create_app


def test_upload_runs_pipeline_and_exposes_outline(sample_docx: Path, viewer_data_dir) -> None:
    client = TestClient(create_app())
    with sample_docx.open("rb") as handle:
        response = client.post(
            "/api/upload",
            files={"file": (sample_docx.name, handle, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
    assert response.status_code == 200
    body = response.json()
    session_id = body["session_id"]
    job_id = body["job_id"]

    for _ in range(120):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in {"done", "failed"}:
            break
        time.sleep(0.5)
    assert job["status"] == "done"

    outline = client.get(f"/api/sessions/{session_id}/outline")
    assert outline.status_code == 200
    assert outline.json()["nodes"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest viewer/tests/integration/test_upload_pipeline.py -v
```

Expected: FAIL 404 or 405 on `/api/upload`

- [ ] **Step 3: Implement upload route**

```python
# viewer/viewer/routes/upload.py
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile

from viewer.deps import get_job_registry, get_pipeline_service, get_session_store, get_settings
from viewer.models import SessionRecord, UploadResponse
from doc_chunk.extract.detect import detect_file_type
from doc_chunk.errors import UnsupportedFormatError

router = APIRouter(tags=["upload"])

_ALLOWED = {"docx", "pdf"}


@router.post("/upload", response_model=UploadResponse)
async def upload_file(background_tasks: BackgroundTasks, file: UploadFile) -> UploadResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="filename is required")

    settings = get_settings()
    session_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    workspace_dir = settings.workspaces_dir / session_id
    workspace_dir.mkdir(parents=True, exist_ok=True)

    dest = workspace_dir / file.filename
    content = await file.read()
    dest.write_bytes(content)

    try:
        file_type = detect_file_type(dest)
    except UnsupportedFormatError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if file_type not in _ALLOWED:
        raise HTTPException(status_code=400, detail=f"unsupported file type: {file_type}")

    now = datetime.now(UTC).isoformat()
    record = SessionRecord(
        id=session_id,
        title=file.filename,
        workspace_path=str(workspace_dir),
        source_type="upload",
        status="running",
        created_at=now,
        opened_at=now,
        error=None,
    )
    get_session_store().add(record)
    get_job_registry().create(job_id, session_id)

    service = get_pipeline_service()
    background_tasks.add_task(
        service.run_upload_job,
        job_id=job_id,
        session_id=session_id,
        input_path=dest,
        workspace_dir=workspace_dir,
    )
    return UploadResponse(session_id=session_id, job_id=job_id)
```

**Important:** `JobRegistry` and `SessionStore` must be singletons across requests. Update `deps.py`:

```python
@lru_cache
def get_job_registry() -> JobRegistry:
    return JobRegistry()
```

`BackgroundTasks` in TestClient runs after response — the integration test loop handles this.

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest viewer/tests/integration/test_upload_pipeline.py -v
```

Expected: PASS (≤60s)

- [ ] **Step 5: Commit**

```bash
git add viewer/viewer/routes/upload.py viewer/viewer/deps.py viewer/tests/integration/test_upload_pipeline.py
git commit -m "feat(viewer): add upload endpoint with background pipeline"
```

---

### Task 11: 前端单页（HTML / CSS / JS）

**Files:**
- Modify: `viewer/viewer/static/index.html`
- Create: `viewer/viewer/static/style.css`
- Create: `viewer/viewer/static/app.js`

- [ ] **Step 1: Implement static UI**

`index.html` 结构要点：
- 顶栏：`<input type="file" id="upload-input">`、`<input id="open-path">` + 打开按钮、`<select id="session-select">`
- 进度：`<div id="progress-bar">`
- 主体：`<aside id="outline-tree">` + `<main id="content-panel">`
- 引入 `/static/style.css`、`/static/app.js`、CDN `marked@12`

`app.js` 核心逻辑：

```javascript
const state = { sessionId: null, selectedNodeId: null, pollTimer: null };

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || response.statusText);
  }
  return response.json();
}

async function refreshSessions() {
  const sessions = await api("/api/sessions");
  const select = document.getElementById("session-select");
  select.innerHTML = "";
  for (const session of sessions) {
    const option = document.createElement("option");
    option.value = session.id;
    option.textContent = `${session.title} (${session.status})`;
    select.appendChild(option);
  }
  if (sessions.length && !state.sessionId) {
    state.sessionId = sessions[0].id;
    select.value = state.sessionId;
    await loadOutline();
  }
}

async function loadOutline() {
  const data = await api(`/api/sessions/${state.sessionId}/outline`);
  document.getElementById("outline-meta").textContent = `strategy: ${data.strategy}`;
  const container = document.getElementById("outline-tree");
  container.innerHTML = "";
  container.appendChild(renderNodes(data.nodes, 0));
}

function renderNodes(nodes, depth) {
  const ul = document.createElement("ul");
  for (const node of nodes) {
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.className = "tree-node";
    btn.style.paddingLeft = `${depth * 12}px`;
    btn.textContent = (node.needs_review ? "⚠ " : "") + node.title;
    btn.onclick = () => selectNode(node.node_id);
    li.appendChild(btn);
    if (node.children?.length) li.appendChild(renderNodes(node.children, depth + 1));
    ul.appendChild(li);
  }
  return ul;
}

async function selectNode(nodeId) {
  state.selectedNodeId = nodeId;
  const section = await api(`/api/sessions/${state.sessionId}/sections/${nodeId}`);
  const html = marked.parse(section.markdown, {
    mangle: false,
    headerIds: false,
  });
  document.getElementById("content-panel").innerHTML = html;
  document.getElementById("section-meta").textContent =
    `char: ${section.char_start}–${section.char_end} · needs_review: ${section.needs_review}`;
}

async function pollJob(jobId) {
  const bar = document.getElementById("progress-bar");
  bar.hidden = false;
  clearInterval(state.pollTimer);
  state.pollTimer = setInterval(async () => {
    const job = await api(`/api/jobs/${jobId}`);
    bar.textContent = `${job.stage}: ${job.message}`;
    if (job.status === "done") {
      clearInterval(state.pollTimer);
      bar.hidden = true;
      await refreshSessions();
      state.sessionId = job.session_id;
      document.getElementById("session-select").value = state.sessionId;
      await loadOutline();
    }
    if (job.status === "failed") {
      clearInterval(state.pollTimer);
      bar.textContent = job.error || "pipeline failed";
    }
  }, 1000);
}

document.getElementById("upload-input").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  const form = new FormData();
  form.append("file", file);
  const result = await api("/api/upload", { method: "POST", body: form });
  state.sessionId = result.session_id;
  await refreshSessions();
  await pollJob(result.job_id);
});

document.getElementById("open-btn").addEventListener("click", async () => {
  const path = document.getElementById("open-path").value.trim();
  const result = await api("/api/workspaces/open", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  });
  state.sessionId = result.session_id;
  await refreshSessions();
  await loadOutline();
});

document.getElementById("session-select").addEventListener("change", async (event) => {
  state.sessionId = event.target.value;
  await loadOutline();
});

refreshSessions().catch(console.error);
```

`style.css`：flex 布局，左栏 `width: 30%`，树按钮全宽左对齐，内容区 `overflow: auto`，进度条固定在顶栏下方。

- [ ] **Step 2: Manual smoke test**

```bash
python -m viewer
# 浏览器打开 http://127.0.0.1:8765
# 上传 tests 样例 docx，确认树与 Markdown 渲染
```

- [ ] **Step 3: Commit**

```bash
git add viewer/viewer/static/
git commit -m "feat(viewer): add static UI for upload, sessions, and outline browsing"
```

---

### Task 12: 文档与全量测试

**Files:**
- Modify: `viewer/README.md`
- Modify: root `README.md`（追加 viewer 小节）

- [ ] **Step 1: Update README**

在根 `README.md` 末尾追加：

```markdown
## Viewer（调试 UI）

```bash
pip install -e "./viewer[dev]"
python -m viewer
```

详见 [`viewer/README.md`](viewer/README.md)。
```

- [ ] **Step 2: Run full viewer test suite**

```bash
cd /Users/tongqianni/xlab/tender_skills
pip install -e ".[dev]"
pip install -e "./viewer[dev]"
python -m pytest viewer/tests/ -v
```

Expected: all PASS

- [ ] **Step 3: Commit**

```bash
git add viewer/README.md README.md
git commit -m "docs: document doc-chunk viewer usage"
```

---

## Spec Coverage Check

| Spec 要求 | 对应 Task |
|-----------|-----------|
| 上传 docx/pdf | Task 10 |
| pipeline skip refine/enrich | Task 6, 10 |
| 左侧 outline 树 | Task 3, 9, 11 |
| 右侧章节 Markdown | Task 4, 9, 11 |
| 打开已有工作区 | Task 5, 8 |
| 会话历史 20 条 | Task 2, 8 |
| 图片 assets 代理 | Task 9 |
| job 进度轮询 | Task 6, 8, 10, 11 |
| 本机 127.0.0.1 | Task 1 |
| AC-1~AC-7 测试 | Task 4, 8, 9, 10 |

无遗漏。

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-16-doc-chunk-viewer.md`.

**两种执行方式：**

**1. Subagent-Driven（推荐）** — 每个 Task 派发独立 subagent，任务间做代码审查，迭代快

**2. Inline Execution** — 在本会话用 executing-plans 按批次执行，设置检查点

你倾向哪种？
