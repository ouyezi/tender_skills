# tender-insights CLI 与 Viewer 编排对齐 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将工作区合并、pipeline 编排、解读任务与 Markdown 报告渲染内聚到 `tender_insights`，使 CLI 与 Viewer 共用同一套 API，并支持双文件命令行解读。

**Architecture:** 在 `tender_insights/common/` 新增 `workspace_merge` 与 `pipeline_runner`；扩展 `api.py` 为编排门面；CLI 通过 `prepare_workspaces` + `run_interpret_job` + `render` 子命令暴露能力；Viewer 改为调用 API 而非内联逻辑。

**Tech Stack:** Python 3.11+, Typer, Pydantic, pytest, 现有 `doc_chunk` / `tender_insights` 包

**Spec:** [`docs/superpowers/specs/2026-06-24-tender-insights-cli-parity-design.md`](../specs/2026-06-24-tender-insights-cli-parity-design.md)

---

## 当前进度

**已完成（2026-06-24）** — 全部 Task 1–8 已实现，`tests/tender_insights/` 77 passed，`viewer/tests/` 37 passed。

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `src/tender_insights/common/workspace_merge.py` | 双工作区 content/outline/images 合并与校验 |
| `src/tender_insights/common/pipeline_runner.py` | `INSIGHTS_PIPELINE_KWARGS`、`prepare_workspaces()` |
| `src/tender_insights/api.py` | 对外门面：`prepare_workspaces`、`run_interpret_job`、`render_interpretation_report` |
| `src/tender_insights/interpret/render.py` | `interpretation.json` → Markdown |
| `src/tender_insights/cli/main.py` | `interpret` 多文件、`render` 子命令 |
| `viewer/viewer/services/workspace_merge.py` | thin re-export（兼容旧 import） |
| `viewer/viewer/services/interpret_pipeline.py` | 调用 `api.prepare_workspaces` + `api.run_interpret_job` |

---

### Task 1: 修复 API 断裂并补齐 re-export

**Files:**
- Modify: `src/tender_insights/api.py`
- Test: `tests/tender_insights/unit/test_import.py`

- [ ] **Step 1: 补全 import**

在 `api.py` 增加：

```python
from tender_insights.interpret.extractor import interpret_workspace
```

- [ ] **Step 2: re-export `prepare_workspaces`**

`api.py` 已有 `from tender_insights.common.pipeline_runner import prepare_workspaces`，确认 `cli/main.py` 可 `from tender_insights.api import prepare_workspaces`。

- [ ] **Step 3: 验证 import**

Run: `.venv/bin/python -c "from tender_insights.api import prepare_workspaces, run_interpret_job, render_interpretation_report"`

Expected: 无 ImportError

- [ ] **Step 4: 更新 test_import（若存在）**

Run: `.venv/bin/pytest tests/tender_insights/unit/test_import.py -v`

---

### Task 2: 迁移 workspace_merge 测试

**Files:**
- Create: `tests/tender_insights/unit/test_workspace_merge.py`
- Modify: `viewer/tests/unit/test_workspace_merge.py`
- Modify: `viewer/viewer/services/workspace_merge.py`

- [ ] **Step 1: 复制测试并改 import**

将 `viewer/tests/unit/test_workspace_merge.py` 内容复制到 `tests/tender_insights/unit/test_workspace_merge.py`，import 改为：

```python
from tender_insights.common.workspace_merge import merge_workspaces, validate_merged_workspace
```

- [ ] **Step 2: Viewer re-export**

`viewer/viewer/services/workspace_merge.py` 替换为：

```python
from tender_insights.common.workspace_merge import merge_workspaces, validate_merged_workspace

__all__ = ["merge_workspaces", "validate_merged_workspace"]
```

- [ ] **Step 3: 跑测试**

Run: `.venv/bin/pytest tests/tender_insights/unit/test_workspace_merge.py viewer/tests/unit/test_workspace_merge.py -v`

Expected: PASS

---

### Task 3: prepare_workspaces 集成测试

**Files:**
- Create: `tests/tender_insights/integration/test_prepare_workspaces.py`
- Modify: `src/tender_insights/common/pipeline_runner.py`（多文件 progress 带 file_index）

- [ ] **Step 1: 写双文件 merge 失败测试（无 output_dir）**

```python
def test_prepare_workspaces_merge_requires_output_dir(sample_docx, tmp_path):
    with pytest.raises(WorkspaceResolveError, match="output_dir"):
        prepare_workspaces([sample_docx, sample_docx])
```

- [ ] **Step 2: 写三文件超限测试**

```python
def test_prepare_workspaces_rejects_three_files(sample_docx, tmp_path):
    with pytest.raises(WorkspaceResolveError, match="at most two"):
        prepare_workspaces([sample_docx, sample_docx, sample_docx], output_dir=tmp_path / "out")
```

- [ ] **Step 3: 写双文件 merge 集成测试（FakeLLM 不需要，只测工作区结构）**

使用 `tests/tender_insights/conftest.py` 的 `sample_docx`，调用：

```python
ws = prepare_workspaces([doc1, doc2], output_dir=tmp_path / "merged", overwrite=True)
assert (ws.root / "content.md").exists()
assert "<!-- source:" in ws.content_path.read_text(encoding="utf-8")
validate_merged_workspace(ws.root)
```

- [ ] **Step 4: 增强多文件 on_progress（可选，为 Viewer 准备）**

