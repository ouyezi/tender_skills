# Tender Diagnosis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `tender_insights` 中新增 `diagnose` 子命令，读取工作区 `chunks/` 与 `summary_loop/report.md`，经 8000–15000 字符分段优化后顺序调用平台 `bid_chunk_summary`，滚动产出概要并落盘到 `diagnosis/`。

**Architecture:** 新建 `tender_insights/diagnosis/` 子包：`SegmentOptimizer`（合并/拆分）、`DiagnosisClient`（专用 HTTP，structuredOutput）、`DiagnosisRunner`（顺序循环 + 重试）、`loader`/`writer`。CLI 仅接受已有工作区，严格校验前置文件。

**Tech Stack:** Python 3.11+、Pydantic v2、Typer、stdlib `urllib`、现有 `doc_chunk` / `tender_insights.summary_loop`（模式参考）

**设计文档:** `docs/superpowers/specs/2026-07-07-tender-diagnosis-design.md`

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `src/tender_insights/diagnosis/__init__.py` | 导出 `run_diagnosis` |
| `src/tender_insights/diagnosis/models.py` | 数据模型、异常、`DiagnosisRunResult` |
| `src/tender_insights/diagnosis/segment_optimizer.py` | 8000–15000 字符分段 |
| `src/tender_insights/diagnosis/loader.py` | 前置校验 + 加载 report/chunks |
| `src/tender_insights/diagnosis/client.py` | `DiagnosisClient`、`create_diagnosis_client_from_env` |
| `src/tender_insights/diagnosis/writer.py` | `diagnosis/` 落盘 |
| `src/tender_insights/diagnosis/runner.py` | `DiagnosisRunner`、`run_diagnosis` |
| `src/tender_insights/api.py` | 新增 `run_diagnosis_job` |
| `src/tender_insights/cli/main.py` | 新增 `diagnose` 子命令 |
| `.env.example` | 新增 `DIAGNOSIS_INVOKE_TIMEOUT_S` |
| `tests/tender_insights/unit/test_diagnosis_models.py` | models 单元测试 |
| `tests/tender_insights/unit/test_diagnosis_segment_optimizer.py` | 分段优化测试 |
| `tests/tender_insights/unit/test_diagnosis_loader.py` | loader 前置校验测试 |
| `tests/tender_insights/unit/test_diagnosis_client.py` | client HTTP mock 测试 |
| `tests/tender_insights/unit/test_diagnosis_writer.py` | writer 落盘测试 |
| `tests/tender_insights/unit/test_diagnosis_runner.py` | runner 滚动状态、重试、超时测试 |
| `tests/tender_insights/unit/test_cli.py` | 补充 `diagnose --help` 测试（修改） |

---

### Task 1: 数据模型与异常

