# Tender Summary Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `tender_insights` 中新增 `loop` 子命令，顺序调用平台 `tender_summary_app` 完成标书五步法解读，支持 600s 超时、超时立即中止、非超时错误重试 1 次，并将结果落盘到 `summary_loop/`。

**Architecture:** 新建 `tender_insights/summary_loop/` 子包：`SummaryLoopClient`（专用 HTTP，API Key + 600s）、`SummaryLoopRunner`（状态机 + 重试）、`tasks.py`（5 步硬编码）、`writer.py`（落盘）。CLI 复用 `prepare_workspaces` + `prepare_interpret_source` 准备 `tender_info`。

**Tech Stack:** Python 3.11+、Pydantic v2、Typer、stdlib `urllib`、现有 `doc_chunk` / `tender_insights.common`

**设计文档:** `docs/superpowers/specs/2026-07-07-tender-summary-loop-design.md`

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `src/tender_insights/summary_loop/__init__.py` | 导出 `run_summary_loop` |
| `src/tender_insights/summary_loop/models.py` | `TaskDefinition`、`LoopState`、`StepResult`、`LoopRunResult`、异常类 |
| `src/tender_insights/summary_loop/tasks.py` | `TASK_DEFINITIONS`（5 步常量） |
| `src/tender_insights/summary_loop/client.py` | `SummaryLoopClient`、`create_summary_loop_client_from_env` |
| `src/tender_insights/summary_loop/writer.py` | `init_loop_dir`、`write_step`、`write_run_state`、`write_results` |
| `src/tender_insights/summary_loop/runner.py` | `SummaryLoopRunner`、`run_summary_loop` |
| `src/tender_insights/api.py` | 新增 `run_summary_loop_job` 薄封装 |
| `src/tender_insights/cli/main.py` | 新增 `loop` 子命令 |
| `.env.example` | 新增 `AGENT_PLATFORM_API_KEY`、`SUMMARY_LOOP_INVOKE_TIMEOUT_S` |
| `tests/tender_insights/unit/test_summary_loop_models.py` | models 单元测试 |
| `tests/tender_insights/unit/test_summary_loop_tasks.py` | tasks 单元测试 |
| `tests/tender_insights/unit/test_summary_loop_client.py` | client HTTP mock 测试 |
| `tests/tender_insights/unit/test_summary_loop_writer.py` | writer 落盘测试 |
| `tests/tender_insights/unit/test_summary_loop_runner.py` | runner 状态传递、重试、超时测试 |
| `tests/tender_insights/unit/test_cli.py` | 补充 `loop --help` 测试（修改） |

---

### Task 1: 数据模型与异常

