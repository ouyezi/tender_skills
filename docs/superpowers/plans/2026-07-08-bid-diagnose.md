# Bid Diagnose Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `tender_insights` 中新增 `bid-diagnose` 子命令，严格依赖 `bid_summary/` 产物，按 segment 顺序对每个分片执行三步 `bid_diagnose_app` 任务，滚动产出累积诊断并落盘到 `bid_diagnose/`。

**Architecture:** 新建 `tender_insights/bid_diagnose/` 子包，镜像 `summary_loop` + `diagnosis` 分层：`loader` 重建 segment 并校验、`tasks.py` 硬编码三步任务、`BidDiagnoseClient`（structuredOutput）、`BidDiagnoseRunner`（segment 外循环 + task 内循环）、`writer` 落盘。共享诊断 prompt 提取到 `common/diagnosis_prompts.py`。

**Tech Stack:** Python 3.11+、Pydantic v2、Typer、stdlib `urllib`、现有 `diagnosis/segment_optimizer`

**设计文档:** `docs/superpowers/specs/2026-07-08-bid-diagnose-design.md`

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `src/tender_insights/common/diagnosis_prompts.py` | 共享 `_DIAGNOSIS_SKILLS` / `_DIAGNOSIS_CHECKLIST` |
| `src/tender_insights/summary_loop/tasks.py` | 改为从 common 导入 prompt（修改） |
| `src/tender_insights/bid_diagnose/__init__.py` | 导出 `run_bid_diagnose` |
| `src/tender_insights/bid_diagnose/models.py` | 状态、输出模型、异常 |
| `src/tender_insights/bid_diagnose/tasks.py` | 3 个 `TaskDefinition` |
| `src/tender_insights/bid_diagnose/loader.py` | 校验 bid_summary + 重建 segments |
| `src/tender_insights/bid_diagnose/client.py` | `BidDiagnoseClient` |
| `src/tender_insights/bid_diagnose/writer.py` | `bid_diagnose/` 落盘 |
| `src/tender_insights/bid_diagnose/runner.py` | `BidDiagnoseRunner`、`run_bid_diagnose` |
| `src/tender_insights/api.py` | 新增 `run_bid_diagnose_job` |
| `src/tender_insights/cli/main.py` | 新增 `bid-diagnose` 子命令 |
| `.env.example` | 新增 `BID_DIAGNOSE_INVOKE_TIMEOUT_S` |
| `tests/tender_insights/unit/test_diagnosis_prompts.py` | 共享 prompt 测试 |
| `tests/tender_insights/unit/test_bid_diagnose_models.py` | models 测试 |
| `tests/tender_insights/unit/test_bid_diagnose_tasks.py` | tasks 测试 |
| `tests/tender_insights/unit/test_bid_diagnose_loader.py` | loader 测试 |
| `tests/tender_insights/unit/test_bid_diagnose_client.py` | client 测试 |
| `tests/tender_insights/unit/test_bid_diagnose_writer.py` | writer 测试 |
| `tests/tender_insights/unit/test_bid_diagnose_runner.py` | runner 测试 |
| `tests/tender_insights/unit/test_cli.py` | 补充 `bid-diagnose --help`（修改） |

---

### Task 1: 提取共享诊断 prompt

**Files:**
- Create: `src/tender_insights/common/diagnosis_prompts.py`
- Modify: `src/tender_insights/summary_loop/tasks.py`
- Test: `tests/tender_insights/unit/test_diagnosis_prompts.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tender_insights/unit/test_diagnosis_prompts.py
from __future__ import annotations

from tender_insights.common.diagnosis_prompts import DIAGNOSIS_CHECKLIST, DIAGNOSIS_SKILLS


def test_diagnosis_skills_non_empty():
    assert "诊断" in DIAGNOSIS_SKILLS
    assert len(DIAGNOSIS_SKILLS) > 50


def test_diagnosis_checklist_contains_table_header():
    assert "| **序号** | **诊断要点** |" in DIAGNOSIS_CHECKLIST
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/tongqianni/xlab/tender_skills && .venv/bin/python -m pytest tests/tender_insights/unit/test_diagnosis_prompts.py -v`

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/tender_insights/common/diagnosis_prompts.py
from __future__ import annotations

DIAGNOSIS_SKILLS = (
    "你擅长对标书进行系统性诊断。诊断时注重废标项以免投标作废，注重得分项以便得到高分，"
    "每个得分点尽量争取足够高分，并严格遵守招标文件要求的格式。"
)