**Files:**
- Create: `src/tender_insights/diagnosis/__init__.py`
- Create: `src/tender_insights/diagnosis/models.py`
- Test: `tests/tender_insights/unit/test_diagnosis_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tender_insights/unit/test_diagnosis_models.py
from __future__ import annotations

import pytest

from tender_insights.diagnosis.models import (
    ChunkSummaryOutput,
    DiagnosisInvokeError,
    DiagnosisInvokeTimeoutError,
    DiagnosisPrerequisiteError,
    DiagnosisRunResult,
    DiagnosisSegment,
    DiagnosisState,
)


def test_diagnosis_state_to_invoke_input():
    seg = DiagnosisSegment(
        segment_index=2,
        markdown="正文",
        char_count=2,
        source_chunk_ids=["c1"],
        section_path=["第一章"],
    )
    state = DiagnosisState(
        tender_report="解读报告",
        preview_summary="上一段整体概述",
        segments=[DiagnosisSegment(1, "a", 1, ["c0"], []), seg],
    )
    payload = state.to_invoke_input(seg)
    assert payload == {
        "chunk": "正文",
        "tender_report": "解读报告",
        "total_chunk_count": "2",
        "current_count": "2",
        "preview_summary": "上一段整体概述",
    }


def test_diagnosis_state_apply_output_updates_preview():
    state = DiagnosisState(tender_report="r", preview_summary="", segments=[])
    out = ChunkSummaryOutput(current_summary="当前", total_summary="整体")
    state.apply_output(out)
    assert state.preview_summary == "整体"


def test_diagnosis_run_result_to_run_state_dict_includes_timeout_fields():
    state = DiagnosisState(tender_report="r", preview_summary="", segments=[])
    result = DiagnosisRunResult(
        status="failed",
        state=state,
        failed_segment=2,
        error_type="timeout",
        error_message="timeout",
        elapsed_ms=180000,
        configured_timeout_s=600,
    )
    data = result.to_run_state_dict()
    assert data["failed_segment"] == 2
    assert data["elapsed_ms"] == 180000
    assert data["configured_timeout_s"] == 600


def test_diagnosis_invoke_timeout_error_is_subclass():
    with pytest.raises(DiagnosisInvokeError):
        raise DiagnosisInvokeTimeoutError("timeout", elapsed_ms=180000, configured_timeout_s=600)


def test_diagnosis_prerequisite_error_message():
    err = DiagnosisPrerequisiteError("缺少 report.md")
    assert "report.md" in str(err)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/tongqianni/xlab/tender_skills && .venv/bin/python -m pytest tests/tender_insights/unit/test_diagnosis_models.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'tender_insights.diagnosis'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/tender_insights/diagnosis/models.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel


class DiagnosisError(Exception):
    """Base error for diagnosis."""


class DiagnosisPrerequisiteError(DiagnosisError):
    """Missing summary_loop/report.md or chunks/."""


class DiagnosisInvokeError(DiagnosisError):
    def __init__(self, message: str, *, elapsed_ms: int | None = None) -> None:
        super().__init__(message)
        self.elapsed_ms = elapsed_ms


class DiagnosisInvokeTimeoutError(DiagnosisInvokeError):
    def __init__(self, message: str, *, elapsed_ms: int, configured_timeout_s: int) -> None:
        super().__init__(message, elapsed_ms=elapsed_ms)
        self.configured_timeout_s = configured_timeout_s


class ChunkSummaryOutput(BaseModel):
    current_summary: str
    total_summary: str


@dataclass(frozen=True)
class DiagnosisSegment:
    segment_index: int
    markdown: str
    char_count: int
    source_chunk_ids: list[str]
    section_path: list[str]


@dataclass
class DiagnosisState:
    tender_report: str
    preview_summary: str
    segments: list[DiagnosisSegment]

    def to_invoke_input(self, segment: DiagnosisSegment) -> dict[str, str]:
        return {
            "chunk": segment.markdown,
            "tender_report": self.tender_report,
            "total_chunk_count": str(len(self.segments)),
            "current_count": str(segment.segment_index),
            "preview_summary": self.preview_summary,
        }

    def apply_output(self, output: ChunkSummaryOutput) -> None:
        self.preview_summary = output.total_summary


@dataclass(frozen=True)
class SegmentStepResult:
    segment_index: int
    output: ChunkSummaryOutput
    duration_ms: int
    attempt: int
    char_count: int
    source_chunk_ids: list[str]


@dataclass
class DiagnosisRunResult:
    status: Literal["completed", "failed", "partial"]
    state: DiagnosisState
    completed_segments: list[int] = field(default_factory=list)
    step_results: list[SegmentStepResult] = field(default_factory=list)
    failed_segment: int | None = None
    error_type: str | None = None
    error_message: str | None = None
    elapsed_ms: int | None = None
    configured_timeout_s: int | None = None

    def to_run_state_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "status": self.status,
            "completed_segments": self.completed_segments,
            "steps": [
                {
                    "segment_index": s.segment_index,
                    "duration_ms": s.duration_ms,
                    "attempt": s.attempt,
                    "char_count": s.char_count,
                }
                for s in self.step_results
            ],
        }
        if self.failed_segment is not None:
            data["failed_segment"] = self.failed_segment
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

```python
# src/tender_insights/diagnosis/__init__.py
# Task 6 完成后在此导出 run_diagnosis
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/tender_insights/unit/test_diagnosis_models.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tender_insights/diagnosis/__init__.py \
        src/tender_insights/diagnosis/models.py \
        tests/tender_insights/unit/test_diagnosis_models.py
git commit -m "feat(diagnosis): add models and exception types"
```

---

### Task 2: 分段优化 SegmentOptimizer

**Files:**
- Create: `src/tender_insights/diagnosis/segment_optimizer.py`
- Test: `tests/tender_insights/unit/test_diagnosis_segment_optimizer.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tender_insights/unit/test_diagnosis_segment_optimizer.py
from __future__ import annotations

from doc_chunk.models.chunk import ContentChunk

from tender_insights.diagnosis.segment_optimizer import (
    MAX_CHARS,
    MIN_CHARS,
    optimize_segments,
)


def _chunk(chunk_id: str, markdown: str) -> ContentChunk:
    return ContentChunk(chunk_id=chunk_id, title=chunk_id, markdown=markdown)


def test_single_short_chunk_is_one_segment_exempt_min():
    chunks = [_chunk("c1", "x" * 500)]
    segments = optimize_segments(chunks)
    assert len(segments) == 1
    assert segments[0].char_count == 500
    assert segments[0].source_chunk_ids == ["c1"]


def test_merges_small_chunks_into_non_last_segment():
    chunks = [
        _chunk("c1", "a" * 4000),
        _chunk("c2", "b" * 5000),
        _chunk("c3", "c" * 3000),
        _chunk("c4", "d" * 9000),
        _chunk("c5", "e" * 500),
    ]
    segments = optimize_segments(chunks)
    assert len(segments) == 2
    assert MIN_CHARS <= segments[0].char_count <= MAX_CHARS
    assert segments[0].source_chunk_ids == ["c1", "c2", "c3"]
    assert segments[1].char_count == 9500
    assert segments[1].source_chunk_ids == ["c4", "c5"]


def test_splits_oversized_chunk_by_lines():
    big = "line\n" * 4000
    chunks = [_chunk("c1", big), _chunk("c2", "z" * 9000)]
    segments = optimize_segments(chunks)
    assert all(s.char_count <= MAX_CHARS for s in segments[:-1])
    assert segments[0].char_count >= MIN_CHARS