**Files:**
- Create: `src/tender_insights/summary_loop/__init__.py`
- Create: `src/tender_insights/summary_loop/models.py`
- Test: `tests/tender_insights/unit/test_summary_loop_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tender_insights/unit/test_summary_loop_models.py
from __future__ import annotations

import pytest

from tender_insights.summary_loop.models import (
    LoopRunResult,
    LoopState,
    SummaryLoopError,
    SummaryLoopInvokeError,
    SummaryLoopInvokeTimeoutError,
    TaskDefinition,
)


def test_loop_state_to_invoke_input_includes_task_fields():
    state = LoopState(tender_info="正文", task_background="背景")
    task = TaskDefinition(
        step_index=1,
        current_task="get_tender_summary",
        task_skills="概要提取",
        output_requirement="输出 Markdown 概要",
        output_field="tender_summary",
        step_filename="01_tender_summary.txt",
    )
    payload = state.to_invoke_input(task)
    assert payload["tender_info"] == "正文"
    assert payload["task_background"] == "背景"
    assert payload["current_task"] == "get_tender_summary"
    assert payload["tender_summary"] == ""


def test_loop_state_apply_output_updates_field():
    state = LoopState(tender_info="x", task_background="y")
    task = TaskDefinition(
        step_index=1,
        current_task="get_tender_summary",
        task_skills="s",
        output_requirement="r",
        output_field="tender_summary",
        step_filename="01_tender_summary.txt",
    )
    state.apply_output(task, "概要内容")
    assert state.tender_summary == "概要内容"


def test_summary_loop_invoke_timeout_error_is_subclass():
    with pytest.raises(SummaryLoopInvokeError):
        raise SummaryLoopInvokeTimeoutError("timeout", elapsed_ms=180000, configured_timeout_s=600)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/tongqianni/xlab/tender_skills && .venv/bin/python -m pytest tests/tender_insights/unit/test_summary_loop_models.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'tender_insights.summary_loop'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/tender_insights/summary_loop/models.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


class SummaryLoopError(Exception):
  """Base error for summary_loop."""


class SummaryLoopInvokeError(SummaryLoopError):
    def __init__(self, message: str, *, elapsed_ms: int | None = None) -> None:
        super().__init__(message)
        self.elapsed_ms = elapsed_ms


class SummaryLoopInvokeTimeoutError(SummaryLoopInvokeError):
    def __init__(self, message: str, *, elapsed_ms: int, configured_timeout_s: int) -> None:
        super().__init__(message, elapsed_ms=elapsed_ms)
        self.configured_timeout_s = configured_timeout_s


@dataclass(frozen=True)
class TaskDefinition:
    step_index: int
    current_task: str
    task_skills: str
    output_requirement: str
    output_field: str | None
    step_filename: str


@dataclass
class LoopState:
    tender_info: str
    task_background: str
    tender_summary: str = ""
    score_points: str = ""
    disqualification_items: str = ""
    tender_responds: str = ""
    report: str = ""

    def to_invoke_input(self, task: TaskDefinition) -> dict[str, str]:
        return {
            "tender_info": self.tender_info,
            "task_background": self.task_background,
            "tender_summary": self.tender_summary,
            "score_points": self.score_points,
            "disqualification_items": self.disqualification_items,
            "tender_responds": self.tender_responds,
            "current_task": task.current_task,
            "task_skills": task.task_skills,
            "output_requirement": task.output_requirement,
        }

    def apply_output(self, task: TaskDefinition, output: str) -> None:
        if task.output_field is None:
            self.report = output
            return
        setattr(self, task.output_field, output)


@dataclass(frozen=True)
class StepResult:
    current_task: str
    output: str
    duration_ms: int
    attempt: int


@dataclass
class LoopRunResult:
    status: Literal["completed", "failed", "partial"]
    state: LoopState
    completed_steps: list[str] = field(default_factory=list)
    step_results: list[StepResult] = field(default_factory=list)
    failed_step: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    elapsed_ms: int | None = None
    configured_timeout_s: int | None = None

    def to_run_state_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "status": self.status,
            "completed_steps": self.completed_steps,
            "steps": [
                {
                    "current_task": s.current_task,
                    "duration_ms": s.duration_ms,
                    "attempt": s.attempt,
                }
                for s in self.step_results
            ],
        }
        if self.failed_step:
            data["failed_step"] = self.failed_step
        if self.error_type:
            data["error_type"] = self.error_type
        if self.error_message:
            data["message"] = self.error_message
        if self.elapsed_ms is not None:
            data["elapsed_ms"] = self.elapsed_ms
        if self.configured_timeout_s is not None:
            data["configured_timeout_s"] = self.configured_timeout_s
        return data

    def to_results_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "task_background": self.state.task_background,
            "tender_summary": self.state.tender_summary,
            "score_points": self.state.score_points,
            "disqualification_items": self.state.disqualification_items,
            "tender_responds": self.state.tender_responds,
            "report": self.state.report,
            "completed_steps": self.completed_steps,
            "status": self.status,
        }
```

```python
# src/tender_insights/summary_loop/__init__.py
# Task 5 完成后在此导出 run_summary_loop
__all__: list[str] = []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/tender_insights/unit/test_summary_loop_models.py -v`

Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/tender_insights/summary_loop/__init__.py \
        src/tender_insights/summary_loop/models.py \
        tests/tender_insights/unit/test_summary_loop_models.py
git commit -m "feat(summary-loop): add loop state and result models"
```

---

### Task 2: 硬编码任务定义

**Files:**
- Create: `src/tender_insights/summary_loop/tasks.py`
- Test: `tests/tender_insights/unit/test_summary_loop_tasks.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tender_insights/unit/test_summary_loop_tasks.py
from __future__ import annotations

from tender_insights.summary_loop.tasks import TASK_DEFINITIONS


def test_task_definitions_has_five_steps_in_order():
    assert len(TASK_DEFINITIONS) == 5
    assert [t.current_task for t in TASK_DEFINITIONS] == [
        "get_tender_summary",
        "get_score_points",
        "get_disqualification_items",
        "get_tender_responds",
        "generate_report",
    ]