DIAGNOSIS_CHECKLIST = """\
按下列要点生成详细诊断清单（Markdown 表格），并结合招标文件与前序分析结果逐条展开可执行检查项：

| **序号** | **诊断要点** | **依据** |
| ------ | ---------------------------------------------------------- | ------------------ |
| 1 | 投标文件格式核对，是否和招标文件给的格式一致，未任意篡改。 | 招标文件格式 |
| 2 | 投标文件的组成核对，投标文件组成是否无缺漏项，且按顺序编写。 | 招标文件对投标文件的构成要求 |
| 3 | 投标文件资格证明文件核对，招标文件所列资格要求是否都有提供，无缺漏，并核对所提供的资料准确性。 | 招标文件资格要求 |
| 4 | 投标文件对招标文件的响应是否存在偏离，且偏离是否被允许。 | 招标文件采购需求要求及其他要求 |
| 5 | 投标文件的评分应答核对，招标文件评分要求的内容是否都有提供，且提供的内容是否准确，方案等主观分内容是否需要完善补充。 | 招标文件评分要求 |
| 6 | 投标文件的废标项核对 | 招标文件中所列废标、无效投标条款规定 |
| 7 | 投标文件的技术方案是否符合公司的政策要求，是否贴合招标文件采购需求，具有针对性，并可落地执行。 | 招标文件采购需求要求及其他要求 |
| 8 | 投标文件表述内容的准确性，方案或其他部分的描述无前后矛盾或和招标要求的条款不符。 | 招标文件采购需求要求及其他要求 |"""
```

Modify `src/tender_insights/summary_loop/tasks.py` — 删除 `_DIAGNOSIS_SKILLS` / `_DIAGNOSIS_CHECKLIST` 常量，改为：

```python
from tender_insights.common.diagnosis_prompts import DIAGNOSIS_CHECKLIST, DIAGNOSIS_SKILLS
```

并将 `TaskDefinition` step 6 中 `_DIAGNOSIS_SKILLS` → `DIAGNOSIS_SKILLS`，`_DIAGNOSIS_CHECKLIST` → `DIAGNOSIS_CHECKLIST`。

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/tender_insights/unit/test_diagnosis_prompts.py tests/tender_insights/unit/test_summary_loop_models.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tender_insights/common/diagnosis_prompts.py src/tender_insights/summary_loop/tasks.py tests/tender_insights/unit/test_diagnosis_prompts.py
git commit -m "refactor: extract shared diagnosis prompts to common module"
```

---

### Task 2: 数据模型与异常

**Files:**
- Create: `src/tender_insights/bid_diagnose/__init__.py`
- Create: `src/tender_insights/bid_diagnose/models.py`
- Test: `tests/tender_insights/unit/test_bid_diagnose_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tender_insights/unit/test_bid_diagnose_models.py
from __future__ import annotations

import pytest

from tender_insights.bid_diagnose.models import (
    BidDiagnoseInvokeError,
    BidDiagnoseInvokeTimeoutError,
    BidDiagnosePrerequisiteError,
    BidDiagnoseRunResult,
    BidDiagnoseState,
    SegmentDiagnoseState,
    TaskDefinition,
)
from tender_insights.diagnosis.models import DiagnosisSegment


def _segment(index: int = 1) -> DiagnosisSegment:
    return DiagnosisSegment(
        segment_index=index,
        markdown=f"chunk-{index}",
        char_count=len(f"chunk-{index}"),
        source_chunk_ids=[f"c{index}"],
        section_path=["第一章"],
    )


def test_bid_diagnose_state_to_invoke_input_for_import_diagnose():
    task = TaskDefinition(
        step_index=1,
        current_task="import_diagnose",
        task_skills="skills",
        output_requirement="req",
        output_field="import_diagnose",
    )
    state = BidDiagnoseState(
        bid_background="bg",
        analysis_report="report",
        diagnose_before="",
        segments=[_segment()],
    )
    seg_state = SegmentDiagnoseState()
    payload = state.to_invoke_input(_segment(), task, seg_state, sec_in_total="段作用")
    assert payload["bid_background"] == "bg"
    assert payload["analysis_report"] == "report"
    assert payload["diagnose_before"] == ""
    assert payload["sec_in_total"] == "段作用"
    assert payload["current_chunk"] == "chunk-1"
    assert payload["import_diagnose"] == ""
    assert payload["diagnose_result"] == ""
    assert payload["current_task"] == "import_diagnose"
    assert payload["task_skills"] == "skills"
    assert payload["output_requirement"] == "req"


def test_bid_diagnose_state_apply_output_import_diagnose():
    task = TaskDefinition(
        step_index=1,
        current_task="import_diagnose",
        task_skills="s",
        output_requirement="r",
        output_field="import_diagnose",
    )
    state = BidDiagnoseState(bid_background="", analysis_report="r", diagnose_before="", segments=[])
    seg_state = SegmentDiagnoseState()
    state.apply_output(task, {"import_diagnose": "重点"}, seg_state)
    assert seg_state.import_diagnose == "重点"
    assert state.diagnose_before == ""


def test_bid_diagnose_state_apply_output_update_diagnose_rolls_before():
    task = TaskDefinition(
        step_index=3,
        current_task="update_diagnose",
        task_skills="s",
        output_requirement="r",
        output_field="diagnose_result",
    )
    state = BidDiagnoseState(bid_background="", analysis_report="r", diagnose_before="old", segments=[])
    seg_state = SegmentDiagnoseState(segment_diagnose_result="seg")
    state.apply_output(task, {"diagnose_result": "累积新"}, seg_state)
    assert state.diagnose_before == "累积新"


def test_bid_diagnose_run_result_includes_failed_task():
    state = BidDiagnoseState(bid_background="", analysis_report="r", diagnose_before="", segments=[])
    result = BidDiagnoseRunResult(
        status="failed",
        state=state,
        failed_segment=2,
        failed_task="diagnose_result",
        error_type="invoke_error",
        error_message="boom",
    )
    data = result.to_run_state_dict()
    assert data["failed_segment"] == 2
    assert data["failed_task"] == "diagnose_result"


def test_bid_diagnose_invoke_timeout_is_subclass():
    with pytest.raises(BidDiagnoseInvokeError):
        raise BidDiagnoseInvokeTimeoutError("timeout", elapsed_ms=1, configured_timeout_s=600)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/tender_insights/unit/test_bid_diagnose_models.py -v`

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/tender_insights/bid_diagnose/__init__.py
from tender_insights.bid_diagnose.runner import run_bid_diagnose

__all__ = ["run_bid_diagnose"]
```

```python
# src/tender_insights/bid_diagnose/models.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from tender_insights.diagnosis.models import DiagnosisSegment