def test_non_last_segments_respect_char_bounds_when_multiple():
    chunks = [_chunk(f"c{i}", "x" * 10000) for i in range(4)]
    segments = optimize_segments(chunks)
    assert len(segments) >= 2
    for seg in segments[:-1]:
        assert MIN_CHARS <= seg.char_count <= MAX_CHARS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/tender_insights/unit/test_diagnosis_segment_optimizer.py -v`

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/tender_insights/diagnosis/segment_optimizer.py
from __future__ import annotations

from dataclasses import dataclass

from doc_chunk.models.chunk import ContentChunk

from tender_insights.diagnosis.models import DiagnosisSegment

MIN_CHARS = 8000
MAX_CHARS = 15000


@dataclass(frozen=True, slots=True)
class _Atom:
    markdown: str
    source_chunk_id: str
    section_path: list[str]


def _split_by_lines(markdown: str, max_chars: int) -> list[str]:
    if len(markdown) <= max_chars:
        return [markdown]
    parts: list[str] = []
    current: list[str] = []
    for line in markdown.splitlines(keepends=True):
        candidate = "".join(current + [line])
        if current and len(candidate) > max_chars:
            parts.append("".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        parts.append("".join(current))
    return parts or [markdown]


def _atomize_chunks(chunks: list[ContentChunk]) -> list[_Atom]:
    atoms: list[_Atom] = []
    for chunk in chunks:
        for piece in _split_by_lines(chunk.markdown, MAX_CHARS):
            if not piece.strip():
                continue
            atoms.append(
                _Atom(
                    markdown=piece,
                    source_chunk_id=chunk.chunk_id,
                    section_path=list(chunk.section_path),
                )
            )
    return atoms


def _join_atoms(atoms: list[_Atom]) -> str:
    return "\n\n".join(a.markdown.strip() for a in atoms if a.markdown.strip())


def _make_segment(atoms: list[_Atom], segment_index: int) -> DiagnosisSegment:
    markdown = _join_atoms(atoms)
    return DiagnosisSegment(
        segment_index=segment_index,
        markdown=markdown,
        char_count=len(markdown),
        source_chunk_ids=list(dict.fromkeys(a.source_chunk_id for a in atoms)),
        section_path=list(atoms[0].section_path) if atoms else [],
    )


def optimize_segments(chunks: list[ContentChunk]) -> list[DiagnosisSegment]:
    atoms = _atomize_chunks(chunks)
    if not atoms:
        return []
    if len(atoms) == 1:
        return [_make_segment(atoms, 1)]

    segments: list[DiagnosisSegment] = []
    idx = 0
    while idx < len(atoms):
        if len(atoms) - idx == 1:
            segments.append(_make_segment([atoms[idx]], len(segments) + 1))
            break

        buf: list[_Atom] = []
        while idx < len(atoms):
            atom = atoms[idx]
            candidate = _join_atoms(buf + [atom]) if buf else atom.markdown
            if len(candidate) <= MAX_CHARS:
                buf.append(atom)
                idx += 1
                joined = _join_atoms(buf)
                if len(joined) >= MIN_CHARS and idx < len(atoms):
                    next_joined = _join_atoms(buf + [atoms[idx]])
                    if len(next_joined) > MAX_CHARS:
                        break
                continue

            if buf and len(_join_atoms(buf)) >= MIN_CHARS:
                break

            buf.append(atom)
            idx += 1
            break

        if not buf:
            raise ValueError("unable to pack diagnosis segments")
        segments.append(_make_segment(buf, len(segments) + 1))

    return segments
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/tender_insights/unit/test_diagnosis_segment_optimizer.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tender_insights/diagnosis/segment_optimizer.py \
        tests/tender_insights/unit/test_diagnosis_segment_optimizer.py
git commit -m "feat(diagnosis): add 8000-15000 char segment optimizer"
```

---

### Task 3: Loader 前置校验与加载

**Files:**
- Create: `src/tender_insights/diagnosis/loader.py`
- Test: `tests/tender_insights/unit/test_diagnosis_loader.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tender_insights/unit/test_diagnosis_loader.py
from __future__ import annotations

import json
from pathlib import Path

import pytest

from doc_chunk.workspace.layout import OutputWorkspace
from tender_insights.diagnosis.loader import load_diagnosis_inputs
from tender_insights.diagnosis.models import DiagnosisPrerequisiteError


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


def test_loader_raises_when_report_missing(tmp_path: Path):
    ws = _minimal_workspace(tmp_path)
    chunks_dir = ws.root / "chunks"
    chunks_dir.mkdir()
    (chunks_dir / "index.json").write_text(
        json.dumps({"schema_version": "1.0", "chunks": []}),
        encoding="utf-8",
    )
    with pytest.raises(DiagnosisPrerequisiteError, match="summary_loop/report.md"):
        load_diagnosis_inputs(ws)


def test_loader_raises_when_chunks_missing(tmp_path: Path):
    ws = _minimal_workspace(tmp_path)
    loop_dir = ws.root / "summary_loop"
    loop_dir.mkdir()
    (loop_dir / "report.md").write_text("# 解读\n", encoding="utf-8")
    with pytest.raises(DiagnosisPrerequisiteError, match="chunks/"):
        load_diagnosis_inputs(ws)


def test_loader_returns_report_and_chunks(tmp_path: Path):
    ws = _minimal_workspace(tmp_path)
    loop_dir = ws.root / "summary_loop"
    loop_dir.mkdir()
    (loop_dir / "report.md").write_text("# 解读报告\n", encoding="utf-8")

    chunks_dir = ws.root / "chunks"
    chunks_dir.mkdir()
    chunk_path = "0001.json"
    (chunks_dir / chunk_path).write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "chunk_id": "chunk-001",
                "title": "第一章",
                "markdown": "正文内容",
            }
        ),
        encoding="utf-8",
    )
    (chunks_dir / "index.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "chunks": [{"chunk_id": "chunk-001", "path": chunk_path, "section_path": ["第一章"]}],
            }
        ),
        encoding="utf-8",
    )

    report, chunks = load_diagnosis_inputs(ws)
    assert report == "# 解读报告\n"
    assert len(chunks) == 1
    assert chunks[0].chunk_id == "chunk-001"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/tender_insights/unit/test_diagnosis_loader.py -v`

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/tender_insights/diagnosis/loader.py
from __future__ import annotations