def test_generate_report_has_no_output_field():
    report_task = TASK_DEFINITIONS[-1]
    assert report_task.current_task == "generate_report"
    assert report_task.output_field is None
    assert report_task.step_filename == "05_report.md"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/tender_insights/unit/test_summary_loop_tasks.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'tender_insights.summary_loop.tasks'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/tender_insights/summary_loop/tasks.py
from __future__ import annotations

from tender_insights.summary_loop.models import TaskDefinition

TASK_DEFINITIONS: list[TaskDefinition] = [
    TaskDefinition(
        step_index=1,
        current_task="get_tender_summary",
        task_skills="你擅长阅读政府采购/招投标文件，能准确提炼项目背景、采购范围、时间节点与关键要求。",
        output_requirement="输出结构化 Markdown 标书概要，包含：项目名称、采购人、预算/限价（如有）、时间节点、采购内容摘要。",
        output_field="tender_summary",
        step_filename="01_tender_summary.txt",
    ),
    TaskDefinition(
        step_index=2,
        current_task="get_score_points",
        task_skills="你擅长从招标文件评审办法/评分标准章节提取得分项与分值构成。",
        output_requirement="输出 Markdown 列表，每条得分项包含：名称、分值、评分要点、证明材料要求（如有）。",
        output_field="score_points",
        step_filename="02_score_points.txt",
    ),
    TaskDefinition(
        step_index=3,
        current_task="get_disqualification_items",
        task_skills="你擅长识别招标文件中的废标条款、否决投标情形与实质性要求。",
        output_requirement="输出 Markdown 列表，每条废标项包含：条款来源（章节/条款号）、废标情形、投标人注意事项。",
        output_field="disqualification_items",
        step_filename="03_disqualification_items.txt",
    ),
    TaskDefinition(
        step_index=4,
        current_task="get_tender_responds",
        task_skills="你擅长梳理投标文件格式要求、响应性条款与必须提交的证明材料。",
        output_requirement="输出 Markdown，分节列出：投标文件组成、格式要求、必须响应的条款、证明材料清单。",
        output_field="tender_responds",
        step_filename="04_tender_responds.txt",
    ),
    TaskDefinition(
        step_index=5,
        current_task="generate_report",
        task_skills="你擅长将招标解读结果整合为面向投标团队的完整解读报告。",
        output_requirement="综合 tender_summary、score_points、disqualification_items、tender_responds，输出完整 Markdown 解读报告，含执行摘要、得分策略建议、废标风险提示、投标准备清单。",
        output_field=None,
        step_filename="05_report.md",
    ),
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/tender_insights/unit/test_summary_loop_tasks.py -v`

Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/tender_insights/summary_loop/tasks.py \
        tests/tender_insights/unit/test_summary_loop_tasks.py
git commit -m "feat(summary-loop): add hardcoded five-step task definitions"
```

---

### Task 3: SummaryLoopClient（HTTP + API Key + 600s 超时）

**Files:**
- Create: `src/tender_insights/summary_loop/client.py`
- Test: `tests/tender_insights/unit/test_summary_loop_client.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tender_insights/unit/test_summary_loop_client.py
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from tender_insights.summary_loop.client import (
    APP_NAME,
    SummaryLoopClient,
    create_summary_loop_client_from_env,
)
from tender_insights.summary_loop.models import (
    SummaryLoopInvokeError,
    SummaryLoopInvokeTimeoutError,
)


def test_invoke_returns_text_output():
    fake_resp = MagicMock()
    fake_resp.read.return_value = json.dumps(
        {"status": "completed", "output": "概要文本", "structuredOutput": None}
    ).encode("utf-8")
    fake_resp.__enter__ = lambda s: s
    fake_resp.__exit__ = MagicMock(return_value=False)

    captured: dict = {}

    def _urlopen(req, timeout):
        captured["timeout"] = timeout
        captured["headers"] = dict(req.header_items())
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return fake_resp

    client = SummaryLoopClient(
        base_url="http://localhost:8000",
        api_key="test-key",
        timeout_s=600,
    )

    with patch("urllib.request.urlopen", side_effect=_urlopen):
        result = client.invoke({"tender_info": "x", "current_task": "get_tender_summary"})

    assert result.output == "概要文本"
    assert captured["timeout"] == 600
    assert captured["body"]["appName"] == APP_NAME
    assert captured["headers"]["X-api-key"] == "test-key"


def test_invoke_raises_on_non_completed_status():
    fake_resp = MagicMock()
    fake_resp.read.return_value = json.dumps({"status": "failed"}).encode("utf-8")
    fake_resp.__enter__ = lambda s: s
    fake_resp.__exit__ = MagicMock(return_value=False)

    client = SummaryLoopClient(base_url="http://localhost:8000", api_key="k", timeout_s=600)
    with patch("urllib.request.urlopen", return_value=fake_resp):
        with pytest.raises(SummaryLoopInvokeError, match="not completed"):
            client.invoke({})


def test_invoke_timeout_maps_to_timeout_error():
    import socket
    import urllib.error

    client = SummaryLoopClient(base_url="http://localhost:8000", api_key="k", timeout_s=600)
    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.URLError(socket.timeout("timed out")),
    ):
        with pytest.raises(SummaryLoopInvokeTimeoutError) as exc_info:
            client.invoke({})
    assert exc_info.value.configured_timeout_s == 600


def test_create_client_from_env(monkeypatch):
    monkeypatch.setenv("AGENT_PLATFORM_BASE_URL", "http://127.0.0.1:8000")
    monkeypatch.setenv("AGENT_PLATFORM_API_KEY", "env-key")
    monkeypatch.setenv("SUMMARY_LOOP_INVOKE_TIMEOUT_S", "300")
    client = create_summary_loop_client_from_env()
    assert client.timeout_s == 300
    assert client.api_key == "env-key"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/tender_insights/unit/test_summary_loop_client.py -v`

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/tender_insights/summary_loop/client.py
from __future__ import annotations

import json
import os
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from tender_insights.summary_loop.models import SummaryLoopInvokeError, SummaryLoopInvokeTimeoutError

APP_NAME = "tender_summary_app"


@dataclass(frozen=True)
class InvokeTextResult:
    output: str
    duration_ms: int
    raw_response: dict[str, Any]


class SummaryLoopClient:
    def __init__(self, *, base_url: str, api_key: str, timeout_s: int = 600) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_s = timeout_s

    def invoke(self, input: dict[str, Any]) -> InvokeTextResult:
        url = f"{self.base_url}/v1/apps/invoke"
        body = json.dumps({"appName": APP_NAME, "input": input}).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": self.api_key,
        }
        req = urllib.request.Request(url, data=body, method="POST", headers=headers)
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.URLError as exc:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                raise SummaryLoopInvokeTimeoutError(
                    "invoke timed out before configured limit — check client/server timeout alignment",
                    elapsed_ms=elapsed_ms,
                    configured_timeout_s=self.timeout_s,
                ) from exc
            raise SummaryLoopInvokeError(str(exc), elapsed_ms=elapsed_ms) from exc
        except TimeoutError as exc:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            raise SummaryLoopInvokeTimeoutError(
                "invoke timed out before configured limit — check client/server timeout alignment",
                elapsed_ms=elapsed_ms,
                configured_timeout_s=self.timeout_s,
            ) from exc

        duration_ms = int((time.perf_counter() - started) * 1000)
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            raise SummaryLoopInvokeError(f"invalid JSON response: {exc}", elapsed_ms=duration_ms) from exc

        if not isinstance(payload, dict):
            raise SummaryLoopInvokeError("platform response must be JSON object", elapsed_ms=duration_ms)

        status = str(payload.get("status") or "")
        if status != "completed":
            raise SummaryLoopInvokeError(
                f"invoke not completed for {APP_NAME}: {payload}",
                elapsed_ms=duration_ms,
            )

        output = payload.get("output")
        if not isinstance(output, str) or not output.strip():
            raise SummaryLoopInvokeError("missing non-empty text output", elapsed_ms=duration_ms)

        return InvokeTextResult(output=output, duration_ms=duration_ms, raw_response=payload)