class BidDiagnoseError(Exception):
    """Base error for bid diagnose."""


class BidDiagnosePrerequisiteError(BidDiagnoseError):
    """Missing or invalid bid_summary/ prerequisites."""


class BidDiagnoseInvokeError(BidDiagnoseError):
    def __init__(self, message: str, *, elapsed_ms: int | None = None) -> None:
        super().__init__(message)
        self.elapsed_ms = elapsed_ms


class BidDiagnoseInvokeTimeoutError(BidDiagnoseInvokeError):
    def __init__(self, message: str, *, elapsed_ms: int, configured_timeout_s: int) -> None:
        super().__init__(message, elapsed_ms=elapsed_ms)
        self.configured_timeout_s = configured_timeout_s


@dataclass(frozen=True)
class TaskDefinition:
    step_index: int
    current_task: str
    task_skills: str
    output_requirement: str
    output_field: str


@dataclass
class SegmentDiagnoseState:
    import_diagnose: str = ""
    segment_diagnose_result: str = ""


@dataclass
class BidDiagnoseState:
    bid_background: str
    analysis_report: str
    diagnose_before: str
    segments: list[DiagnosisSegment]

    def to_invoke_input(
        self,
        segment: DiagnosisSegment,
        task: TaskDefinition,
        segment_state: SegmentDiagnoseState,
        *,
        sec_in_total: str,
    ) -> dict[str, str]:
        diagnose_result = segment_state.segment_diagnose_result
        return {
            "bid_background": self.bid_background,
            "analysis_report": self.analysis_report,
            "diagnose_before": self.diagnose_before,
            "sec_in_total": sec_in_total,
            "current_chunk": segment.markdown,
            "import_diagnose": segment_state.import_diagnose,
            "diagnose_result": diagnose_result,
            "current_task": task.current_task,
            "task_skills": task.task_skills,
            "output_requirement": task.output_requirement,
        }

    def apply_output(
        self,
        task: TaskDefinition,
        structured: dict[str, str],
        segment_state: SegmentDiagnoseState,
    ) -> None:
        value = structured.get(task.output_field, "").strip()
        if not value:
            raise BidDiagnoseInvokeError(f"empty {task.output_field} in structuredOutput")
        if task.current_task == "import_diagnose":
            segment_state.import_diagnose = value
        elif task.current_task == "diagnose_result":
            segment_state.segment_diagnose_result = value
        elif task.current_task == "update_diagnose":
            self.diagnose_before = value


@dataclass(frozen=True)
class TaskStepResult:
    current_task: str
    duration_ms: int
    attempt: int


@dataclass(frozen=True)
class SegmentDiagnoseStepResult:
    segment_index: int
    char_count: int
    source_chunk_ids: list[str]
    sec_in_total: str
    import_diagnose: str
    segment_diagnose_result: str
    steps: list[TaskStepResult]


@dataclass
class BidDiagnoseRunResult:
    status: Literal["completed", "failed", "partial"]
    state: BidDiagnoseState
    completed_segments: list[int] = field(default_factory=list)
    segment_results: list[SegmentDiagnoseStepResult] = field(default_factory=list)
    failed_segment: int | None = None
    failed_task: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    elapsed_ms: int | None = None
    configured_timeout_s: int | None = None

    def to_run_state_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "status": self.status,
            "completed_segments": self.completed_segments,
            "segments": [
                {
                    "segment_index": s.segment_index,
                    "steps": [
                        {
                            "current_task": step.current_task,
                            "duration_ms": step.duration_ms,
                            "attempt": step.attempt,
                        }
                        for step in s.steps
                    ],
                }
                for s in self.segment_results
            ],
        }
        if self.failed_segment is not None:
            data["failed_segment"] = self.failed_segment
        if self.failed_task:
            data["failed_task"] = self.failed_task
        if self.error_type:
            data["error_type"] = self.error_type
        if self.error_message:
            data["message"] = self.error_message
        if self.elapsed_ms is not None:
            data["elapsed_ms"] = self.elapsed_ms
        if self.configured_timeout_s is not None:
            data["configured_timeout_s"] = self.configured_timeout_s
        return data
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/tender_insights/unit/test_bid_diagnose_models.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tender_insights/bid_diagnose/__init__.py src/tender_insights/bid_diagnose/models.py tests/tender_insights/unit/test_bid_diagnose_models.py
git commit -m "feat(bid-diagnose): add models and state rolling logic"
```

---

### Task 3: Task 定义

**Files:**
- Create: `src/tender_insights/bid_diagnose/tasks.py`
- Test: `tests/tender_insights/unit/test_bid_diagnose_tasks.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tender_insights/unit/test_bid_diagnose_tasks.py
from __future__ import annotations

from tender_insights.bid_diagnose.tasks import TASK_DEFINITIONS
from tender_insights.common.diagnosis_prompts import DIAGNOSIS_CHECKLIST, DIAGNOSIS_SKILLS


def test_task_definitions_count_and_order():
    assert len(TASK_DEFINITIONS) == 3
    assert [t.current_task for t in TASK_DEFINITIONS] == [
        "import_diagnose",
        "diagnose_result",
        "update_diagnose",
    ]