import json

from doc_chunk.models.chunk import ChunkIndex, ContentChunk
from doc_chunk.workspace.layout import OutputWorkspace

from tender_insights.diagnosis.models import DiagnosisPrerequisiteError

_REPORT_HINT = (
    "缺少 summary_loop/report.md，请先运行：\n"
    "  tender-insights loop <workspace> --background \"...\""
)
_CHUNKS_HINT = (
    "缺少 chunks/，请先运行：\n"
    "  doc-chunk pipeline <file> -o <workspace> --overwrite"
)


def load_diagnosis_inputs(workspace: OutputWorkspace) -> tuple[str, list[ContentChunk]]:
    report_path = workspace.root / "summary_loop" / "report.md"
    if not report_path.is_file():
        raise DiagnosisPrerequisiteError(_REPORT_HINT)

    index_path = workspace.chunks_dir / "index.json"
    if not index_path.is_file():
        raise DiagnosisPrerequisiteError(_CHUNKS_HINT)

    index = ChunkIndex.model_validate_json(index_path.read_text(encoding="utf-8"))
    if not index.chunks:
        raise DiagnosisPrerequisiteError(_CHUNKS_HINT)

    chunks: list[ContentChunk] = []
    for entry in index.chunks:
        chunk_path = workspace.chunks_dir / entry.path
        if not chunk_path.is_file():
            continue
        chunk = ContentChunk.model_validate(json.loads(chunk_path.read_text(encoding="utf-8")))
        chunks.append(chunk)

    if not chunks:
        raise DiagnosisPrerequisiteError(_CHUNKS_HINT)

    tender_report = report_path.read_text(encoding="utf-8")
    return tender_report, chunks
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/tender_insights/unit/test_diagnosis_loader.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tender_insights/diagnosis/loader.py \
        tests/tender_insights/unit/test_diagnosis_loader.py
git commit -m "feat(diagnosis): add prerequisite loader for report and chunks"
```

---

### Task 4: DiagnosisClient（structuredOutput）

**Files:**
- Create: `src/tender_insights/diagnosis/client.py`
- Test: `tests/tender_insights/unit/test_diagnosis_client.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tender_insights/unit/test_diagnosis_client.py
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from tender_insights.diagnosis.client import (
    APP_NAME,
    DiagnosisClient,
    create_diagnosis_client_from_env,
)
from tender_insights.diagnosis.models import (
    ChunkSummaryOutput,
    DiagnosisInvokeError,
    DiagnosisInvokeTimeoutError,
)


def test_invoke_returns_structured_output():
    fake_resp = MagicMock()
    fake_resp.read.return_value = json.dumps(
        {
            "status": "completed",
            "structuredOutput": {
                "current_summary": "当前",
                "total_summary": "整体",
            },
        }
    ).encode("utf-8")
    fake_resp.__enter__ = lambda s: s
    fake_resp.__exit__ = MagicMock(return_value=False)

    captured: dict = {}

    def _urlopen(req, timeout):
        captured["timeout"] = timeout
        captured["headers"] = dict(req.header_items())
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return fake_resp

    client = DiagnosisClient(
        base_url="http://localhost:8000",
        api_key="test-key",
        timeout_s=600,
    )

    with patch("urllib.request.urlopen", side_effect=_urlopen):
        result = client.invoke({"chunk": "x", "current_count": "1"})

    assert result.output == ChunkSummaryOutput(current_summary="当前", total_summary="整体")
    assert captured["timeout"] == 600
    assert captured["body"]["appName"] == APP_NAME
    assert captured["headers"]["X-api-key"] == "test-key"


def test_invoke_raises_on_missing_structured_output():
    fake_resp = MagicMock()
    fake_resp.read.return_value = json.dumps({"status": "completed", "output": "text only"}).encode("utf-8")
    fake_resp.__enter__ = lambda s: s
    fake_resp.__exit__ = MagicMock(return_value=False)

    client = DiagnosisClient(base_url="http://localhost:8000", api_key="k", timeout_s=600)
    with patch("urllib.request.urlopen", return_value=fake_resp):
        with pytest.raises(DiagnosisInvokeError, match="structured"):
            client.invoke({})


def test_invoke_timeout_maps_to_timeout_error():
    import socket
    import urllib.error

    client = DiagnosisClient(base_url="http://localhost:8000", api_key="k", timeout_s=600)
    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.URLError(socket.timeout("timed out")),
    ):
        with pytest.raises(DiagnosisInvokeTimeoutError) as exc_info:
            client.invoke({})
    assert exc_info.value.configured_timeout_s == 600


