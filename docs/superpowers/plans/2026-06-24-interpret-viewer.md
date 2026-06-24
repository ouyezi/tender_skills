# 招标解读 Viewer 页面 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 `viewer/` 应用中新增 `/interpret` 页面，支持上传 1～2 个招标文件、合并工作区、运行 tender_insights 解读与模版提取，并以分类 Tab 展示结果。

**Architecture:** 扩展 viewer 包：新增 `workspace_merge` 按上传顺序合并双 pipeline 工作区；`interpret_pipeline` 编排 pipeline → merge → interpret → template；独立 `InterpretSessionStore` 与 `InterpretJobRegistry` 避免污染现有切片会话；前端新增 `interpret.html` + `interpret.js`，切片预览页加导航与深链接。

**Tech Stack:** Python 3.11+, FastAPI, uvicorn, pydantic v2, doc_chunk, tender_insights, pytest, httpx TestClient, marked.js (CDN), 原生 JavaScript

**设计来源:** [`docs/superpowers/specs/2026-06-24-interpret-viewer-design.md`](../specs/2026-06-24-interpret-viewer-design.md)

**Worktree / 分支:** 从 `main` 创建 `006-interpret-viewer`

---

## File Structure

```text
viewer/
├── pyproject.toml                          # README 注明需 pip install -e ".[dev]"
├── README.md                               # 追加解读页说明
├── viewer/
│   ├── config.py                           # + interpret_sessions_file 属性
│   ├── models.py                           # + InterpretSessionRecord, InterpretJobState, InterpretResultResponse
│   ├── deps.py                             # + interpret session/job/pipeline getters
│   ├── main.py                             # + /interpret 路由与 interpret API router
│   ├── services/
│   │   ├── interpret_session_store.py      # interpret_sessions.json CRUD
│   │   ├── interpret_job_registry.py       # 解读 job 内存状态
│   │   ├── workspace_merge.py              # 双工作区合并
│   │   └── interpret_pipeline.py           # pipeline → merge → interpret → template
│   ├── routes/
│   │   └── interpret.py                    # 解读 API 端点
│   └── static/
│       ├── index.html                      # 顶栏导航
│       ├── app.js                          # URL ?session=&node= 深链接
│       ├── interpret.html                  # 解读页
│       ├── interpret.js                    # 解读页逻辑
│       └── style.css                       # 共用样式扩展
└── tests/
    ├── unit/
    │   ├── test_workspace_merge.py
    │   └── test_interpret_session_store.py
    ├── api/
    │   └── test_interpret_api.py
    └── integration/
        ├── test_interpret_single_file.py
        └── test_interpret_dual_file.py
```

---

### Task 1: 配置与解读会话模型

**Files:**
- Modify: `viewer/viewer/config.py`
- Modify: `viewer/viewer/models.py`
- Create: `viewer/viewer/services/interpret_session_store.py`
- Create: `viewer/tests/unit/test_interpret_session_store.py`

- [ ] **Step 1: Write the failing test**

```python
# viewer/tests/unit/test_interpret_session_store.py
from __future__ import annotations

from viewer.models import InterpretSessionRecord
from viewer.services.interpret_session_store import InterpretSessionStore


def test_add_and_list_interpret_sessions(tmp_path) -> None:
    store = InterpretSessionStore(tmp_path / "interpret_sessions.json", max_sessions=20)
    record = InterpretSessionRecord(
        id="s1",
        title="bid.docx",
        workspace_path=str(tmp_path / "ws"),
        source_files=["bid.docx"],
        status="pending",
        created_at="2026-06-24T00:00:00+00:00",
        opened_at="2026-06-24T00:00:00+00:00",
        error=None,
    )
    store.add(record)
    sessions = store.list_sessions()
    assert len(sessions) == 1
    assert sessions[0].source_files == ["bid.docx"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/tongqianni/xlab/tender_skills
source .venv/bin/activate
pip install -e ".[dev]"
pip install -e "./viewer[dev]"
python -m pytest viewer/tests/unit/test_interpret_session_store.py -v
```