def test_import_diagnose_reuses_shared_prompts():
    first = TASK_DEFINITIONS[0]
    assert first.task_skills == DIAGNOSIS_SKILLS
    assert first.output_requirement == DIAGNOSIS_CHECKLIST
    assert first.output_field == "import_diagnose"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/tender_insights/unit/test_bid_diagnose_tasks.py -v`

Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# src/tender_insights/bid_diagnose/tasks.py
from __future__ import annotations

from tender_insights.bid_diagnose.models import TaskDefinition
from tender_insights.common.diagnosis_prompts import DIAGNOSIS_CHECKLIST, DIAGNOSIS_SKILLS

TASK_DEFINITIONS: list[TaskDefinition] = [
    TaskDefinition(
        step_index=1,
        current_task="import_diagnose",
        task_skills=DIAGNOSIS_SKILLS,
        output_requirement=DIAGNOSIS_CHECKLIST,
        output_field="import_diagnose",
    ),
    TaskDefinition(
        step_index=2,
        current_task="diagnose_result",
        task_skills=(
            "你擅长结合诊断重点、累积诊断与分片正文，产出可执行的段级标书诊断结论。"
        ),
        output_requirement=(
            "结合 import_diagnose 诊断重点、diagnose_before 累积诊断、analysis_report 解读概要、"
            "sec_in_total 本分片定位与 current_chunk 正文，输出 Markdown 段级诊断结果。"
        ),
        output_field="diagnose_result",
    ),
    TaskDefinition(
        step_index=3,
        current_task="update_diagnose",
        task_skills="你擅长将段级诊断合并进整体诊断，保持结构清晰、避免重复遗漏。",
        output_requirement=(
            "将本段段级 diagnose_result 合并进 diagnose_before，输出更新后的完整累积诊断 Markdown，"
            "供后续分片继续滚动使用。"
        ),
        output_field="diagnose_result",
    ),
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/tender_insights/unit/test_bid_diagnose_tasks.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tender_insights/bid_diagnose/tasks.py tests/tender_insights/unit/test_bid_diagnose_tasks.py
git commit -m "feat(bid-diagnose): add three-step task definitions"
```

---

### Task 4: Loader

**Files:**
- Create: `src/tender_insights/bid_diagnose/loader.py`
- Test: `tests/tender_insights/unit/test_bid_diagnose_loader.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tender_insights/unit/test_bid_diagnose_loader.py
from __future__ import annotations

import json
from pathlib import Path

import pytest

from doc_chunk.workspace.layout import OutputWorkspace
from tender_insights.bid_diagnose.loader import load_bid_diagnose_inputs
from tender_insights.bid_diagnose.models import BidDiagnosePrerequisiteError
from tender_insights.diagnosis.segment_optimizer import optimize_segments


def _minimal_workspace(tmp_path: Path) -> OutputWorkspace:
    root = tmp_path / "ws"
    root.mkdir()
    (root / "manifest.json").write_text("{}", encoding="utf-8")
    (root / "content.md").write_text("# doc\n", encoding="utf-8")
    (root / "outline.json").write_text(
        json.dumps({"schema_version": "1.0", "strategy": "heading_heuristic", "nodes": []}),
        encoding="utf-8",
    )
    return OutputWorkspace.open_existing(root)


def _write_chunk(ws: OutputWorkspace, markdown: str, chunk_id: str = "chunk-001") -> None:
    chunks_dir = ws.root / "chunks"
    chunks_dir.mkdir(exist_ok=True)
    chunk_path = "0001.json"
    (chunks_dir / chunk_path).write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "chunk_id": chunk_id,
                "title": "第一章",
                "markdown": markdown,
            }
        ),
        encoding="utf-8",
    )
    (chunks_dir / "index.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "chunks": [
                    {
                        "chunk_id": chunk_id,
                        "title": "第一章",
                        "path": chunk_path,
                        "section_path": ["第一章"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def _write_bid_summary(ws: OutputWorkspace, segments_payload: list[dict], *, status: str = "completed") -> None:
    summary_dir = ws.root / "bid_summary"
    summary_dir.mkdir(parents=True)
    (summary_dir / "total_summary.md").write_text("# 概要\n", encoding="utf-8")
    (summary_dir / "run_state.json").write_text(
        json.dumps({"status": status, "completed_segments": [1]}),
        encoding="utf-8",
    )
    (summary_dir / "sec_in_total.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "segments": [
                    {"segment_index": s["segment_index"], "sec_in_total": f"作用{s['segment_index']}"}
                    for s in segments_payload
                ],
            }
        ),
        encoding="utf-8",
    )
    (summary_dir / "segments.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "min_chars": 8000,
                "max_chars": 15000,
                "total_segments": len(segments_payload),
                "segments": segments_payload,
            }
        ),
        encoding="utf-8",
    )


def test_loader_raises_when_bid_summary_missing(tmp_path: Path):
    ws = _minimal_workspace(tmp_path)
    with pytest.raises(BidDiagnosePrerequisiteError, match="bid_summary"):
        load_bid_diagnose_inputs(ws)


def test_loader_raises_when_bid_summary_not_completed(tmp_path: Path):
    ws = _minimal_workspace(tmp_path)
    _write_chunk(ws, "x" * 9000)
    from doc_chunk.models.chunk import ContentChunk

    chunks = [
        ContentChunk.model_validate_json((ws.root / "chunks" / "0001.json").read_text(encoding="utf-8"))
    ]
    segments = optimize_segments(chunks)
    payload = [
        {
            "segment_index": s.segment_index,
            "char_count": s.char_count,
            "source_chunk_ids": s.source_chunk_ids,
            "section_path": s.section_path,
        }
        for s in segments
    ]
    _write_bid_summary(ws, payload, status="failed")
    with pytest.raises(BidDiagnosePrerequisiteError, match="completed"):
        load_bid_diagnose_inputs(ws)


def test_loader_returns_aligned_segments_and_maps(tmp_path: Path):
    ws = _minimal_workspace(tmp_path)
    _write_chunk(ws, "x" * 9000)
    from doc_chunk.models.chunk import ContentChunk

    chunks = [
        ContentChunk.model_validate_json((ws.root / "chunks" / "0001.json").read_text(encoding="utf-8"))
    ]
    segments = optimize_segments(chunks)
    payload = [
        {
            "segment_index": s.segment_index,
            "char_count": s.char_count,
            "source_chunk_ids": s.source_chunk_ids,
            "section_path": s.section_path,
        }
        for s in segments
    ]
    _write_bid_summary(ws, payload)
    analysis_report, loaded_segments, sec_map = load_bid_diagnose_inputs(ws)
    assert analysis_report == "# 概要\n"
    assert len(loaded_segments) == len(segments)
    assert loaded_segments[0].char_count == segments[0].char_count
    assert sec_map[1].startswith("作用")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/tender_insights/unit/test_bid_diagnose_loader.py -v`

Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# src/tender_insights/bid_diagnose/loader.py
from __future__ import annotations