def test_create_client_from_env(monkeypatch):
    monkeypatch.setenv("AGENT_PLATFORM_BASE_URL", "http://127.0.0.1:8000")
    monkeypatch.setenv("AGENT_PLATFORM_API_KEY", "env-key")
    monkeypatch.setenv("DIAGNOSIS_INVOKE_TIMEOUT_S", "300")
    client = create_diagnosis_client_from_env()
    assert client.timeout_s == 300
    assert client.api_key == "env-key"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/tender_insights/unit/test_diagnosis_client.py -v`

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/tender_insights/diagnosis/client.py
from __future__ import annotations

import json
import os
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from agent_platform.json_coerce import coerce_structured_output

from tender_insights.diagnosis.models import (
    ChunkSummaryOutput,
    DiagnosisInvokeError,
    DiagnosisInvokeTimeoutError,
)

APP_NAME = "bid_chunk_summary"


def _validate_http_header_value(name: str, value: str) -> str:
    try:
        value.encode("latin-1")
    except UnicodeEncodeError as exc:
        raise DiagnosisInvokeError(
            f"{name} must contain only ASCII characters (HTTP header limit); "
            f"check that AGENT_PLATFORM_API_KEY is the platform API key, not Chinese text or LLM_API_KEY"
        ) from exc
    return value


@dataclass(frozen=True)
class InvokeStructuredResult:
    output: ChunkSummaryOutput
    duration_ms: int
    raw_response: dict[str, Any]


class DiagnosisClient:
    def __init__(self, *, base_url: str, api_key: str, timeout_s: int = 600) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = _validate_http_header_value("X-API-Key", api_key.strip())
        self.timeout_s = timeout_s

    def invoke(self, input: dict[str, Any]) -> InvokeStructuredResult:
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
                raise DiagnosisInvokeTimeoutError(
                    "invoke timed out before configured limit — check client/server timeout alignment",
                    elapsed_ms=elapsed_ms,
                    configured_timeout_s=self.timeout_s,
                ) from exc
            raise DiagnosisInvokeError(str(exc), elapsed_ms=elapsed_ms) from exc
        except TimeoutError as exc:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            raise DiagnosisInvokeTimeoutError(
                "invoke timed out before configured limit — check client/server timeout alignment",
                elapsed_ms=elapsed_ms,
                configured_timeout_s=self.timeout_s,
            ) from exc

        duration_ms = int((time.perf_counter() - started) * 1000)
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            raise DiagnosisInvokeError(f"invalid JSON response: {exc}", elapsed_ms=duration_ms) from exc

        if not isinstance(payload, dict):
            raise DiagnosisInvokeError("platform response must be JSON object", elapsed_ms=duration_ms)

        status = str(payload.get("status") or "")
        if status != "completed":
            raise DiagnosisInvokeError(
                f"invoke not completed for {APP_NAME}: {payload}",
                elapsed_ms=duration_ms,
            )

        structured = coerce_structured_output(payload)
        if not isinstance(structured, dict):
            raise DiagnosisInvokeError("missing structuredOutput", elapsed_ms=duration_ms)

        try:
            output = ChunkSummaryOutput.model_validate(structured)
        except Exception as exc:
            raise DiagnosisInvokeError(f"invalid structuredOutput: {exc}", elapsed_ms=duration_ms) from exc

        if not output.current_summary.strip() or not output.total_summary.strip():
            raise DiagnosisInvokeError("empty summary fields in structuredOutput", elapsed_ms=duration_ms)

        return InvokeStructuredResult(output=output, duration_ms=duration_ms, raw_response=payload)


def create_diagnosis_client_from_env() -> DiagnosisClient:
    base_url = os.environ.get("AGENT_PLATFORM_BASE_URL", "http://localhost:8000")
    api_key = os.environ.get("AGENT_PLATFORM_API_KEY", "").strip()
    if not api_key:
        raise DiagnosisInvokeError("AGENT_PLATFORM_API_KEY is required for diagnosis")
    timeout_raw = os.environ.get("DIAGNOSIS_INVOKE_TIMEOUT_S", "600").strip()
    timeout_s = int(timeout_raw)
    return DiagnosisClient(base_url=base_url, api_key=api_key, timeout_s=timeout_s)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/tender_insights/unit/test_diagnosis_client.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tender_insights/diagnosis/client.py \
        tests/tender_insights/unit/test_diagnosis_client.py
git commit -m "feat(diagnosis): add bid_chunk_summary platform client"
```

---

### Task 5: Writer 落盘

**Files:**
- Create: `src/tender_insights/diagnosis/writer.py`
- Test: `tests/tender_insights/unit/test_diagnosis_writer.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tender_insights/unit/test_diagnosis_writer.py
from __future__ import annotations

import json
from pathlib import Path

from tender_insights.diagnosis.models import (
    ChunkSummaryOutput,
    DiagnosisRunResult,
    DiagnosisSegment,
    DiagnosisState,
    SegmentStepResult,
)
from tender_insights.diagnosis.writer import (
    init_diagnosis_dir,
    write_run_state,
    write_segment_result,
    write_segments_plan,
    write_total_summary,
)


def test_init_diagnosis_dir_creates_structure(tmp_path: Path):
    loop_dir = init_diagnosis_dir(tmp_path, overwrite=False)
    assert loop_dir == tmp_path / "diagnosis"
    assert (loop_dir / "chunks").is_dir()


def test_write_segments_plan_and_step(tmp_path: Path):
    diag_dir = init_diagnosis_dir(tmp_path, overwrite=True)
    segments = [
        DiagnosisSegment(1, "a" * 9000, 9000, ["c1"], ["第一章"]),
    ]
    write_segments_plan(diag_dir, segments)

    step = SegmentStepResult(
        segment_index=1,
        output=ChunkSummaryOutput(current_summary="当前", total_summary="整体"),
        duration_ms=100,
        attempt=1,
        char_count=9000,
        source_chunk_ids=["c1"],
    )
    write_segment_result(diag_dir, step)

    plan = json.loads((diag_dir / "segments.json").read_text(encoding="utf-8"))
    assert plan["total_segments"] == 1
    assert plan["segments"][0]["char_count"] == 9000

    chunk_file = diag_dir / "chunks" / "001_summary.json"
    payload = json.loads(chunk_file.read_text(encoding="utf-8"))
    assert payload["total_summary"] == "整体"


def test_write_run_state_and_total_summary(tmp_path: Path):
    diag_dir = init_diagnosis_dir(tmp_path, overwrite=True)
    state = DiagnosisState(tender_report="r", preview_summary="整体", segments=[])
    result = DiagnosisRunResult(status="completed", state=state, completed_segments=[1])
    write_run_state(diag_dir, result)
    write_total_summary(diag_dir, "整体")

    run_state = json.loads((diag_dir / "run_state.json").read_text(encoding="utf-8"))
    assert run_state["status"] == "completed"
    assert (diag_dir / "total_summary.md").read_text(encoding="utf-8") == "整体"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/tender_insights/unit/test_diagnosis_writer.py -v`

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/tender_insights/diagnosis/writer.py
from __future__ import annotations