def create_summary_loop_client_from_env() -> SummaryLoopClient:
    base_url = os.environ.get("AGENT_PLATFORM_BASE_URL", "http://localhost:8000")
    api_key = os.environ.get("AGENT_PLATFORM_API_KEY", "").strip()
    if not api_key:
        raise SummaryLoopInvokeError("AGENT_PLATFORM_API_KEY is required for summary loop")
    timeout_raw = os.environ.get("SUMMARY_LOOP_INVOKE_TIMEOUT_S", "600").strip()
    timeout_s = int(timeout_raw)
    return SummaryLoopClient(base_url=base_url, api_key=api_key, timeout_s=timeout_s)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/tender_insights/unit/test_summary_loop_client.py -v`

Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/tender_insights/summary_loop/client.py \
        tests/tender_insights/unit/test_summary_loop_client.py
git commit -m "feat(summary-loop): add platform client with API key and 600s timeout"
```

---

### Task 4: Writer 落盘

**Files:**
- Create: `src/tender_insights/summary_loop/writer.py`
- Test: `tests/tender_insights/unit/test_summary_loop_writer.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tender_insights/unit/test_summary_loop_writer.py
from __future__ import annotations

import json
from pathlib import Path

from tender_insights.summary_loop.models import LoopRunResult, LoopState, StepResult
from tender_insights.summary_loop.writer import (
    init_loop_dir,
    write_results,
    write_run_state,
    write_step,
)


def test_init_loop_dir_creates_structure(tmp_path: Path):
    loop_dir = init_loop_dir(tmp_path, overwrite=False)
    assert loop_dir == tmp_path / "summary_loop"
    assert (loop_dir / "steps").is_dir()


def test_write_step_and_results(tmp_path: Path):
    loop_dir = init_loop_dir(tmp_path, overwrite=True)
    write_step(loop_dir, "01_tender_summary.txt", "概要")
    result = LoopRunResult(
        status="completed",
        state=LoopState(
            tender_info="i",
            task_background="b",
            tender_summary="概要",
            report="报告",
        ),
        completed_steps=["get_tender_summary"],
        step_results=[StepResult("get_tender_summary", "概要", 100, 1)],
    )
    write_run_state(loop_dir, result)
    write_results(loop_dir, result)

    assert (loop_dir / "steps" / "01_tender_summary.txt").read_text(encoding="utf-8") == "概要"
    run_state = json.loads((loop_dir / "run_state.json").read_text(encoding="utf-8"))
    assert run_state["status"] == "completed"
    results = json.loads((loop_dir / "results.json").read_text(encoding="utf-8"))
    assert results["tender_summary"] == "概要"
    assert (loop_dir / "report.md").read_text(encoding="utf-8") == "报告"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/tender_insights/unit/test_summary_loop_writer.py -v`

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/tender_insights/summary_loop/writer.py
from __future__ import annotations