import json

from doc_chunk.models.chunk import ChunkIndex, ContentChunk
from doc_chunk.workspace.layout import OutputWorkspace

from tender_insights.bid_diagnose.models import BidDiagnosePrerequisiteError
from tender_insights.diagnosis.models import DiagnosisSegment
from tender_insights.diagnosis.segment_optimizer import optimize_segments

_BID_SUMMARY_HINT = (
    "缺少 bid_summary/ 或关键文件，请先运行：\n"
    "  tender-insights bid-summary <workspace> --overwrite"
)
_CHUNKS_HINT = (
    "缺少 chunks/，请先运行：\n"
    "  doc-chunk pipeline <file> -o <workspace> --overwrite"
)


def load_bid_diagnose_inputs(
    workspace: OutputWorkspace,
) -> tuple[str, list[DiagnosisSegment], dict[int, str]]:
    summary_dir = workspace.root / "bid_summary"
    required = [
        summary_dir / "segments.json",
        summary_dir / "sec_in_total.json",
        summary_dir / "total_summary.md",
        summary_dir / "run_state.json",
    ]
    if not summary_dir.is_dir() or not all(p.is_file() for p in required):
        raise BidDiagnosePrerequisiteError(_BID_SUMMARY_HINT)

    run_state = json.loads((summary_dir / "run_state.json").read_text(encoding="utf-8"))
    if run_state.get("status") != "completed":
        raise BidDiagnosePrerequisiteError(
            "bid-summary 尚未成功完成（run_state.status != completed），请先重跑 bid-summary"
        )

    analysis_report = (summary_dir / "total_summary.md").read_text(encoding="utf-8")

    sec_payload = json.loads((summary_dir / "sec_in_total.json").read_text(encoding="utf-8"))
    sec_map: dict[int, str] = {}
    for entry in sec_payload.get("segments", []):
        sec_map[int(entry["segment_index"])] = str(entry["sec_in_total"])

    plan = json.loads((summary_dir / "segments.json").read_text(encoding="utf-8"))
    planned_segments = plan.get("segments", [])

    index_path = workspace.chunks_dir / "index.json"
    if not index_path.is_file():
        raise BidDiagnosePrerequisiteError(_CHUNKS_HINT)

    index = ChunkIndex.model_validate_json(index_path.read_text(encoding="utf-8"))
    chunks: list[ContentChunk] = []
    for entry in index.chunks:
        chunk_path = workspace.chunks_dir / entry.path
        if chunk_path.is_file():
            chunks.append(ContentChunk.model_validate(json.loads(chunk_path.read_text(encoding="utf-8"))))
    if not chunks:
        raise BidDiagnosePrerequisiteError(_CHUNKS_HINT)

    rebuilt = optimize_segments(chunks)
    if len(rebuilt) != len(planned_segments):
        raise BidDiagnosePrerequisiteError(
            "分段计划与 bid-summary 不一致（段数不同），请重跑 bid-summary"
        )

    for rebuilt_seg, planned in zip(rebuilt, planned_segments, strict=True):
        if rebuilt_seg.segment_index != planned["segment_index"]:
            raise BidDiagnosePrerequisiteError("分段计划与 bid-summary 不一致，请重跑 bid-summary")
        if rebuilt_seg.char_count != planned["char_count"]:
            raise BidDiagnosePrerequisiteError("分段计划与 bid-summary 不一致，请重跑 bid-summary")
        if rebuilt_seg.source_chunk_ids != planned["source_chunk_ids"]:
            raise BidDiagnosePrerequisiteError("分段计划与 bid-summary 不一致，请重跑 bid-summary")
        if rebuilt_seg.segment_index not in sec_map:
            raise BidDiagnosePrerequisiteError(
                f"sec_in_total.json 缺少 segment_index={rebuilt_seg.segment_index}"
            )

    return analysis_report, rebuilt, sec_map
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/tender_insights/unit/test_bid_diagnose_loader.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tender_insights/bid_diagnose/loader.py tests/tender_insights/unit/test_bid_diagnose_loader.py
git commit -m "feat(bid-diagnose): add loader with bid_summary alignment checks"
```

---

### Task 5: HTTP Client

**Files:**
- Create: `src/tender_insights/bid_diagnose/client.py`
- Test: `tests/tender_insights/unit/test_bid_diagnose_client.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tender_insights/unit/test_bid_diagnose_client.py
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from tender_insights.bid_diagnose.client import (
    APP_NAME,
    BidDiagnoseClient,
    BidDiagnoseInvokeError,
    create_bid_diagnose_client_from_env,
)