import json
import shutil
from pathlib import Path

from tender_insights.diagnosis.models import DiagnosisRunResult, DiagnosisSegment, SegmentStepResult
from tender_insights.diagnosis.segment_optimizer import MAX_CHARS, MIN_CHARS


def init_diagnosis_dir(workspace_root: Path, *, overwrite: bool) -> Path:
    diag_dir = workspace_root / "diagnosis"
    if diag_dir.exists():
        if not overwrite:
            raise FileExistsError(f"diagnosis already exists: {diag_dir}")
        shutil.rmtree(diag_dir)
    (diag_dir / "chunks").mkdir(parents=True, exist_ok=True)
    return diag_dir


def write_segments_plan(diag_dir: Path, segments: list[DiagnosisSegment]) -> Path:
    dest = diag_dir / "segments.json"
    payload = {
        "schema_version": "1.0",
        "min_chars": MIN_CHARS,
        "max_chars": MAX_CHARS,
        "total_segments": len(segments),
        "segments": [
            {
                "segment_index": s.segment_index,
                "char_count": s.char_count,
                "source_chunk_ids": s.source_chunk_ids,
                "section_path": s.section_path,
            }
            for s in segments
        ],
    }
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return dest


def write_segment_result(diag_dir: Path, step: SegmentStepResult) -> Path:
    dest = diag_dir / "chunks" / f"{step.segment_index:03d}_summary.json"
    payload = {
        "schema_version": "1.0",
        "segment_index": step.segment_index,
        "char_count": step.char_count,
        "source_chunk_ids": step.source_chunk_ids,
        "current_summary": step.output.current_summary,
        "total_summary": step.output.total_summary,
        "duration_ms": step.duration_ms,
        "attempt": step.attempt,
    }
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return dest