Expected: FAIL `ModuleNotFoundError` or `ImportError: cannot import name 'InterpretSessionRecord'`

- [ ] **Step 3: Write minimal implementation**

在 `viewer/viewer/config.py` 追加：

```python
    @property
    def interpret_sessions_file(self) -> Path:
        return self.data_dir / "interpret_sessions.json"

    @property
    def interpret_uploads_dir(self) -> Path:
        return self.data_dir / "uploads" / "interpret"
```

在 `viewer/viewer/models.py` 追加：

```python
class InterpretSessionRecord(BaseModel):
    id: str
    title: str
    workspace_path: str
    source_files: list[str]
    status: Literal["pending", "running", "success", "failed"]
    created_at: str
    opened_at: str
    error: str | None = None


class InterpretJobState(BaseModel):
    job_id: str
    session_id: str
    stage: Literal[
        "pipeline_1",
        "pipeline_2",
        "merge",
        "interpret",
        "template",
        "done",
        "failed",
    ]
    message: str
    status: Literal["running", "done", "failed"]
    error: str | None = None


class InterpretUploadResponse(BaseModel):
    session_id: str
    job_id: str


class InterpretResultResponse(BaseModel):
    interpretation: dict
    templates: dict
    source_files: list[str]
```

创建 `viewer/viewer/services/interpret_session_store.py`（结构与 `session_store.py` 相同，操作 `InterpretSessionRecord`）。

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest viewer/tests/unit/test_interpret_session_store.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add viewer/viewer/config.py viewer/viewer/models.py viewer/viewer/services/interpret_session_store.py viewer/tests/unit/test_interpret_session_store.py
git commit -m "feat(viewer): add interpret session models and store"
```

---

### Task 2: 工作区合并服务

**Files:**
- Create: `viewer/viewer/services/workspace_merge.py`
- Create: `viewer/tests/unit/test_workspace_merge.py`

- [ ] **Step 1: Write the failing test**

```python
# viewer/tests/unit/test_workspace_merge.py
from __future__ import annotations

import json
from pathlib import Path

import pytest

from viewer.services.workspace_merge import merge_workspaces, validate_merged_workspace


def _write_minimal_workspace(
    root: Path,
    *,
    content: str,
    nodes: list[dict],
    images: dict[str, bytes] | None = None,
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "content.md").write_text(content, encoding="utf-8")
    outline = {
        "schema_version": "1.0",
        "strategy": "heading_heuristic",
        "nodes": nodes,
    }
    (root / "outline.json").write_text(json.dumps(outline), encoding="utf-8")
    if images:
        img_dir = root / "images"
        img_dir.mkdir(exist_ok=True)
        for name, data in images.items():
            (img_dir / name).write_bytes(data)
    return root


def test_merge_offsets_second_file_nodes(tmp_path: Path) -> None:
    ws1 = _write_minimal_workspace(
        tmp_path / "ws1",
        content="# A\n\nalpha",
        nodes=[
            {
                "node_id": "n-001",
                "title": "A",
                "level": 1,
                "parent_id": None,
                "sort_order": 0,
                "anchor": {"char_start": 0, "char_end": 10},
            }
        ],
    )
    ws2 = _write_minimal_workspace(
        tmp_path / "ws2",
        content="# B\n\nbeta",
        nodes=[
            {
                "node_id": "n-001",
                "title": "B",
                "level": 1,
                "parent_id": None,
                "sort_order": 0,
                "anchor": {"char_start": 0, "char_end": 9},
            }
        ],
    )
    target = tmp_path / "merged"
    merge_workspaces(
        target,
        sources=[(ws1, "file1.docx"), (ws2, "file2.docx")],
    )
    merged_content = (target / "content.md").read_text(encoding="utf-8")
    assert merged_content.startswith("# A\n\nalpha")
    assert "<!-- source: file2.docx -->" in merged_content
    assert merged_content.endswith("beta\n") or merged_content.endswith("beta")

    outline = json.loads((target / "outline.json").read_text(encoding="utf-8"))
    node_ids = {n["node_id"] for n in outline["nodes"]}
    assert "n-001" in node_ids
    assert "m2:n-001" in node_ids

    m2 = next(n for n in outline["nodes"] if n["node_id"] == "m2:n-001")
    offset = len("# A\n\nalpha\n\n<!-- source: file2.docx -->\n")
    assert m2["anchor"]["char_start"] == 0 + offset
    validate_merged_workspace(target)