在 `pipeline_runner.py` 的 pipeline 循环内包装 callback，payload 增加 `file_index`、`file_name`、`file_total`。

- [ ] **Step 5: 跑测试**

Run: `.venv/bin/pytest tests/tender_insights/integration/test_prepare_workspaces.py -v`

---

### Task 4: render 单元测试

**Files:**
- Create: `tests/tender_insights/unit/test_interpret_render.py`
- Modify: `src/tender_insights/interpret/render.py`（仅在测试暴露问题时修）

- [ ] **Step 1: 写最小快照测试**

```python
from tender_insights.interpret.models import InterpretationFile, InterpretationOverview
from tender_insights.interpret.render import render_interpretation_markdown

def test_render_includes_overview_and_sections():
    data = InterpretationFile(
        source_workspace="/tmp/ws",
        overview=InterpretationOverview(
            summary="总览",
            disqualification_summary="废标概要",
            scoring_summary="得分概要",
            bid_risk_summary="风险概要",
            directory_summary="目录概要",
        ),
    )
    md = render_interpretation_markdown(data)
    assert "# 招标解读报告" in md
    assert "## 废标项" in md
    assert "总览" in md
```

- [ ] **Step 2: 写 `render_interpretation_report` API 测试**

```python
def test_render_interpretation_report_writes_file(tmp_path):
    ws_root = tmp_path / "ws"
    ws_root.mkdir()
    (ws_root / "manifest.json").write_text("{}", encoding="utf-8")
    (ws_root / "content.md").write_text("# x\n", encoding="utf-8")
  # 写入最小 interpretation.json ...
    dest = render_interpretation_report(OutputWorkspace.open_existing(ws_root))
    assert dest.exists()
```

- [ ] **Step 3: 跑测试**

Run: `.venv/bin/pytest tests/tender_insights/unit/test_interpret_render.py -v`

---

### Task 5: CLI smoke 测试

**Files:**
- Create: `tests/tender_insights/unit/test_cli.py`

- [ ] **Step 1: 写 help smoke**

```python
from typer.testing import CliRunner
from tender_insights.cli.main import app

def test_cli_help():
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "render" in result.stdout
```

- [ ] **Step 2: 写 render 无 JSON 退出码测试**

```python
def test_render_missing_interpretation_exits_1(tmp_path):
    # 最小工作区，无 interpretation.json
    result = CliRunner().invoke(app, ["render", str(ws_root)])
    assert result.exit_code == 1
```

- [ ] **Step 3: 跑测试**

Run: `.venv/bin/pytest tests/tender_insights/unit/test_cli.py -v`

---

### Task 6: 收敛 Viewer interpret_pipeline

**Files:**
- Modify: `viewer/viewer/services/interpret_pipeline.py`

- [ ] **Step 1: 替换 import**

```python
from tender_insights.api import prepare_workspaces, run_interpret_job
```

删除对 `interpret_workspace`、`extract_templates`、`workspace_merge` 的直接 import。

- [ ] **Step 2: 重构 `run_job` 工作区准备段**

将 pipeline 循环 + copytree + merge 替换为：

```python
def _pipeline_progress(substage: str, payload: dict) -> None:
    nonlocal step
    file_index = int(payload.get("file_index", 1))
    stage = "pipeline_1" if file_index == 1 else "pipeline_2"
    if substage == "merge":
        stage = "merge"
    step += 1
    ...

ws = await asyncio.to_thread(
    prepare_workspaces,
    input_paths,
    output_dir=workspace_dir,
    overwrite=True,
    on_progress=_pipeline_progress,
)
```

- [ ] **Step 3: 重构解读段**

```python
await asyncio.to_thread(
    run_interpret_job,
    ws,
    client=client,
    on_progress=_interpret_progress,
    setup_logging=True,
)
```

- [ ] **Step 4: 跑 Viewer 测试**

Run: `.venv/bin/pytest viewer/tests/api/test_interpret_api.py viewer/tests/unit/test_workspace_merge.py -v`

---

### Task 7: 文档更新

**Files:**
- Modify: `README.md`（tender_insights 快速开始段）

- [ ] **Step 1: 补充双文件 CLI 示例**

```bash
tender-insights interpret bid.docx spec.docx -o ./out --overwrite
tender-insights render ./out -o ./out/interpret_report.md
```

- [ ] **Step 2: 说明 `skip_enrich=True` 与 Viewer 对齐**

---

### Task 8: 全量回归

- [ ] **Step 1: tender_insights 全量**

Run: `.venv/bin/pytest tests/tender_insights/ -v`

- [ ] **Step 2: viewer 相关**

Run: `.venv/bin/pytest viewer/tests/ -v`

Expected: PASS

---

## Spec 覆盖自检

| Spec 要求 | Task |
|-----------|------|
| workspace_merge 下沉 | Task 1–2 |
| 统一 pipeline 参数 | Task 1, 3 |
| API 编排门面 | Task 1, 6 |
| CLI 多文件 + render | Task 4–5 |
| Viewer 收敛 | Task 6 |
| 测试 | Task 2–5, 8 |
| README | Task 7 |

## 执行选项

Plan 已保存。两种执行方式：

1. **Subagent-Driven（推荐）** — 每 Task 派生子 agent，逐步 review
2. **Inline Execution** — 当前会话按 Task 顺序执行，每 2–3 个 Task 设检查点

**请选择执行方式，或确认从 Task 1 继续修复 WIP。**