def test_client_parses_import_diagnose_output():
    client = BidDiagnoseClient(base_url="http://example.com", api_key="key", timeout_s=30)
    body = json.dumps(
        {
            "status": "completed",
            "structuredOutput": {"import_diagnose": "重点"},
        }
    ).encode()

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return body

    with patch("urllib.request.urlopen", return_value=FakeResp()):
        result = client.invoke({"current_task": "import_diagnose"})

    assert result.output == {"import_diagnose": "重点"}
    assert result.duration_ms >= 0


def test_client_rejects_empty_output_field():
    client = BidDiagnoseClient(base_url="http://example.com", api_key="key", timeout_s=30)
    body = json.dumps({"status": "completed", "structuredOutput": {"import_diagnose": "  "}}).encode()

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return body

    with patch("urllib.request.urlopen", return_value=FakeResp()):
        with pytest.raises(BidDiagnoseInvokeError, match="empty import_diagnose"):
            client.invoke({"current_task": "import_diagnose"})


def test_create_client_requires_api_key(monkeypatch):
    monkeypatch.delenv("AGENT_PLATFORM_API_KEY", raising=False)
    with pytest.raises(BidDiagnoseInvokeError, match="API_KEY"):
        create_bid_diagnose_client_from_env()


def test_app_name():
    assert APP_NAME == "bid_diagnose_app"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/tender_insights/unit/test_bid_diagnose_client.py -v`

Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

Mirror `diagnosis/client.py` with these changes:
- `APP_NAME = "bid_diagnose_app"`
- `_OUTPUT_FIELD_BY_TASK = {"import_diagnose": "import_diagnose", "diagnose_result": "diagnose_result", "update_diagnose": "diagnose_result"}`
- `invoke()` reads `current_task` from input, validates corresponding field in structuredOutput
- `create_bid_diagnose_client_from_env()` reads `BID_DIAGNOSE_INVOKE_TIMEOUT_S` default 600

```python
# src/tender_insights/bid_diagnose/client.py — key parts
_OUTPUT_FIELD_BY_TASK = {
    "import_diagnose": "import_diagnose",
    "diagnose_result": "diagnose_result",
    "update_diagnose": "diagnose_result",
}

def invoke(self, input: dict[str, Any]) -> InvokeStructuredResult:
    current_task = str(input.get("current_task") or "")
    output_field = _OUTPUT_FIELD_BY_TASK.get(current_task)
    if not output_field:
        raise BidDiagnoseInvokeError(f"unknown current_task: {current_task}")
    # ... same HTTP logic as DiagnosisClient ...
    value = str(structured.get(output_field) or "").strip()
    if not value:
        raise BidDiagnoseInvokeError(f"empty {output_field} in structuredOutput")
    return InvokeStructuredResult(output={output_field: value}, duration_ms=duration_ms, raw_response=payload)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/tender_insights/unit/test_bid_diagnose_client.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tender_insights/bid_diagnose/client.py tests/tender_insights/unit/test_bid_diagnose_client.py
git commit -m "feat(bid-diagnose): add HTTP client for bid_diagnose_app"
```

---

### Task 6: Writer

**Files:**
- Create: `src/tender_insights/bid_diagnose/writer.py`
- Test: `tests/tender_insights/unit/test_bid_diagnose_writer.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tender_insights/unit/test_bid_diagnose_writer.py
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tender_insights.bid_diagnose.models import (
    BidDiagnoseRunResult,
    BidDiagnoseState,
    SegmentDiagnoseStepResult,
    TaskStepResult,
)
from tender_insights.bid_diagnose.writer import (
    init_bid_diagnose_dir,
    write_diagnose_result,
    write_run_state,
    write_segment_result,
)


def test_init_bid_diagnose_dir_creates_structure(tmp_path: Path):
    root = tmp_path / "ws"
    root.mkdir()
    diag_dir = init_bid_diagnose_dir(root, overwrite=False)
    assert diag_dir == root / "bid_diagnose"
    assert (diag_dir / "segments").is_dir()


def test_init_raises_when_exists_without_overwrite(tmp_path: Path):
    root = tmp_path / "ws"
    (root / "bid_diagnose").mkdir(parents=True)
    with pytest.raises(FileExistsError):
        init_bid_diagnose_dir(root, overwrite=False)


def test_write_segment_result_payload(tmp_path: Path):
    diag_dir = init_bid_diagnose_dir(tmp_path / "ws", overwrite=True)
    step = SegmentDiagnoseStepResult(
        segment_index=1,
        char_count=100,
        source_chunk_ids=["c1"],
        sec_in_total="作用",
        import_diagnose="重点",
        segment_diagnose_result="段结果",
        steps=[TaskStepResult("import_diagnose", 10, 1)],
    )
    path = write_segment_result(diag_dir, step)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["segment_index"] == 1
    assert payload["import_diagnose"] == "重点"
    assert payload["segment_diagnose_result"] == "段结果"


def test_write_diagnose_result_md(tmp_path: Path):
    diag_dir = init_bid_diagnose_dir(tmp_path / "ws2", overwrite=True)
    path = write_diagnose_result(diag_dir, "# 累积\n")
    assert path.read_text(encoding="utf-8") == "# 累积\n"


def test_write_run_state(tmp_path: Path):
    diag_dir = init_bid_diagnose_dir(tmp_path / "ws3", overwrite=True)
    state = BidDiagnoseState(bid_background="", analysis_report="r", diagnose_before="", segments=[])
    result = BidDiagnoseRunResult(status="completed", state=state, completed_segments=[1])
    path = write_run_state(diag_dir, result)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["status"] == "completed"
    assert data["completed_segments"] == [1]