def test_merge_renames_conflicting_images(tmp_path: Path) -> None:
    ws1 = _write_minimal_workspace(
        tmp_path / "ws1",
        content="![a](images/logo.png)",
        nodes=[],
        images={"logo.png": b"1"},
    )
    ws2 = _write_minimal_workspace(
        tmp_path / "ws2",
        content="![b](images/logo.png)",
        nodes=[],
        images={"logo.png": b"2"},
    )
    target = tmp_path / "merged"
    merge_workspaces(target, sources=[(ws1, "a.docx"), (ws2, "b.docx")])
    assert (target / "images" / "logo.png").read_bytes() == b"1"
    assert (target / "images" / "m2_logo.png").read_bytes() == b"2"
    content = (target / "content.md").read_text(encoding="utf-8")
    assert "images/m2_logo.png" in content.split("<!-- source:")[1]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest viewer/tests/unit/test_workspace_merge.py -v
```

Expected: FAIL `ModuleNotFoundError: No module named 'viewer.services.workspace_merge'`

- [ ] **Step 3: Write minimal implementation**

创建 `viewer/viewer/services/workspace_merge.py`：

```python
from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from doc_chunk.models.outline import OutlineNode, OutlineTree
from doc_chunk.workspace.layout import OutputWorkspace


def _separator(file2_name: str) -> str:
    return f"\n\n<!-- source: {file2_name} -->\n"


def _remap_node(node: OutlineNode, *, prefix: str, offset: int, sort_shift: int) -> OutlineNode:
    data = node.model_dump()
    data["node_id"] = f"{prefix}{node.node_id}"
    if node.parent_id:
        data["parent_id"] = f"{prefix}{node.parent_id}"
    data["sort_order"] = node.sort_order + sort_shift
    anchor = dict(data.get("anchor") or {})
    for key in ("char_start", "char_end", "block_start", "block_end"):
        if anchor.get(key) is not None:
            anchor[key] = int(anchor[key]) + offset
    data["anchor"] = anchor
    return OutlineNode.model_validate(data)


def _copy_images(src_ws: Path, dst_images: Path, *, rename_prefix: str = "") -> dict[str, str]:
    mapping: dict[str, str] = {}
    src_images = src_ws / "images"
    if not src_images.exists():
        return mapping
    dst_images.mkdir(parents=True, exist_ok=True)
    for src_file in src_images.iterdir():
        if not src_file.is_file():
            continue
        name = src_file.name
        dst_name = f"{rename_prefix}{name}" if rename_prefix and (dst_images / name).exists() else name
        if rename_prefix and (dst_images / name).exists():
            dst_name = f"{rename_prefix}{name}"
        shutil.copy2(src_file, dst_images / dst_name)
        if dst_name != name:
            mapping[name] = dst_name
    return mapping