import json
import shutil
from pathlib import Path

from tender_insights.summary_loop.models import LoopRunResult


def init_loop_dir(workspace_root: Path, *, overwrite: bool) -> Path:
    loop_dir = workspace_root / "summary_loop"
    if loop_dir.exists():
        if not overwrite:
            raise FileExistsError(f"summary_loop already exists: {loop_dir}")
        shutil.rmtree(loop_dir)
    (loop_dir / "steps").mkdir(parents=True, exist_ok=True)
    return loop_dir


def write_step(loop_dir: Path, filename: str, content: str) -> Path:
    dest = loop_dir / "steps" / filename
    dest.write_text(content, encoding="utf-8")
    return dest


def write_run_state(loop_dir: Path, result: LoopRunResult) -> Path:
    dest = loop_dir / "run_state.json"
    dest.write_text(
        json.dumps(result.to_run_state_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return dest


def write_results(loop_dir: Path, result: LoopRunResult) -> Path:
    dest = loop_dir / "results.json"
    dest.write_text(
        json.dumps(result.to_results_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if result.state.report:
        (loop_dir / "report.md").write_text(result.state.report, encoding="utf-8")
    return dest
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/tender_insights/unit/test_summary_loop_writer.py -v`

Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/tender_insights/summary_loop/writer.py \
        tests/tender_insights/unit/test_summary_loop_writer.py
git commit -m "feat(summary-loop): add workspace writer for loop artifacts"
```

---

### Task 5: SummaryLoopRunner（状态传递、重试、超时中止）

**Files:**
- Create: `src/tender_insights/summary_loop/runner.py`
- Test: `tests/tender_insights/unit/test_summary_loop_runner.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tender_insights/unit/test_summary_loop_runner.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from tender_insights.summary_loop.client import InvokeTextResult
from tender_insights.summary_loop.models import (
    LoopState,
    SummaryLoopInvokeError,
    SummaryLoopInvokeTimeoutError,
)
from tender_insights.summary_loop.runner import SummaryLoopRunner
from tender_insights.summary_loop.tasks import TASK_DEFINITIONS


@dataclass
class FakeSummaryLoopClient:
    responses: list[str] = field(default_factory=list)
    errors: list[Exception | None] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)
    _index: int = 0

    def invoke(self, input: dict[str, Any]) -> InvokeTextResult:
        self.calls.append(dict(input))
        if self._index < len(self.errors) and self.errors[self._index] is not None:
            err = self.errors[self._index]
            self._index += 1
            raise err
        text = self.responses[self._index]
        self._index += 1
        return InvokeTextResult(output=text, duration_ms=10, raw_response={"status": "completed"})


def test_runner_accumulates_state_across_five_steps():
    client = FakeSummaryLoopClient(
        responses=["概要", "得分", "废标", "响应", "完整报告"],
    )
    runner = SummaryLoopRunner(client=client)
    result = runner.run(LoopState(tender_info="正文", task_background="背景"))

    assert result.status == "completed"
    assert result.state.tender_summary == "概要"
    assert result.state.score_points == "得分"
    assert result.state.report == "完整报告"
    assert len(result.completed_steps) == 5
    assert client.calls[1]["tender_summary"] == "概要"
    assert client.calls[4]["disqualification_items"] == "废标"


def test_runner_retries_once_on_invoke_error():
    client = FakeSummaryLoopClient(
        responses=["概要", "得分", "废标", "响应", "完整报告"],
        errors=[SummaryLoopInvokeError("boom"), None],
    )
    runner = SummaryLoopRunner(client=client)
    result = runner.run(LoopState(tender_info="x", task_background="y"))
    assert result.status == "completed"
    assert result.step_results[0].attempt == 2


def test_runner_does_not_retry_on_timeout():
    client = FakeSummaryLoopClient(
        responses=[],
        errors=[SummaryLoopInvokeTimeoutError("timeout", elapsed_ms=180000, configured_timeout_s=600)],
    )
    runner = SummaryLoopRunner(client=client)
    result = runner.run(LoopState(tender_info="x", task_background="y"))
    assert result.status == "failed"
    assert result.error_type == "timeout"
    assert result.failed_step == TASK_DEFINITIONS[0].current_task
    assert result.elapsed_ms == 180000
    assert len(client.calls) == 1


def test_runner_fails_after_two_non_timeout_errors():
    client = FakeSummaryLoopClient(
        responses=[],
        errors=[
            SummaryLoopInvokeError("e1"),
            SummaryLoopInvokeError("e2"),
        ],
    )
    runner = SummaryLoopRunner(client=client)
    result = runner.run(LoopState(tender_info="x", task_background="y"))
    assert result.status == "failed"
    assert result.error_type == "invoke_error"
    assert len(client.calls) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/tender_insights/unit/test_summary_loop_runner.py -v`

Expected: FAIL with `ImportError` / `ModuleNotFoundError` for `SummaryLoopRunner`

- [ ] **Step 3: Write minimal implementation**

```python
# src/tender_insights/summary_loop/runner.py
from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from doc_chunk.workspace.layout import OutputWorkspace

from tender_insights.common.content_source import prepare_interpret_source
from tender_insights.config import InsightsConfig
from tender_insights.summary_loop.client import (
    InvokeTextResult,
    SummaryLoopClient,
    create_summary_loop_client_from_env,
)
from tender_insights.summary_loop.models import (
    LoopRunResult,
    LoopState,
    StepResult,
    SummaryLoopInvokeError,
    SummaryLoopInvokeTimeoutError,
)
from tender_insights.summary_loop.tasks import TASK_DEFINITIONS
from tender_insights.summary_loop.writer import init_loop_dir, write_results, write_run_state, write_step

MAX_RETRIES = 1


class SummaryLoopClientProtocol(Protocol):
    def invoke(self, input: dict) -> InvokeTextResult: ...


class SummaryLoopRunner:
    def __init__(
        self,
        *,
        client: SummaryLoopClientProtocol,
        on_progress: Callable[[str, dict], None] | None = None,
    ) -> None:
        self._client = client
        self._on_progress = on_progress

    def run(self, state: LoopState) -> LoopRunResult:
        result = LoopRunResult(status="partial", state=state)
        total = len(TASK_DEFINITIONS)
        for index, task in enumerate(TASK_DEFINITIONS, start=1):
            if self._on_progress:
                self._on_progress(
                    "summary_loop",
                    {
                        "message": f"执行 {task.current_task}",
                        "current": index,
                        "total": total,
                        "step": task.current_task,
                    },
                )
            last_error: Exception | None = None
            succeeded = False
            for attempt in range(MAX_RETRIES + 1):
                try:
                    invoke_result = self._client.invoke(state.to_invoke_input(task))
                    state.apply_output(task, invoke_result.output)
                    result.completed_steps.append(task.current_task)
                    result.step_results.append(
                        StepResult(
                            current_task=task.current_task,
                            output=invoke_result.output,
                            duration_ms=invoke_result.duration_ms,
                            attempt=attempt + 1,
                        )
                    )
                    succeeded = True
                    break
                except SummaryLoopInvokeTimeoutError as exc:
                    return self._failed_result(
                        result,
                        task.current_task,
                        error_type="timeout",
                        error_message=str(exc),
                        elapsed_ms=exc.elapsed_ms,
                        configured_timeout_s=exc.configured_timeout_s,
                    )
                except SummaryLoopInvokeError as exc:
                    last_error = exc
                    if attempt >= MAX_RETRIES:
                        return self._failed_result(
                            result,
                            task.current_task,
                            error_type="invoke_error",
                            error_message=str(exc),
                            elapsed_ms=exc.elapsed_ms,
                        )
            if not succeeded:
                return self._failed_result(
                    result,
                    task.current_task,
                    error_type="invoke_error",
                    error_message=str(last_error),
                )

        result.status = "completed"
        return result

    @staticmethod
    def _failed_result(
        result: LoopRunResult,
        failed_step: str,
        *,
        error_type: str,
        error_message: str,
        elapsed_ms: int | None = None,
        configured_timeout_s: int | None = None,
    ) -> LoopRunResult:
        result.status = "failed" if not result.completed_steps else "partial"
        result.failed_step = failed_step
        result.error_type = error_type
        result.error_message = error_message
        result.elapsed_ms = elapsed_ms
        result.configured_timeout_s = configured_timeout_s
        return result


def run_summary_loop(
    workspace: OutputWorkspace,
    *,
    task_background: str,
    client: SummaryLoopClient | None = None,
    config: InsightsConfig | None = None,
    on_progress: Callable[[str, dict], None] | None = None,
    overwrite: bool = False,
    timeout_s: int | None = None,
) -> LoopRunResult:
    config = config or InsightsConfig.from_env()
    resolved_client = client
    if resolved_client is None:
        resolved_client = create_summary_loop_client_from_env()
        if timeout_s is not None:
            resolved_client = SummaryLoopClient(
                base_url=resolved_client.base_url,
                api_key=resolved_client.api_key,
                timeout_s=timeout_s,
            )

    source = prepare_interpret_source(workspace, config=config)
    state = LoopState(tender_info=source.markdown, task_background=task_background)
    loop_dir = init_loop_dir(workspace.root, overwrite=overwrite)

    runner = SummaryLoopRunner(client=resolved_client, on_progress=on_progress)
    result = runner.run(state)

    for step_result, task in zip(result.step_results, TASK_DEFINITIONS[: len(result.step_results)], strict=False):
        write_step(loop_dir, task.step_filename, step_result.output)

    write_run_state(loop_dir, result)
    write_results(loop_dir, result)
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/tender_insights/unit/test_summary_loop_runner.py -v`

Expected: PASS (4 tests)

- [ ] **Step 5: Update `__init__.py` export**

```python
# src/tender_insights/summary_loop/__init__.py
from tender_insights.summary_loop.runner import run_summary_loop

__all__ = ["run_summary_loop"]
```

- [ ] **Step 6: Run tests again**

Run: `.venv/bin/python -m pytest tests/tender_insights/unit/test_summary_loop_runner.py -v`

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/tender_insights/summary_loop/runner.py \
        src/tender_insights/summary_loop/__init__.py \
        tests/tender_insights/unit/test_summary_loop_runner.py
git commit -m "feat(summary-loop): add runner with retry and timeout abort"
```

---

### Task 6: API 封装与 CLI 子命令

**Files:**
- Modify: `src/tender_insights/api.py`
- Modify: `src/tender_insights/cli/main.py`
- Modify: `tests/tender_insights/unit/test_cli.py`
- Modify: `.env.example`

- [ ] **Step 1: Write the failing CLI test**

在 `tests/tender_insights/unit/test_cli.py` 末尾追加：

```python
def test_cli_loop_help() -> None:
    result = CliRunner().invoke(app, ["loop", "--help"])
    assert result.exit_code == 0
    assert "--background" in result.stdout
    assert "--timeout" in result.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/tender_insights/unit/test_cli.py::test_cli_loop_help -v`

Expected: FAIL — typer 报 `No such command 'loop'`

- [ ] **Step 3: Implement API + CLI**

在 `src/tender_insights/api.py` 末尾追加：

```python
from tender_insights.summary_loop.models import LoopRunResult
from tender_insights.summary_loop.runner import run_summary_loop as _run_summary_loop


def run_summary_loop_job(
    workspace: OutputWorkspace,
    *,
    task_background: str,
    on_progress: Callable[[str, dict], None] | None = None,
    overwrite: bool = False,
    timeout_s: int | None = None,
) -> LoopRunResult:
    return _run_summary_loop(
        workspace,
        task_background=task_background,
        on_progress=on_progress,
        overwrite=overwrite,
        timeout_s=timeout_s,
    )
```

在 `src/tender_insights/cli/main.py` 的 import 区追加 `run_summary_loop_job`，并追加命令：

```python
@app.command("loop")
def loop_cmd(
    paths: list[Path] = typer.Argument(..., help="工作区目录或原始文档"),
    output: Path | None = typer.Option(None, "-o", "--output"),
    background: str = typer.Option(..., "--background", help="任务背景描述"),
    overwrite: bool = typer.Option(False, "--overwrite"),
    timeout: int | None = typer.Option(None, "--timeout", help="单次 invoke 超时秒数，默认 600"),
) -> None:
    ws = _resolve_workspaces(paths, output, overwrite)
    result = run_summary_loop_job(
        ws,
        task_background=background,
        overwrite=overwrite,
        timeout_s=timeout,
    )
    loop_dir = ws.root / "summary_loop"
    if result.status != "completed":
        typer.echo(f"Summary loop failed at step {result.failed_step}: {result.error_message}", err=True)
        typer.echo(f"Partial results written to {loop_dir}")
        raise typer.Exit(code=1)
    typer.echo(f"Wrote {loop_dir / 'results.json'}")
    typer.echo(f"Wrote {loop_dir / 'report.md'}")
```

在 `.env.example` 的 `AGENT_PLATFORM_BASE_URL` 行后追加：

```bash
AGENT_PLATFORM_API_KEY=
SUMMARY_LOOP_INVOKE_TIMEOUT_S=600
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/tender_insights/unit/test_cli.py -v`

Expected: PASS（含新增 `test_cli_loop_help`）

- [ ] **Step 5: Commit**

```bash
git add src/tender_insights/api.py \
        src/tender_insights/cli/main.py \
        tests/tender_insights/unit/test_cli.py \
        .env.example
git commit -m "feat(summary-loop): add loop CLI command and API entrypoint"
```

---

### Task 7: 全量回归与 README 补充

**Files:**
- Modify: `README.md`（在 tender-insights 命令区追加 `loop` 示例）

- [ ] **Step 1: Run full unit test suite**

Run: `.venv/bin/python -m pytest tests/tender_insights/unit/ -v`

Expected: 全部 PASS

- [ ] **Step 2: Add README snippet**

在 `README.md` 的 `tender-insights` 命令示例区追加：

```markdown
### 标书解读循环（summary loop）

```bash
export AGENT_PLATFORM_API_KEY=your-key
export AGENT_PLATFORM_BASE_URL=http://localhost:8000

tender-insights loop /path/to/bid.docx \
  -o ./output/my-bid \
  --background "本次投标重点关注价格分和技术方案" \
  --overwrite
```

产物目录：`{workspace}/summary_loop/`（`results.json`、`report.md`、`run_state.json`）。
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document tender-insights loop command"
```

---

## Spec 覆盖自检

| Spec 要求 | 对应 Task |
|-----------|-----------|
| `tender-insights loop` 子命令 | Task 6 |
| doc_chunk + OCR 增强 `tender_info` | Task 5 `run_summary_loop` |
| 5 步顺序 invoke `tender_summary_app` | Task 2 + Task 5 |
| 纯文本 `output` | Task 3 |
| 600s 超时 + `--timeout` 覆盖 | Task 3 + Task 6 |
| 超时立即中止、不重试 | Task 5 `test_runner_does_not_retry_on_timeout` |
| 非超时重试 1 次 | Task 5 `test_runner_retries_once_on_invoke_error` |
| `run_state.json` 诊断字段 | Task 1 `to_run_state_dict` + Task 4 |
| `X-API-Key` / `AGENT_PLATFORM_API_KEY` | Task 3 |
| `summary_loop/` 落盘结构 | Task 4 |
| 不改动 interpret | 无 interpret 文件修改 |

## 执行选项

Plan complete and saved to `docs/superpowers/plans/2026-07-07-tender-summary-loop.md`. Two execution options:

**1. Subagent-Driven (recommended)** — 每个 Task 派发独立 subagent，任务间做 review，迭代快

**2. Inline Execution** — 在本会话用 executing-plans 按 Task 批量执行，checkpoint 处暂停 review

Which approach?