```

- [ ] **Step 2–4:** Implement `writer.py` mirroring `diagnosis/writer.py` paths under `bid_diagnose/`; run tests until PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tender_insights/bid_diagnose/writer.py tests/tender_insights/unit/test_bid_diagnose_writer.py
git commit -m "feat(bid-diagnose): add writer for bid_diagnose output directory"
```

---

### Task 7: Runner

**Files:**
- Create: `src/tender_insights/bid_diagnose/runner.py`
- Test: `tests/tender_insights/unit/test_bid_diagnose_runner.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tender_insights/unit/test_bid_diagnose_runner.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from tender_insights.bid_diagnose.client import InvokeStructuredResult
from tender_insights.bid_diagnose.models import (
    BidDiagnoseInvokeError,
    BidDiagnoseInvokeTimeoutError,
    BidDiagnoseState,
)
from tender_insights.bid_diagnose.runner import BidDiagnoseRunner
from tender_insights.diagnosis.models import DiagnosisSegment


@dataclass
class FakeBidDiagnoseClient:
    outcomes: list[dict[str, str] | Exception] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)
    _index: int = 0

    def invoke(self, input: dict[str, Any]) -> InvokeStructuredResult:
        self.calls.append(dict(input))
        outcome = self.outcomes[self._index]
        self._index += 1
        if isinstance(outcome, Exception):
            raise outcome
        return InvokeStructuredResult(output=outcome, duration_ms=10, raw_response={"status": "completed"})


def _state_two_segments() -> tuple[BidDiagnoseState, dict[int, str]]:
    segments = [
        DiagnosisSegment(1, "seg1", 4, ["c1"], []),
        DiagnosisSegment(2, "seg2", 4, ["c2"], []),
    ]
    state = BidDiagnoseState(
        bid_background="bg",
        analysis_report="report",
        diagnose_before="",
        segments=segments,
    )
    return state, {1: "s1", 2: "s2"}


def test_runner_executes_three_tasks_per_segment_and_rolls_diagnose_before():
    client = FakeBidDiagnoseClient(
        outcomes=[
            {"import_diagnose": "i1"},
            {"diagnose_result": "d1"},
            {"diagnose_result": "acc1"},
            {"import_diagnose": "i2"},
            {"diagnose_result": "d2"},
            {"diagnose_result": "acc2"},
        ]
    )
    state, sec_map = _state_two_segments()
    runner = BidDiagnoseRunner(client=client)
    result = runner.run(state, sec_map)

    assert result.status == "completed"
    assert result.state.diagnose_before == "acc2"
    assert len(client.calls) == 6
    assert client.calls[0]["current_task"] == "import_diagnose"
    assert client.calls[1]["import_diagnose"] == "i1"
    assert client.calls[2]["diagnose_result"] == "d1"
    assert client.calls[3]["diagnose_before"] == "acc1"
    assert client.calls[3]["current_task"] == "import_diagnose"


def test_runner_does_not_retry_on_timeout():
    client = FakeBidDiagnoseClient(outcomes=[BidDiagnoseInvokeTimeoutError("t", elapsed_ms=1, configured_timeout_s=600)])
    state, sec_map = _state_two_segments()
    runner = BidDiagnoseRunner(client=client)
    result = runner.run(state, sec_map)
    assert result.status == "failed"
    assert result.failed_segment == 1
    assert result.failed_task == "import_diagnose"
    assert len(client.calls) == 1


def test_runner_retries_once_on_invoke_error():
    client = FakeBidDiagnoseClient(
        outcomes=[
            BidDiagnoseInvokeError("boom"),
            {"import_diagnose": "i1"},
            {"diagnose_result": "d1"},
            {"diagnose_result": "acc1"},
            {"import_diagnose": "i2"},
            {"diagnose_result": "d2"},
            {"diagnose_result": "acc2"},
        ]
    )
    state, sec_map = _state_two_segments()
    runner = BidDiagnoseRunner(client=client)
    result = runner.run(state, sec_map)
    assert result.status == "completed"
    assert result.segment_results[0].steps[0].attempt == 2
```

- [ ] **Step 2–4:** Implement `BidDiagnoseRunner` with `MAX_RETRIES = 1`, nested loop over segments × `TASK_DEFINITIONS`, `_failed_result` sets `failed_segment` + `failed_task`. Run tests until PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tender_insights/bid_diagnose/runner.py tests/tender_insights/unit/test_bid_diagnose_runner.py
git commit -m "feat(bid-diagnose): add runner with per-segment three-step loop"
```

---

### Task 8: 编排入口 `run_bid_diagnose`

**Files:**
- Modify: `src/tender_insights/bid_diagnose/runner.py`（追加 `run_bid_diagnose` 函数）
- Test: extend `tests/tender_insights/unit/test_bid_diagnose_runner.py` 或新增集成 mock 测试

- [ ] **Step 1: Implement `run_bid_diagnose`**

```python
def run_bid_diagnose(
    workspace: OutputWorkspace,
    *,
    bid_background: str = "",
    client: BidDiagnoseClient | None = None,
    on_progress: Callable[[str, dict], None] | None = None,
    overwrite: bool = False,
    timeout_s: int | None = None,
) -> BidDiagnoseRunResult:
    analysis_report, segments, sec_map = load_bid_diagnose_inputs(workspace)
    state = BidDiagnoseState(
        bid_background=bid_background,
        analysis_report=analysis_report,
        diagnose_before="",
        segments=segments,
    )
    resolved_client = client or create_bid_diagnose_client_from_env()
    if timeout_s is not None and client is None:
        resolved_client = BidDiagnoseClient(
            base_url=resolved_client.base_url,
            api_key=resolved_client.api_key,
            timeout_s=timeout_s,
        )
    diag_dir = init_bid_diagnose_dir(workspace.root, overwrite=overwrite)
    runner = BidDiagnoseRunner(client=resolved_client, on_progress=on_progress)
    result = runner.run(state, sec_map)
    for segment_result in result.segment_results:
        write_segment_result(diag_dir, segment_result)
    write_run_state(diag_dir, result)
    if state.diagnose_before:
        write_diagnose_result(diag_dir, state.diagnose_before)
    return result