def merge_workspaces(
    target: Path,
    *,
    sources: list[tuple[Path, str]],
) -> Path:
    if len(sources) < 2:
        raise ValueError("merge_workspaces requires at least two sources")
    target.mkdir(parents=True, exist_ok=True)
    ws1_path, file1_name = sources[0]
    ws2_path, file2_name = sources[1]

    ws1 = OutputWorkspace.open_existing(ws1_path)
    ws2 = OutputWorkspace.open_existing(ws2_path)
    content1 = ws1.content_path.read_text(encoding="utf-8")
    content2 = ws2.content_path.read_text(encoding="utf-8")
    sep = _separator(file2_name)
    merged_content = content1 + sep + content2
    offset2 = len(content1) + len(sep)

    outline1 = OutlineTree.model_validate_json(ws1.outline_path.read_text(encoding="utf-8"))
    outline2 = OutlineTree.model_validate_json(ws2.outline_path.read_text(encoding="utf-8"))
    max_sort = max((n.sort_order for n in outline1.nodes), default=-1) + 1
    merged_nodes = list(outline1.nodes)
    for node in outline2.nodes:
        merged_nodes.append(_remap_node(node, prefix="m2:", offset=offset2, sort_shift=max_sort))

    merged_outline = OutlineTree(
        strategy=outline1.strategy,
        nodes=merged_nodes,
        derived_from=f"merged:{file1_name}+{file2_name}",
    )

    target_ws = OutputWorkspace(target)
    target_ws.content_path.write_text(merged_content, encoding="utf-8")
    target_ws.outline_path.write_text(
        merged_outline.model_dump_json(indent=2),
        encoding="utf-8",
    )

    images_dir = target_ws.root / "images"
    _copy_images(ws1.root, images_dir)
    image_map = _copy_images(ws2.root, images_dir, rename_prefix="m2_")
    if image_map:
        tail = merged_content.split(sep, 1)[1]
        for old, new in image_map.items():
            tail = tail.replace(f"images/{old}", f"images/{new}")
        merged_content = merged_content.split(sep, 1)[0] + sep + tail
        target_ws.content_path.write_text(merged_content, encoding="utf-8")

    manifest = {
        "sources": [file1_name, file2_name],
        "merged_at": datetime.now(UTC).isoformat(),
    }
    (target_ws.root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return target_ws.root


def validate_merged_workspace(workspace: Path) -> None:
    ws = OutputWorkspace.open_existing(workspace)
    content = ws.content_path.read_text(encoding="utf-8")
    outline = OutlineTree.model_validate_json(ws.outline_path.read_text(encoding="utf-8"))
    node_ids = set()
    for node in outline.nodes:
        if node.node_id in node_ids:
            raise ValueError(f"duplicate node_id: {node.node_id}")
        node_ids.add(node.node_id)
        if node.parent_id and node.parent_id not in node_ids:
            raise ValueError(f"invalid parent_id: {node.parent_id}")
        if node.anchor.char_start is not None and node.anchor.char_end is not None:
            if not (0 <= node.anchor.char_start < node.anchor.char_end <= len(content)):
                raise ValueError(f"invalid anchor for {node.node_id}")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest viewer/tests/unit/test_workspace_merge.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add viewer/viewer/services/workspace_merge.py viewer/tests/unit/test_workspace_merge.py
git commit -m "feat(viewer): add dual-workspace merge service"
```

---

### Task 3: 解读 Job Registry 与 Pipeline 服务

**Files:**
- Create: `viewer/viewer/services/interpret_job_registry.py`
- Create: `viewer/viewer/services/interpret_pipeline.py`
- Modify: `viewer/viewer/deps.py`

- [ ] **Step 1: Write the failing test**

```python
# viewer/tests/unit/test_interpret_pipeline.py
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from doc_chunk.api import run_pipeline
from doc_chunk.llm.client import FakeLLMClient

from viewer.services.interpret_job_registry import InterpretJobRegistry
from viewer.services.interpret_pipeline import InterpretPipelineService
from viewer.services.interpret_session_store import InterpretSessionStore
from viewer.models import InterpretSessionRecord


@pytest.mark.asyncio
async def test_single_file_interpret_pipeline(sample_docx: Path, tmp_path: Path) -> None:
    sessions = InterpretSessionStore(tmp_path / "interpret_sessions.json")
    jobs = InterpretJobRegistry()
    session_id = "sess-1"
    job_id = "job-1"
    workspace_dir = tmp_path / "workspaces" / session_id
    workspace_dir.mkdir(parents=True)
    sessions.add(
        InterpretSessionRecord(
            id=session_id,
            title=sample_docx.name,
            workspace_path=str(workspace_dir),
            source_files=[sample_docx.name],
            status="running",
            created_at="2026-06-24T00:00:00+00:00",
            opened_at="2026-06-24T00:00:00+00:00",
        )
    )
    jobs.create(job_id, session_id)

    fake_llm = FakeLLMClient(
        default_response=json.dumps(
            {
                "disqualification_items": [],
                "scoring_items": [],
                "bid_risk_items": [],
                "directory_requirements": [],
            }
        )
    )
    service = InterpretPipelineService(
        sessions=sessions,
        jobs=jobs,
        llm_client_factory=lambda: fake_llm,
    )
    await service.run_job(
        job_id=job_id,
        session_id=session_id,
        input_paths=[sample_docx],
        workspace_dir=workspace_dir,
    )
    job = jobs.get(job_id)
    assert job is not None
    assert job.status == "done"
    assert (workspace_dir / "interpretation.json").exists()
    assert (workspace_dir / "templates").exists() or (workspace_dir / "templates" / "index.json").exists()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest viewer/tests/unit/test_interpret_pipeline.py -v
```

Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

`interpret_job_registry.py`（镜像 `job_registry.py`，初始 stage=`pipeline_1`）。

`interpret_pipeline.py` 核心逻辑：

```python
class InterpretPipelineService:
    def __init__(self, *, sessions, jobs, llm_client_factory=None, run_pipeline_fn=run_pipeline):
        ...

    async def run_job(self, *, job_id, session_id, input_paths: list[Path], workspace_dir: Path) -> None:
        try:
            temp_dirs: list[Path] = []
            for idx, input_path in enumerate(input_paths, start=1):
                stage = f"pipeline_{idx}"
                self._jobs.update(job_id, stage=stage, message=f"extracting file {idx}")
                temp = workspace_dir.parent / f"{session_id}_tmp{idx}"
                temp_dirs.append(temp)
                result = await asyncio.to_thread(
                    self._run_pipeline,
                    input_path,
                    temp,
                    overwrite=True,
                    skip_refine=True,
                    skip_enrich=True,
                )
                if result.status == "failed":
                    raise RuntimeError(result.errors[0]["error"] if result.errors else "pipeline failed")

            if len(input_paths) == 1:
                shutil.copytree(temp_dirs[0], workspace_dir, dirs_exist_ok=True)
            else:
                self._jobs.update(job_id, stage="merge", message="merging workspaces")
                merge_workspaces(
                    workspace_dir,
                    sources=[(temp_dirs[0], input_paths[0].name), (temp_dirs[1], input_paths[1].name)],
                )
                validate_merged_workspace(workspace_dir)

            ws = OutputWorkspace.open_existing(workspace_dir)
            client = self._llm_client_factory()
            self._jobs.update(job_id, stage="interpret", message="running interpret")
            interpret_document(ws, client=client)
            self._jobs.update(job_id, stage="template", message="extracting templates")
            extract_templates(ws, client=client)
            self._jobs.update(job_id, stage="done", message="complete", status="done")
            self._sessions.update(session_id, status="success", error=None)
        except Exception as exc:
            self._jobs.update(job_id, stage="failed", message=str(exc), status="failed", error=str(exc))
            self._sessions.update(session_id, status="failed", error=str(exc))
        finally:
            for temp in temp_dirs:
                shutil.rmtree(temp, ignore_errors=True)
```

在 `deps.py` 追加 `get_interpret_session_store`、`get_interpret_job_registry`、`get_interpret_pipeline_service`（测试时可 monkeypatch factory）。

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest viewer/tests/unit/test_interpret_pipeline.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add viewer/viewer/services/interpret_job_registry.py viewer/viewer/services/interpret_pipeline.py viewer/viewer/deps.py viewer/tests/unit/test_interpret_pipeline.py
git commit -m "feat(viewer): add interpret pipeline service with FakeLLM hook"
```

---

### Task 4: 解读 API 路由

**Files:**
- Create: `viewer/viewer/routes/interpret.py`
- Modify: `viewer/viewer/main.py`
- Create: `viewer/tests/api/test_interpret_api.py`

- [ ] **Step 1: Write the failing test**

```python
# viewer/tests/api/test_interpret_api.py
from __future__ import annotations

from fastapi.testclient import TestClient

from viewer.main import create_app


def test_interpret_page_served() -> None:
    client = TestClient(create_app())
    response = client.get("/interpret")
    assert response.status_code == 200
    assert "招标解读" in response.text


def test_interpret_upload_requires_file1(viewer_data_dir) -> None:
    client = TestClient(create_app())
    response = client.post("/api/interpret/upload", files={})
    assert response.status_code == 422 or response.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest viewer/tests/api/test_interpret_api.py -v
```

Expected: FAIL `404` on `/interpret`

- [ ] **Step 3: Write minimal implementation**

`viewer/viewer/routes/interpret.py`：

```python
router = APIRouter(prefix="/interpret", tags=["interpret"])

@router.post("/upload", response_model=InterpretUploadResponse)
async def upload_interpret(background_tasks: BackgroundTasks, file1: UploadFile = File(...), file2: UploadFile | None = File(None)):
    # 校验 docx/pdf，写 uploads/interpret/<session_id>/
    # 创建 InterpretSessionRecord，启动 interpret pipeline background task
    ...

@router.get("/jobs/{job_id}", response_model=InterpretJobState)
def get_interpret_job(job_id: str): ...

@router.get("/sessions", response_model=list[InterpretSessionRecord])
def list_interpret_sessions(): ...

@router.get("/sessions/{session_id}", response_model=InterpretSessionRecord)
def get_interpret_session(session_id: str): ...

@router.get("/sessions/{session_id}/result", response_model=InterpretResultResponse)
def get_interpret_result(session_id: str):
    # 读 workspace/interpretation.json 与 templates/index.json
    ...

@router.get("/sessions/{session_id}/sections/{node_id}")
def get_interpret_section(session_id: str, node_id: str):
    # 复用 slice_section，从 interpret session 的 workspace_path 加载
    ...
```

`main.py` 追加：

```python
from viewer.routes import interpret

@app.get("/interpret")
def interpret_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "interpret.html")

app.include_router(interpret.router, prefix="/api")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest viewer/tests/api/test_interpret_api.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add viewer/viewer/routes/interpret.py viewer/viewer/main.py viewer/tests/api/test_interpret_api.py
git commit -m "feat(viewer): add interpret REST API and /interpret page route"
```

---

### Task 5: 解读页前端

**Files:**
- Create: `viewer/viewer/static/interpret.html`
- Create: `viewer/viewer/static/interpret.js`
- Modify: `viewer/viewer/static/style.css`

- [ ] **Step 1: Create interpret.html 骨架**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>招标解读</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body class="interpret-page">
  <header class="top-bar">
    <nav class="nav-tabs">
      <a href="/">切片预览</a>
      <a href="/interpret" class="active">招标解读</a>
    </nav>
  </header>
  <section class="upload-panel">
    <label>文件 1（必填）<input type="file" id="file1-input" accept=".docx,.pdf"></label>
    <label>补充文件（可选）<input type="file" id="file2-input" accept=".docx,.pdf"></label>
    <button type="button" id="start-btn">开始解读</button>
    <select id="interpret-session-select"></select>
  </section>
  <div id="interpret-progress" class="progress-steps" hidden></div>
  <section id="result-panel" hidden>
    <div class="tab-bar" id="result-tabs"></div>
    <div id="result-cards" class="card-list"></div>
  </section>
  <aside id="source-panel" class="source-panel" hidden>
    <button type="button" id="close-source-panel">关闭</button>
    <div id="source-content"></div>
  </aside>
  <script src="https://cdn.jsdelivr.net/npm/marked@12/marked.min.js"></script>
  <script src="/static/interpret.js"></script>
</body>
</html>
```

- [ ] **Step 2: Implement interpret.js**

核心函数：

```javascript
const STAGES = ["pipeline_1", "pipeline_2", "merge", "interpret", "template"];
const STAGE_LABELS = {
  pipeline_1: "提取文件 1",
  pipeline_2: "提取文件 2",
  merge: "合并工作区",
  interpret: "解读招标",
  template: "提取模版",
};

async function startInterpret() { /* FormData file1/file2 → POST /api/interpret/upload */ }
async function pollInterpretJob(jobId) { /* 1s 轮询 /api/interpret/jobs/{id} */ }
async function loadResult(sessionId) { /* GET result → renderTabs() */ }
function renderCard(item, tabKey) { /* 构建卡片 + 查看原文 + 切片预览链接 */ }
async function openSourcePanel(sessionId, nodeId) { /* GET sections API */ }
```

单文件时进度条隐藏 `pipeline_2` 与 `merge` 步骤。

- [ ] **Step 3: Extend style.css**

追加 `.nav-tabs`、`.progress-steps`、`.card-list`、`.severity-badge`、`.source-panel` 样式，与现有 `top-bar` 风格一致。

- [ ] **Step 4: Manual smoke**

```bash
python -m viewer
# 浏览器打开 http://127.0.0.1:8765/interpret
# 确认导航、上传区、进度条 DOM 存在
```

- [ ] **Step 5: Commit**

```bash
git add viewer/viewer/static/interpret.html viewer/viewer/static/interpret.js viewer/viewer/static/style.css
git commit -m "feat(viewer): add interpret page UI"
```

---

### Task 6: 切片预览页导航与深链接

**Files:**
- Modify: `viewer/viewer/static/index.html`
- Modify: `viewer/viewer/static/app.js`
- Modify: `viewer/viewer/static/style.css`

- [ ] **Step 1: Add nav to index.html**

在 `<header class="top-bar">` 内最前面插入：

```html
<nav class="nav-tabs">
  <a href="/" class="active">切片预览</a>
  <a href="/interpret">招标解读</a>
</nav>
```

- [ ] **Step 2: Support URL params in app.js**

在文件末尾 `refreshSessions()` 之前追加：

```javascript
async function bootstrapFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const sessionId = params.get("session");
  const nodeId = params.get("node");
  await refreshSessions();
  if (sessionId) {
    state.sessionId = sessionId;
    const select = document.getElementById("session-select");
    if (select) select.value = sessionId;
    await loadOutline();
    if (nodeId) {
      state.selectedNodeId = nodeId;
      await loadSection(nodeId);
      markTreeSelection(nodeId);
    }
  }
}