def write_run_state(diag_dir: Path, result: DiagnosisRunResult) -> Path:
    dest = diag_dir / "run_state.json"
    dest.write_text(
        json.dumps(result.to_run_state_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return dest


def write_total_summary(diag_dir: Path, total_summary: str) -> Path:
    dest = diag_dir / "total_summary.md"
    dest.write_text(total_summary, encoding="utf-8")
    return dest
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/tender_insights/unit/test_diagnosis_writer.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tender_insights/diagnosis/writer.py \
        tests/tender_insights/unit/test_diagnosis_writer.py
git commit -m "feat(diagnosis): add diagnosis workspace writer"
```

---

### Task 6: DiagnosisRunner 与 run_diagnosis

**Files:**
- Create: `src/tender_insights/diagnosis/runner.py`
- Modify: `src/tender_insights/diagnosis/__init__.py`
- Test: `tests/tender_insights/unit/test_diagnosis_runner.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tender_insights/unit/test_diagnosis_runner.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from tender_insights.diagnosis.client import InvokeStructuredResult
from tender_insights.diagnosis.models import (
    ChunkSummaryOutput,
    DiagnosisInvokeError,
    DiagnosisInvokeTimeoutError,
    DiagnosisSegment,
    DiagnosisState,
)
from tender_insights.diagnosis.runner import DiagnosisRunner


@dataclass
class FakeDiagnosisClient:
    outcomes: list[ChunkSummaryOutput | Exception] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)
    _index: int = 0

    def invoke(self, input: dict[str, Any]) -> InvokeStructuredResult:
        self.calls.append(dict(input))
        outcome = self.outcomes[self._index]
        self._index += 1
        if isinstance(outcome, Exception):
            raise outcome
        return InvokeStructuredResult(output=outcome, duration_ms=10, raw_response={"status": "completed"})


def _state_with_two_segments() -> DiagnosisState:
    segments = [
        DiagnosisSegment(1, "seg1", 4, ["c1"], []),
        DiagnosisSegment(2, "seg2", 4, ["c2"], []),
    ]
    return DiagnosisState(tender_report="report", preview_summary="", segments=segments)


def test_runner_passes_preview_summary_across_segments():
    client = FakeDiagnosisClient(
        outcomes=[
            ChunkSummaryOutput(current_summary="c1", total_summary="t1"),
            ChunkSummaryOutput(current_summary="c2", total_summary="t2"),
        ],
    )
    runner = DiagnosisRunner(client=client)
    result = runner.run(_state_with_two_segments())

    assert result.status == "completed"
    assert result.state.preview_summary == "t2"
    assert client.calls[0]["preview_summary"] == ""
    assert client.calls[1]["preview_summary"] == "t1"
    assert client.calls[1]["current_count"] == "2"
    assert client.calls[1]["total_chunk_count"] == "2"


def test_runner_retries_once_on_invoke_error():
    client = FakeDiagnosisClient(
        outcomes=[
            DiagnosisInvokeError("boom"),
            ChunkSummaryOutput(current_summary="c1", total_summary="t1"),
            ChunkSummaryOutput(current_summary="c2", total_summary="t2"),
        ],
    )
    runner = DiagnosisRunner(client=client)
    result = runner.run(_state_with_two_segments())
    assert result.status == "completed"
    assert result.step_results[0].attempt == 2


def test_runner_does_not_retry_on_timeout():
    client = FakeDiagnosisClient(
        outcomes=[DiagnosisInvokeTimeoutError("timeout", elapsed_ms=180000, configured_timeout_s=600)],
    )
    runner = DiagnosisRunner(client=client)
    result = runner.run(_state_with_two_segments())
    assert result.status == "failed"
    assert result.error_type == "timeout"
    assert result.failed_segment == 1
    assert len(client.calls) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/tender_insights/unit/test_diagnosis_runner.py -v`

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/tender_insights/diagnosis/runner.py
from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from doc_chunk.workspace.layout import OutputWorkspace

from tender_insights.diagnosis.client import (
    DiagnosisClient,
    InvokeStructuredResult,
    create_diagnosis_client_from_env,
)
from tender_insights.diagnosis.loader import load_diagnosis_inputs
from tender_insights.diagnosis.models import (
    DiagnosisInvokeError,
    DiagnosisInvokeTimeoutError,
    DiagnosisRunResult,
    DiagnosisState,
    SegmentStepResult,
)
from tender_insights.diagnosis.segment_optimizer import optimize_segments
from tender_insights.diagnosis.writer import (
    init_diagnosis_dir,
    write_run_state,
    write_segment_result,
    write_segments_plan,
    write_total_summary,
)

MAX_RETRIES = 1


class DiagnosisClientProtocol(Protocol):
    def invoke(self, input: dict) -> InvokeStructuredResult: ...


class DiagnosisRunner:
    def __init__(
        self,
        *,
        client: DiagnosisClientProtocol,
        on_progress: Callable[[str, dict], None] | None = None,
    ) -> None:
        self._client = client
        self._on_progress = on_progress

    def run(self, state: DiagnosisState) -> DiagnosisRunResult:
        result = DiagnosisRunResult(status="partial", state=state)
        total = len(state.segments)
        for segment in state.segments:
            if self._on_progress:
                self._on_progress(
                    "diagnosis",
                    {
                        "message": f"诊断分段 {segment.segment_index}/{total}",
                        "current": segment.segment_index,
                        "total": total,
                    },
                )
            last_error: Exception | None = None
            succeeded = False
            for attempt in range(MAX_RETRIES + 1):
                try:
                    invoke_result = self._client.invoke(state.to_invoke_input(segment))
                    state.apply_output(invoke_result.output)
                    result.completed_segments.append(segment.segment_index)
                    result.step_results.append(
                        SegmentStepResult(
                            segment_index=segment.segment_index,
                            output=invoke_result.output,
                            duration_ms=invoke_result.duration_ms,
                            attempt=attempt + 1,
                            char_count=segment.char_count,
                            source_chunk_ids=list(segment.source_chunk_ids),
                        )
                    )
                    succeeded = True
                    break
                except DiagnosisInvokeTimeoutError as exc:
                    return self._failed_result(
                        result,
                        segment.segment_index,
                        error_type="timeout",
                        error_message=str(exc),
                        elapsed_ms=exc.elapsed_ms,
                        configured_timeout_s=exc.configured_timeout_s,
                    )
                except DiagnosisInvokeError as exc:
                    last_error = exc
                    if attempt >= MAX_RETRIES:
                        return self._failed_result(
                            result,
                            segment.segment_index,
                            error_type="invoke_error",
                            error_message=str(exc),
                            elapsed_ms=exc.elapsed_ms,
                        )
            if not succeeded:
                return self._failed_result(
                    result,
                    segment.segment_index,
                    error_type="invoke_error",
                    error_message=str(last_error),
                )

        result.status = "completed"
        return result

    @staticmethod
    def _failed_result(
        result: DiagnosisRunResult,
        failed_segment: int,
        *,
        error_type: str,
        error_message: str,
        elapsed_ms: int | None = None,
        configured_timeout_s: int | None = None,
    ) -> DiagnosisRunResult:
        result.status = "failed" if not result.completed_segments else "partial"
        result.failed_segment = failed_segment
        result.error_type = error_type
        result.error_message = error_message
        result.elapsed_ms = elapsed_ms
        result.configured_timeout_s = configured_timeout_s
        return result


def run_diagnosis(
    workspace: OutputWorkspace,
    *,
    client: DiagnosisClient | None = None,
    on_progress: Callable[[str, dict], None] | None = None,
    overwrite: bool = False,
    timeout_s: int | None = None,
) -> DiagnosisRunResult:
    tender_report, raw_chunks = load_diagnosis_inputs(workspace)
    segments = optimize_segments(raw_chunks)
    state = DiagnosisState(tender_report=tender_report, preview_summary="", segments=segments)

    resolved_client = client
    if resolved_client is None:
        resolved_client = create_diagnosis_client_from_env()
        if timeout_s is not None:
            resolved_client = DiagnosisClient(
                base_url=resolved_client.base_url,
                api_key=resolved_client.api_key,
                timeout_s=timeout_s,
            )

    diag_dir = init_diagnosis_dir(workspace.root, overwrite=overwrite)
    write_segments_plan(diag_dir, segments)

    runner = DiagnosisRunner(client=resolved_client, on_progress=on_progress)
    result = runner.run(state)

    for step_result in result.step_results:
        write_segment_result(diag_dir, step_result)

    write_run_state(diag_dir, result)
    if result.state.preview_summary:
        write_total_summary(diag_dir, result.state.preview_summary)

    return result
```

```python
# src/tender_insights/diagnosis/__init__.py
from tender_insights.diagnosis.runner import run_diagnosis

__all__ = ["run_diagnosis"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/tender_insights/unit/test_diagnosis_runner.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tender_insights/diagnosis/runner.py \
        src/tender_insights/diagnosis/__init__.py \
        tests/tender_insights/unit/test_diagnosis_runner.py
git commit -m "feat(diagnosis): add sequential runner with retry and timeout handling"
```

---

### Task 7: API、CLI 与配置

**Files:**
- Modify: `src/tender_insights/api.py`
- Modify: `src/tender_insights/cli/main.py`
- Modify: `.env.example`
- Modify: `tests/tender_insights/unit/test_cli.py`

- [ ] **Step 1: Write the failing test**

在 `tests/tender_insights/unit/test_cli.py` 追加：

```python
def test_cli_diagnose_help() -> None:
    result = CliRunner().invoke(app, ["diagnose", "--help"])
    assert result.exit_code == 0
    assert "--overwrite" in result.stdout
    assert "--timeout" in result.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/tender_insights/unit/test_cli.py::test_cli_diagnose_help -v`

Expected: FAIL（`diagnose` 子命令不存在）

- [ ] **Step 3: Wire API + CLI + env**

在 `src/tender_insights/api.py` 追加：

```python
def run_diagnosis_job(
    workspace: OutputWorkspace,
    *,
    on_progress: Callable[[str, dict], None] | None = None,
    overwrite: bool = False,
    timeout_s: int | None = None,
):
    from tender_insights.diagnosis.runner import run_diagnosis

    return run_diagnosis(
        workspace,
        on_progress=on_progress,
        overwrite=overwrite,
        timeout_s=timeout_s,
    )
```

在 `src/tender_insights/cli/main.py` 的 import 区追加 `run_diagnosis_job`、`DiagnosisPrerequisiteError`，并追加命令：

```python
@app.command("diagnose")
def diagnose_cmd(
    path: Path = typer.Argument(..., help="已有工作区目录（须含 summary_loop/report.md 与 chunks/）"),
    overwrite: bool = typer.Option(False, "--overwrite"),
    timeout: int | None = typer.Option(None, "--timeout", help="单次 invoke 超时秒数，默认 600"),
) -> None:
    ws = _resolve_workspace(path, None, overwrite=False)
    try:
        result = run_diagnosis_job(ws, overwrite=overwrite, timeout_s=timeout)
    except DiagnosisPrerequisiteError as exc:
        raise typer.BadParameter(str(exc)) from exc

    diag_dir = ws.root / "diagnosis"
    if result.status != "completed":
        typer.echo(
            f"Diagnosis failed at segment {result.failed_segment}: {result.error_message}",
            err=True,
        )
        typer.echo(f"Partial results written to {diag_dir}")
        raise typer.Exit(code=1)
    typer.echo(f"Wrote {diag_dir / 'total_summary.md'}")
    typer.echo(f"Wrote {diag_dir / 'run_state.json'}")
```

在 `.env.example` 追加：

```
DIAGNOSIS_INVOKE_TIMEOUT_S=600
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/tender_insights/unit/test_cli.py tests/tender_insights/unit/test_diagnosis_*.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tender_insights/api.py \
        src/tender_insights/cli/main.py \
        .env.example \
        tests/tender_insights/unit/test_cli.py
git commit -m "feat(diagnosis): add diagnose CLI command and API entrypoint"
```

---

## Spec 覆盖自检

| Spec 要求 | 对应 Task |
|-----------|-----------|
| 严格前置 `report.md` + `chunks/` | Task 3, Task 7 CLI 错误映射 |
| 8000–15000 字符分段（末段豁免） | Task 2 |
| 超大 chunk 按行拆分 | Task 2 `_split_by_lines` |
| `preview_summary` 滚动传递 | Task 1 models, Task 6 runner 测试 |
| `bid_chunk_summary` structuredOutput | Task 4 |
| 超时/重试策略 | Task 4, Task 6 |
| `diagnosis/` 落盘结构 | Task 5, Task 6 |
| CLI `diagnose` | Task 7 |
| 环境变量 `DIAGNOSIS_INVOKE_TIMEOUT_S` | Task 4, Task 7 |

---

## 最终验证

Run: `cd /Users/tongqianni/xlab/tender_skills && .venv/bin/python -m pytest tests/tender_insights/unit/test_diagnosis_*.py tests/tender_insights/unit/test_cli.py -v`

Expected: 全部 PASS