```

- [ ] **Step 2: Run full unit test suite for bid_diagnose**

Run: `.venv/bin/python -m pytest tests/tender_insights/unit/test_bid_diagnose_*.py -v`

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add src/tender_insights/bid_diagnose/runner.py
git commit -m "feat(bid-diagnose): wire run_bid_diagnose orchestration"
```

---

### Task 9: API、CLI 与环境变量

**Files:**
- Modify: `src/tender_insights/api.py`
- Modify: `src/tender_insights/cli/main.py`
- Modify: `.env.example`
- Modify: `tests/tender_insights/unit/test_cli.py`

- [ ] **Step 1: Add API facade**

```python
# src/tender_insights/api.py
def run_bid_diagnose_job(
    workspace: OutputWorkspace,
    *,
    bid_background: str = "",
    on_progress: Callable[[str, dict], None] | None = None,
    overwrite: bool = False,
    timeout_s: int | None = None,
):
    from tender_insights.bid_diagnose.runner import run_bid_diagnose

    return run_bid_diagnose(
        workspace,
        bid_background=bid_background,
        on_progress=on_progress,
        overwrite=overwrite,
        timeout_s=timeout_s,
    )
```

- [ ] **Step 2: Add CLI command**

```python
# src/tender_insights/cli/main.py
from tender_insights.api import run_bid_diagnose_job
from tender_insights.bid_diagnose.models import BidDiagnosePrerequisiteError

@app.command("bid-diagnose", help="对标书分片滚动诊断（需 bid_summary/ 已完成）")
def bid_diagnose_cmd(
    path: Path = typer.Argument(..., help="已有工作区目录（须含 bid_summary/ 与 chunks/）"),
    background: str = typer.Option("", "--background", help="bid_background，可为空"),
    overwrite: bool = typer.Option(False, "--overwrite"),
    timeout: int | None = typer.Option(None, "--timeout", help="单次 invoke 超时秒数，默认 600"),
) -> None:
    ws = _resolve_workspace(path, None, overwrite=False)
    try:
        result = run_bid_diagnose_job(
            ws, bid_background=background, overwrite=overwrite, timeout_s=timeout
        )
    except BidDiagnosePrerequisiteError as exc:
        raise typer.BadParameter(str(exc)) from exc

    diag_dir = ws.root / "bid_diagnose"
    if result.status != "completed":
        typer.echo(
            f"标书诊断失败，停在分段 {result.failed_segment} / 任务 {result.failed_task}: {result.error_message}",
            err=True,
        )
        typer.echo(f"Partial results written to {diag_dir}")
        raise typer.Exit(code=1)
    typer.echo(f"Wrote {diag_dir / 'diagnose_result.md'}")
    typer.echo(f"Wrote {diag_dir / 'run_state.json'}")
```

- [ ] **Step 3: Update `.env.example`**

```
BID_DIAGNOSE_INVOKE_TIMEOUT_S=600
```

- [ ] **Step 4: CLI test**

```python
def test_cli_bid_diagnose_help() -> None:
    result = CliRunner().invoke(app, ["bid-diagnose", "--help"])
    assert result.exit_code == 0
    assert "bid-diagnose" in result.output
    assert "--background" in result.output
```

Run: `.venv/bin/python -m pytest tests/tender_insights/unit/test_cli.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/tender_insights/api.py src/tender_insights/cli/main.py .env.example tests/tender_insights/unit/test_cli.py
git commit -m "feat(bid-diagnose): expose CLI and API entry points"
```

---

### Task 10: 全量回归

- [ ] **Step 1: Run bid_diagnose unit tests**

Run: `.venv/bin/python -m pytest tests/tender_insights/unit/test_bid_diagnose_*.py tests/tender_insights/unit/test_diagnosis_prompts.py -v`

Expected: all PASS

- [ ] **Step 2: Run related regression**

Run: `.venv/bin/python -m pytest tests/tender_insights/unit/test_summary_loop_models.py tests/tender_insights/unit/test_diagnosis_runner.py tests/tender_insights/unit/test_cli.py -v`

Expected: all PASS

- [ ] **Step 3: Final commit if any fixups**

```bash
git status
# commit any remaining fixups
```

---

## Spec Coverage Checklist

| Spec 要求 | 对应 Task |
|-----------|-----------|
| 前置 bid_summary 校验 | Task 4 |
| segments 对齐校验 | Task 4 |
| 三步 task 顺序 invoke | Task 3, 7 |
| diagnose_before 滚动 | Task 2, 7 |
| bid_diagnose_app client | Task 5 |
| 落盘 bid_diagnose/ | Task 6 |
| CLI bid-diagnose + --background | Task 9 |
| 共享 diagnosis prompt | Task 1 |
| 超时/重试策略 | Task 5, 7 |
| BID_DIAGNOSE_INVOKE_TIMEOUT_S | Task 5, 9 |