bootstrapFromUrl().catch(console.error);
```

删除或替换原来的 `refreshSessions().catch(console.error);`。

- [ ] **Step 3: Verify deep link**

```bash
# 上传样例后访问：
# http://127.0.0.1:8765/?session=<id>&node=n-001
```

- [ ] **Step 4: Commit**

```bash
git add viewer/viewer/static/index.html viewer/viewer/static/app.js viewer/viewer/static/style.css
git commit -m "feat(viewer): add nav tabs and session deep links"
```

---

### Task 7: 集成测试（单文件 + 双文件）

**Files:**
- Create: `viewer/tests/integration/test_interpret_single_file.py`
- Create: `viewer/tests/integration/test_interpret_dual_file.py`
- Modify: `viewer/tests/conftest.py`

- [ ] **Step 1: Add FakeLLM app fixture**

在 `conftest.py` 追加：

```python
@pytest.fixture
def interpret_client(viewer_data_dir, monkeypatch):
    import json
    from doc_chunk.llm.client import FakeLLMClient
    from fastapi.testclient import TestClient
    from viewer.deps import get_interpret_pipeline_service
    from viewer.main import create_app
    from viewer.services.interpret_pipeline import InterpretPipelineService

    fake = FakeLLMClient(
        default_response=json.dumps(
            {
                "disqualification_items": [
                    {
                        "id": "dq-001",
                        "title": "测试废标",
                        "summary": "摘要",
                        "trigger_condition": "条件",
                        "source_excerpt": "原文",
                        "section_path": ["第一章"],
                        "confidence": 0.9,
                    }
                ],
                "scoring_items": [],
                "bid_risk_items": [],
                "directory_requirements": [],
            }
        )
    )

    def factory():
        from viewer.deps import get_interpret_job_registry, get_interpret_session_store
        return InterpretPipelineService(
            sessions=get_interpret_session_store(),
            jobs=get_interpret_job_registry(),
            llm_client_factory=lambda: fake,
        )

    app = create_app()
    app.dependency_overrides[get_interpret_pipeline_service] = factory
    return TestClient(app)
```

（若 pipeline service 非 FastAPI Depends 注入，改为 monkeypatch `get_interpret_pipeline_service` 返回值。）

- [ ] **Step 2: Single-file integration test**

```python
# viewer/tests/integration/test_interpret_single_file.py
import time

def test_single_file_upload_and_result(interpret_client, sample_docx):
    with sample_docx.open("rb") as f:
        resp = interpret_client.post(
            "/api/interpret/upload",
            files={"file1": (sample_docx.name, f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
    assert resp.status_code == 200
    body = resp.json()
    for _ in range(180):
        job = interpret_client.get(f"/api/interpret/jobs/{body['job_id']}").json()
        if job["status"] in {"done", "failed"}:
            break
        time.sleep(0.5)
    assert job["status"] == "done"
    result = interpret_client.get(f"/api/interpret/sessions/{body['session_id']}/result")
    assert result.status_code == 200
    data = result.json()
    assert data["source_files"] == [sample_docx.name]
    assert len(data["interpretation"]["disqualification_items"]) >= 1
```

- [ ] **Step 3: Dual-file integration test**

```python
# viewer/tests/integration/test_interpret_dual_file.py
def test_dual_file_merge(interpret_client, sample_docx, tmp_path):
    docx2 = ...  # 复用 conftest 再建一个 sample docx 或复制 sample_docx
    with sample_docx.open("rb") as f1, docx2.open("rb") as f2:
        resp = interpret_client.post(
            "/api/interpret/upload",
            files={
                "file1": (sample_docx.name, f1, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
                "file2": ("supplement.docx", f2, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
            },
        )
    ...
    ws = Path(session["workspace_path"])
    content = (ws / "content.md").read_text(encoding="utf-8")
    assert "<!-- source: supplement.docx -->" in content
    outline = json.loads((ws / "outline.json").read_text())
    assert any(n["node_id"].startswith("m2:") for n in outline["nodes"])
```

- [ ] **Step 4: Run integration tests**

```bash
python -m pytest viewer/tests/integration/test_interpret_single_file.py viewer/tests/integration/test_interpret_dual_file.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add viewer/tests/conftest.py viewer/tests/integration/test_interpret_single_file.py viewer/tests/integration/test_interpret_dual_file.py
git commit -m "test(viewer): add interpret integration tests with FakeLLM"
```

---

### Task 8: 文档与全量测试

**Files:**
- Modify: `viewer/README.md`
- Modify: root `README.md`（可选，追加解读页一句）

- [ ] **Step 1: Update viewer README**

追加章节：

```markdown
## 招标解读页

```bash
export LLM_API_KEY=sk-...
python -m viewer
# → http://127.0.0.1:8765/interpret
```

支持上传 1～2 个招标文件（按上传顺序合并），运行解读与模版提取。
```

更新 REST API 表格，列出 `/api/interpret/*` 端点。

- [ ] **Step 2: Run full viewer test suite**

```bash
python -m pytest viewer/tests/ -v
```

Expected: all PASS

- [ ] **Step 3: Commit**

```bash
git add viewer/README.md README.md
git commit -m "docs(viewer): document interpret page and API"
```

---

## Spec Coverage Checklist

| Spec 要求 | Task |
|-----------|------|
| 独立 `/interpret` 页面 | Task 4, 5 |
| 1～2 文件上传 | Task 4 |
| 按上传顺序合并工作区 | Task 2, 3, 7 |
| interpret + template | Task 3 |
| 五类 Tab 展示 | Task 5 |
| 解读会话历史 | Task 1, 4, 5 |
| 原文侧栏 + 切片预览深链接 | Task 5, 6 |
| LLM 未配置错误提示 | Task 3（异常 message）, Task 5（展示 error） |
| FakeLLM 测试 | Task 3, 7 |
| Out of scope 不做 | 无对应 task（符合 YAGNI） |
