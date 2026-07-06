# Agent Platform Invoke 实现计划

> **状态：已完成（2026-07-06）** — 试点 `outline_refine` 已落地；其余 15 个 call_type 见 migrate-remaining 设计（Batch A–E）。下列 checkbox 为历史实施步骤，无需再执行。
>
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 `agent_platform` 包，提供统一的 `AgentClient.invoke()` 接口，并将 `outline_refine` 从直接 `LLMClient.complete()` 迁移为 invoke 调用，支持 `AGENT_INVOKE_MODE=local|platform` 切换且默认行为不变。

**Architecture:** `AgentClient` 委托给 `LocalBackend` 或 `PlatformBackend`；local 模式通过 `handlers/outline_refine.py` 复用现有 prompt + `LLMClient`；platform 模式 HTTP 调用 `POST /v1/apps/invoke`。`OutlineRefineEngine` 只改 invoke 入口，校验/重试逻辑不动。

**Tech Stack:** Python 3.11+、Pydantic v2、stdlib `urllib`、现有 `doc_chunk.llm`（`LLMClient` / `FakeLLMClient`）

**设计文档:** `docs/superpowers/specs/2026-07-06-agent-platform-invoke-design.md`

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `src/agent_platform/models.py` | `AgentInvokeRequest`、`AgentInvokeResult`、`AgentInvokeError` |
| `src/agent_platform/json_coerce.py` | 从 platform `output` 字符串提取 JSON object |
| `src/agent_platform/backends/base.py` | `AgentBackend` Protocol |
| `src/agent_platform/backends/local.py` | 按 call_type 分发 local handler |
| `src/agent_platform/backends/platform.py` | HTTP `POST /v1/apps/invoke` |
| `src/agent_platform/handlers/outline_refine.py` | local 模式 outline_refine prompt + LLM |
| `src/agent_platform/client.py` | `AgentClient.invoke()` |
| `src/agent_platform/factory.py` | `create_agent_client_from_env()` |
| `src/agent_platform/__init__.py` | 公共导出 |
| `src/doc_chunk/outline_refine/engine.py` | 改用 `agent_client` |
| `src/doc_chunk/api.py` | `refine_outline` 注入 `create_agent_client_from_env` |
| `tests/unit/agent_platform/test_json_coerce.py` | json_coerce 单元测试 |
| `tests/unit/agent_platform/test_local_backend.py` | LocalBackend + outline_refine handler |
| `tests/unit/agent_platform/test_platform_backend.py` | PlatformBackend HTTP mock |
| `tests/unit/agent_platform/test_factory.py` | 环境变量 mode 切换 |
| `tests/unit/test_refine_engine.py` | 改用 `AgentClient` 包装（修改） |
| `tests/integration/test_refine_cli.py` | monkeypatch 路径更新（修改） |

---

### Task 1: 核心模型与异常

**Files:**
- Create: `src/agent_platform/__init__.py`
- Create: `src/agent_platform/models.py`
- Test: `tests/unit/agent_platform/test_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/agent_platform/test_models.py
from __future__ import annotations

import pytest

from agent_platform.models import AgentInvokeError, AgentInvokeResult


def test_agent_invoke_result_fields():
    result = AgentInvokeResult(
        call_type="outline_refine",
        status="completed",
        structured_output={"change_summary": "ok"},
        text_output=None,
        raw_response={"status": "completed"},
        duration_ms=12,
    )
    assert result.call_type == "outline_refine"
    assert result.structured_output["change_summary"] == "ok"


def test_agent_invoke_error_carries_message():
    err = AgentInvokeError("platform failed")
    assert str(err) == "platform failed"
    with pytest.raises(AgentInvokeError):
        raise AgentInvokeError("boom")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/tongqianni/xlab/tender_skills && .venv/bin/python -m pytest tests/unit/agent_platform/test_models.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'agent_platform'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/agent_platform/models.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class AgentInvokeError(Exception):
    pass


@dataclass(frozen=True)
class AgentInvokeRequest:
    call_type: str
    input: dict[str, Any]


@dataclass(frozen=True)
class AgentInvokeResult:
    call_type: str
    status: str
    structured_output: dict[str, Any] | None
    text_output: str | None
    raw_response: dict[str, Any]
    duration_ms: int | None = None
```

```python
# src/agent_platform/__init__.py
from agent_platform.client import AgentClient
from agent_platform.factory import create_agent_client_from_env
from agent_platform.models import AgentInvokeError, AgentInvokeRequest, AgentInvokeResult

__all__ = [
    "AgentClient",
    "AgentInvokeError",
    "AgentInvokeRequest",
    "AgentInvokeResult",
    "create_agent_client_from_env",
]
```

（`client.py` / `factory.py` 在 Task 5/6 实现；Task 1 先只提交 `models.py`，`__init__.py` 在 Task 6 补全导出。Task 1 的 `__init__.py` 可暂留空或仅写 docstring，避免 import 失败——测试只 import models。）

Task 1 实际做法：`__init__.py` 先只包含：

```python
# src/agent_platform/__init__.py
"""Agent platform invoke client."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/agent_platform/test_models.py -v`

Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/agent_platform/__init__.py src/agent_platform/models.py tests/unit/agent_platform/test_models.py
git commit -m "feat: add agent_platform invoke models"
```

---

### Task 2: JSON coerce 工具

**Files:**
- Create: `src/agent_platform/json_coerce.py`
- Test: `tests/unit/agent_platform/test_json_coerce.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/agent_platform/test_json_coerce.py
from __future__ import annotations

from agent_platform.json_coerce import coerce_structured_output, parse_json_object


def test_parse_json_object_from_plain_json():
    assert parse_json_object('{"a": 1}') == {"a": 1}


def test_parse_json_object_from_markdown_fence():
    text = 'Here is JSON:\n```json\n{"b": 2}\n```'
    assert parse_json_object(text) == {"b": 2}


def test_parse_json_object_returns_none_for_invalid():
    assert parse_json_object("not json") is None


def test_coerce_structured_output_prefers_structured_output_key():
    resp = {"structuredOutput": {"x": 1}, "output": '{"y": 2}'}
    assert coerce_structured_output(resp) == {"x": 1}


def test_coerce_structured_output_parses_output_string():
    resp = {"output": '{"z": 3}'}
    assert coerce_structured_output(resp) == {"z": 3}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/agent_platform/test_json_coerce.py -v`

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/agent_platform/json_coerce.py
from __future__ import annotations

import json
import re
from typing import Any

_JSON_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def parse_json_object(text: str) -> dict[str, Any] | None:
    stripped = (text or "").strip()
    if not stripped:
        return None
    candidates = [stripped]
    candidates.extend(m.group(1).strip() for m in _JSON_FENCE.finditer(stripped) if m.group(1).strip())
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        candidates.append(stripped[start : end + 1])
    for candidate in candidates:
        try:
            obj = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def coerce_structured_output(resp: dict[str, Any]) -> dict[str, Any] | None:
    structured = resp.get("structuredOutput")
    if isinstance(structured, dict):
        return structured
    return parse_json_object(str(resp.get("output") or ""))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/agent_platform/test_json_coerce.py -v`

Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/agent_platform/json_coerce.py tests/unit/agent_platform/test_json_coerce.py
git commit -m "feat: add agent_platform json coerce helpers"
```

---

### Task 3: AgentBackend 协议与 AgentClient

**Files:**
- Create: `src/agent_platform/backends/__init__.py`
- Create: `src/agent_platform/backends/base.py`
- Create: `src/agent_platform/client.py`
- Test: `tests/unit/agent_platform/test_client.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/agent_platform/test_client.py
from __future__ import annotations

from typing import Any

from agent_platform.client import AgentClient
from agent_platform.models import AgentInvokeResult


class _StubBackend:
    def invoke(self, call_type: str, input: dict[str, Any]) -> AgentInvokeResult:
        return AgentInvokeResult(
            call_type=call_type,
            status="completed",
            structured_output={"echo": input.get("x")},
            text_output=None,
            raw_response={"status": "completed"},
        )


def test_agent_client_delegates_to_backend():
    client = AgentClient(_StubBackend())
    result = client.invoke("outline_refine", {"x": 1})
    assert result.call_type == "outline_refine"
    assert result.structured_output == {"echo": 1}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/agent_platform/test_client.py -v`

Expected: FAIL with `ModuleNotFoundError: agent_platform.client`

- [ ] **Step 3: Write minimal implementation**

```python
# src/agent_platform/backends/__init__.py
```

```python
# src/agent_platform/backends/base.py
from __future__ import annotations

from typing import Any, Protocol

from agent_platform.models import AgentInvokeResult


class AgentBackend(Protocol):
    def invoke(self, call_type: str, input: dict[str, Any]) -> AgentInvokeResult: ...
```

```python
# src/agent_platform/client.py
from __future__ import annotations

from typing import Any

from agent_platform.backends.base import AgentBackend
from agent_platform.models import AgentInvokeResult


class AgentClient:
    def __init__(self, backend: AgentBackend) -> None:
        self._backend = backend

    def invoke(self, call_type: str, input: dict[str, Any]) -> AgentInvokeResult:
        return self._backend.invoke(call_type, input)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/agent_platform/test_client.py -v`

Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add src/agent_platform/backends/ src/agent_platform/client.py tests/unit/agent_platform/test_client.py
git commit -m "feat: add AgentClient delegating to AgentBackend"
```

---

### Task 4: outline_refine local handler 与 LocalBackend

**Files:**
- Create: `src/agent_platform/handlers/__init__.py`
- Create: `src/agent_platform/handlers/outline_refine.py`
- Create: `src/agent_platform/backends/local.py`
- Test: `tests/unit/agent_platform/test_local_backend.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/agent_platform/test_local_backend.py
from __future__ import annotations

import json

from agent_platform.backends.local import LocalBackend
from agent_platform.client import AgentClient
from doc_chunk.llm.client import FakeLLMClient


OUTLINE_REFINE_RESPONSE = (
    '{"outline_refined":{"schema_version":"1.0","strategy":"heading_heuristic","nodes":[]},'
    '"node_mappings":[],"change_summary":"ok"}'
)


def test_local_backend_outline_refine_returns_structured_output():
    llm = FakeLLMClient(responses=[OUTLINE_REFINE_RESPONSE])
    client = AgentClient(LocalBackend(llm_client=llm))
    result = client.invoke(
        "outline_refine",
        {
            "instruction": "test",
            "original_outline": {"schema_version": "1.0", "nodes": []},
            "current_outline": {"schema_version": "1.0", "nodes": []},
        },
    )
    assert result.status == "completed"
    assert result.structured_output is not None
    assert result.structured_output["change_summary"] == "ok"
    assert len(llm.calls) == 1
    user_msg = llm.calls[0]["messages"][1]["content"]
    payload = json.loads(user_msg)
    assert payload["instruction"] == "test"


def test_local_backend_unknown_call_type_raises():
    llm = FakeLLMClient()
    backend = LocalBackend(llm_client=llm)
    try:
        backend.invoke("unknown_agent", {})
        assert False, "expected AgentInvokeError"
    except Exception as exc:
        from agent_platform.models import AgentInvokeError

        assert isinstance(exc, AgentInvokeError)
        assert "unknown_agent" in str(exc)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/agent_platform/test_local_backend.py -v`

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/agent_platform/handlers/__init__.py
```

```python
# src/agent_platform/handlers/outline_refine.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from doc_chunk.llm.client import LLMClient

from agent_platform.models import AgentInvokeError, AgentInvokeResult

_PROMPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "doc_chunk"
    / "llm"
    / "prompts"
    / "outline_refine.txt"
)


def _load_system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def invoke_outline_refine(llm_client: LLMClient, input: dict[str, Any]) -> AgentInvokeResult:
    for key in ("instruction", "original_outline", "current_outline"):
        if key not in input:
            raise AgentInvokeError(f"outline_refine input missing field: {key}")

    user_content = {
        "instruction": input["instruction"],
        "original_outline": input["original_outline"],
        "current_outline": input["current_outline"],
    }
    raw = llm_client.complete(
        [
            {"role": "system", "content": _load_system_prompt()},
            {"role": "user", "content": json.dumps(user_content, ensure_ascii=False)},
        ],
        response_format="json",
        timeout=60.0,
    )
    try:
        structured = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AgentInvokeError(f"outline_refine local handler invalid JSON: {exc}") from exc
    if not isinstance(structured, dict):
        raise AgentInvokeError("outline_refine local handler expected JSON object")

    return AgentInvokeResult(
        call_type="outline_refine",
        status="completed",
        structured_output=structured,
        text_output=None,
        raw_response={"status": "completed", "structuredOutput": structured},
    )
```

```python
# src/agent_platform/backends/local.py
from __future__ import annotations

from typing import Any, Callable

from doc_chunk.llm.client import LLMClient

from agent_platform.handlers.outline_refine import invoke_outline_refine
from agent_platform.models import AgentInvokeError, AgentInvokeResult

Handler = Callable[[LLMClient, dict[str, Any]], AgentInvokeResult]

_HANDLERS: dict[str, Handler] = {
    "outline_refine": invoke_outline_refine,
}


class LocalBackend:
    def __init__(self, *, llm_client: LLMClient) -> None:
        self._llm_client = llm_client

    def invoke(self, call_type: str, input: dict[str, Any]) -> AgentInvokeResult:
        handler = _HANDLERS.get(call_type)
        if handler is None:
            raise AgentInvokeError(f"no local handler registered for call_type: {call_type}")
        return handler(self._llm_client, input)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/agent_platform/test_local_backend.py -v`

Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/agent_platform/handlers/ src/agent_platform/backends/local.py tests/unit/agent_platform/test_local_backend.py
git commit -m "feat: add LocalBackend with outline_refine handler"
```

---

### Task 5: PlatformBackend

**Files:**
- Create: `src/agent_platform/backends/platform.py`
- Test: `tests/unit/agent_platform/test_platform_backend.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/agent_platform/test_platform_backend.py
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from agent_platform.backends.platform import PlatformBackend
from agent_platform.models import AgentInvokeError


def test_platform_backend_maps_structured_output():
    fake_resp = MagicMock()
    fake_resp.read.return_value = json.dumps(
        {
            "status": "completed",
            "structuredOutput": {"change_summary": "done"},
            "output": "",
        }
    ).encode("utf-8")
    fake_resp.__enter__ = lambda s: s
    fake_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=fake_resp):
        backend = PlatformBackend(base_url="http://localhost:8000")
        result = backend.invoke("outline_refine", {"instruction": "x"})

    assert result.status == "completed"
    assert result.structured_output == {"change_summary": "done"}
    assert result.raw_response["status"] == "completed"


def test_platform_backend_raises_on_non_completed_status():
    fake_resp = MagicMock()
    fake_resp.read.return_value = json.dumps({"status": "failed", "error": "boom"}).encode("utf-8")
    fake_resp.__enter__ = lambda s: s
    fake_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=fake_resp):
        backend = PlatformBackend(base_url="http://localhost:8000")
        try:
            backend.invoke("outline_refine", {})
            assert False, "expected AgentInvokeError"
        except AgentInvokeError as exc:
            assert "failed" in str(exc)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/agent_platform/test_platform_backend.py -v`

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/agent_platform/backends/platform.py
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from agent_platform.json_coerce import coerce_structured_output
from agent_platform.models import AgentInvokeError, AgentInvokeResult


class PlatformBackend:
    def __init__(self, *, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")

    def invoke(self, call_type: str, input: dict[str, Any]) -> AgentInvokeResult:
        url = f"{self._base_url}/v1/apps/invoke"
        body = json.dumps({"appName": call_type, "input": input}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise AgentInvokeError(f"HTTP {exc.code} POST /v1/apps/invoke: {detail}") from exc

        duration_ms = int((time.perf_counter() - started) * 1000)
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            raise AgentInvokeError(f"invalid JSON response from platform: {exc}") from exc

        if not isinstance(payload, dict):
            raise AgentInvokeError("platform response must be JSON object")

        status = str(payload.get("status") or "")
        if status != "completed":
            raise AgentInvokeError(f"invoke not completed for {call_type}: {payload}")

        structured = coerce_structured_output(payload)
        text_output = payload.get("output")
        if not isinstance(text_output, str):
            text_output = None
        elif structured is not None:
            text_output = None

        return AgentInvokeResult(
            call_type=call_type,
            status=status,
            structured_output=structured,
            text_output=text_output,
            raw_response=payload,
            duration_ms=duration_ms,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/agent_platform/test_platform_backend.py -v`

Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/agent_platform/backends/platform.py tests/unit/agent_platform/test_platform_backend.py
git commit -m "feat: add PlatformBackend for /v1/apps/invoke"
```

---

### Task 6: Factory 与环境变量

**Files:**
- Create: `src/agent_platform/factory.py`
- Modify: `src/agent_platform/__init__.py`
- Test: `tests/unit/agent_platform/test_factory.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/agent_platform/test_factory.py
from __future__ import annotations

import pytest

from agent_platform.backends.local import LocalBackend
from agent_platform.backends.platform import PlatformBackend
from agent_platform.factory import create_agent_client_from_env
from doc_chunk.llm.client import FakeLLMClient


def test_factory_defaults_to_local_backend(monkeypatch):
    monkeypatch.delenv("AGENT_INVOKE_MODE", raising=False)
    fake = FakeLLMClient(default_response="{}")
    client = create_agent_client_from_env(llm_client=fake)
    backend = client._backend  # noqa: SLF001 - test inspects wiring
    assert isinstance(backend, LocalBackend)


def test_factory_platform_mode(monkeypatch):
    monkeypatch.setenv("AGENT_INVOKE_MODE", "platform")
    monkeypatch.setenv("AGENT_PLATFORM_BASE_URL", "http://127.0.0.1:8000")
    client = create_agent_client_from_env()
    backend = client._backend  # noqa: SLF001
    assert isinstance(backend, PlatformBackend)
    assert backend._base_url == "http://127.0.0.1:8000"  # noqa: SLF001


def test_factory_rejects_unknown_mode(monkeypatch):
    monkeypatch.setenv("AGENT_INVOKE_MODE", "hybrid")
    with pytest.raises(ValueError, match="unsupported AGENT_INVOKE_MODE"):
        create_agent_client_from_env(llm_client=FakeLLMClient())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/agent_platform/test_factory.py -v`

Expected: FAIL with `ModuleNotFoundError: agent_platform.factory`

- [ ] **Step 3: Write minimal implementation**

```python
# src/agent_platform/factory.py
from __future__ import annotations

import os

from doc_chunk.llm.client import LLMClient
from doc_chunk.llm.openai_client import create_llm_client_from_env

from agent_platform.backends.local import LocalBackend
from agent_platform.backends.platform import PlatformBackend
from agent_platform.client import AgentClient


def create_agent_client_from_env(*, llm_client: LLMClient | None = None) -> AgentClient:
    mode = os.environ.get("AGENT_INVOKE_MODE", "local").strip().lower()
    if mode == "platform":
        base_url = os.environ.get("AGENT_PLATFORM_BASE_URL", "http://localhost:8000")
        return AgentClient(PlatformBackend(base_url=base_url))
    if mode != "local":
        raise ValueError(f"unsupported AGENT_INVOKE_MODE: {mode}")
    client = llm_client or create_llm_client_from_env()
    return AgentClient(LocalBackend(llm_client=client))
```

更新 `src/agent_platform/__init__.py`：

```python
from agent_platform.client import AgentClient
from agent_platform.factory import create_agent_client_from_env
from agent_platform.models import AgentInvokeError, AgentInvokeRequest, AgentInvokeResult

__all__ = [
    "AgentClient",
    "AgentInvokeError",
    "AgentInvokeRequest",
    "AgentInvokeResult",
    "create_agent_client_from_env",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/agent_platform/test_factory.py -v`

Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/agent_platform/factory.py src/agent_platform/__init__.py tests/unit/agent_platform/test_factory.py
git commit -m "feat: add create_agent_client_from_env factory"
```

---

### Task 7: 迁移 OutlineRefineEngine

**Files:**
- Modify: `src/doc_chunk/outline_refine/engine.py`
- Test: `tests/unit/test_refine_engine.py`

- [ ] **Step 1: Write the failing test（更新现有测试）**

将 `tests/unit/test_refine_engine.py` 全文替换为：

```python
from __future__ import annotations

from pathlib import Path

import pytest

from agent_platform.backends.local import LocalBackend
from agent_platform.client import AgentClient
from doc_chunk.errors import ValidationError
from doc_chunk.llm.client import FakeLLMClient
from doc_chunk.models.outline import Anchor, OutlineNode, OutlineTree
from doc_chunk.outline_refine.engine import OutlineRefineEngine
from doc_chunk.outline_refine.session import RefineSession


def _session(tmp_path: Path) -> RefineSession:
    original = OutlineTree(
        strategy="heading_heuristic",
        nodes=[
            OutlineNode(
                node_id="n1",
                title="第一章",
                level=1,
                parent_id=None,
                sort_order=0,
                anchor=Anchor(block_index=0),
            )
        ],
    )
    return RefineSession(workspace=tmp_path / "ws", original_outline=original)


def _agent_client(responses: list[str]) -> AgentClient:
    llm = FakeLLMClient(responses=responses)
    return AgentClient(LocalBackend(llm_client=llm))


def test_refine_engine_runs_with_fake_llm(tmp_path: Path) -> None:
    client = _agent_client(
        [
            (
                '{"outline_refined":{"schema_version":"1.0","strategy":"heading_heuristic","nodes":[{"node_id":"r1",'
                '"title":"合并章节","level":1,"parent_id":null,"sort_order":0,"anchor":{"block_index":0},"needs_review":false,'
                '"source_refs":["n1"]}],"derived_from":null,"accepted_at":null},'
                '"node_mappings":[{"refined_node_id":"r1","source_node_ids":["n1"],"markdown_range":{"char_start":0,"char_end":10},"operation":"rename"}],'
                '"change_summary":"重命名第一章"}'
            )
        ]
    )
    engine = OutlineRefineEngine(agent_client=client, strict=True, max_retries=2)
    refined, mapping, summary, preview = engine.run_round(session=_session(tmp_path), instruction="重命名")
    assert refined.nodes[0].title == "合并章节"
    assert mapping.mappings[0].refined_node_id == "r1"
    assert summary == "重命名第一章"
    assert preview.validation_passed is True


def test_refine_engine_retries_and_fails_after_max(tmp_path: Path) -> None:
    llm = FakeLLMClient(responses=["not-json", "still-not-json", "again"])
    client = AgentClient(LocalBackend(llm_client=llm))
    engine = OutlineRefineEngine(agent_client=client, strict=True, max_retries=2)
    with pytest.raises(ValidationError):
        engine.run_round(session=_session(tmp_path), instruction="重命名")
    assert len(llm.calls) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_refine_engine.py -v`

Expected: FAIL — `OutlineRefineEngine.__init__() got an unexpected keyword argument 'agent_client'`

- [ ] **Step 3: Write minimal implementation**

将 `src/doc_chunk/outline_refine/engine.py` 全文替换为：

```python
from __future__ import annotations

from agent_platform.client import AgentClient
from agent_platform.models import AgentInvokeError

from doc_chunk.errors import ValidationError
from doc_chunk.models.outline import OutlineMappingFile, OutlineTree, RefinePreview
from doc_chunk.outline_refine.preview import build_preview
from doc_chunk.outline_refine.session import RefineSession
from doc_chunk.outline_refine.validator import OutlineMappingValidator


class OutlineRefineEngine:
    def __init__(self, *, agent_client: AgentClient, strict: bool = True, max_retries: int = 2) -> None:
        self.agent_client = agent_client
        self.max_retries = max_retries
        self.validator = OutlineMappingValidator(strict=strict)

    def run_round(
        self,
        *,
        session: RefineSession,
        instruction: str,
    ) -> tuple[OutlineTree, OutlineMappingFile, str, RefinePreview]:
        last_errors: list[str] = []
        base_outline = session.base_outline()
        original_outline = session.original_outline

        for _ in range(self.max_retries + 1):
            try:
                result = self.agent_client.invoke(
                    "outline_refine",
                    {
                        "instruction": instruction,
                        "original_outline": original_outline.model_dump(mode="json"),
                        "current_outline": base_outline.model_dump(mode="json"),
                    },
                )
            except AgentInvokeError as exc:
                last_errors = [str(exc)]
                continue

            payload = result.structured_output
            if not isinstance(payload, dict):
                last_errors = ["LLM response missing structured output"]
                continue

            outline_raw = payload.get("outline_refined")
            mapping_raw = payload.get("node_mappings")
            summary = str(payload.get("change_summary", "")).strip() or "no summary"
            if not isinstance(outline_raw, dict) or not isinstance(mapping_raw, list):
                last_errors = ["LLM response missing outline_refined or node_mappings"]
                continue

            try:
                refined = OutlineTree.model_validate(outline_raw)
                mapping = OutlineMappingFile.model_validate({"mappings": mapping_raw})
            except Exception as exc:
                last_errors = [f"invalid payload schema: {exc}"]
                continue

            validation = self.validator.validate(
                original_outline=original_outline,
                refined_outline=refined,
                mapping=mapping,
            )
            preview = build_preview(
                before_titles=[node.title for node in base_outline.nodes],
                after_titles=[node.title for node in refined.nodes],
                change_summary=summary,
                warnings=validation.warnings,
                validation_errors=validation.errors,
            )
            if validation.passed:
                return refined, mapping, summary, preview
            last_errors = validation.errors

        raise ValidationError("; ".join(last_errors) if last_errors else "outline refinement failed")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/test_refine_engine.py -v`

Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/doc_chunk/outline_refine/engine.py tests/unit/test_refine_engine.py
git commit -m "feat: migrate OutlineRefineEngine to AgentClient invoke"
```

---

### Task 8: 更新 refine_outline API 与集成测试

**Files:**
- Modify: `src/doc_chunk/api.py:255-274`
- Modify: `tests/integration/test_refine_cli.py:66-79`

- [ ] **Step 1: 修改 api.py**

在 `src/doc_chunk/api.py` 顶部增加 import：

```python
from agent_platform.factory import create_agent_client_from_env
```

将 `refine_outline` 中 LLM 客户端段：

```python
    client = llm_client
    if client is None:
        client = create_llm_client_from_env()

    engine = OutlineRefineEngine(llm_client=client, strict=strict, max_retries=2)
```

替换为：

```python
    agent_client = create_agent_client_from_env(llm_client=llm_client)

    engine = OutlineRefineEngine(agent_client=agent_client, strict=strict, max_retries=2)
```

保留函数签名中的 `llm_client: LLMClient | None = None` 不变（供测试注入 FakeLLMClient）。

- [ ] **Step 2: 更新 integration test monkeypatch 路径**

在 `tests/integration/test_refine_cli.py` 将：

```python
    monkeypatch.setattr(
        "doc_chunk.api.create_llm_client_from_env",
        lambda: __import__(...).FakeLLMClient(...)
    )
```

替换为：

```python
    monkeypatch.setattr(
        "doc_chunk.llm.openai_client.create_llm_client_from_env",
        lambda: __import__("doc_chunk.llm.client", fromlist=["FakeLLMClient"]).FakeLLMClient(
            responses=[
                (
                    '{"outline_refined":{"schema_version":"1.0","strategy":"heading_heuristic","nodes":[{"node_id":"r1",'
                    '"title":"优化第一章","level":1,"parent_id":null,"sort_order":0,"anchor":{"block_index":0},"needs_review":false,"source_refs":["n1"]}],'
                    '"derived_from":null,"accepted_at":null},"node_mappings":[{"refined_node_id":"r1","source_node_ids":["n1"],'
                    '"markdown_range":{"char_start":0,"char_end":8},"operation":"rename"}],"change_summary":"重命名章节"}'
                )
            ]
        ),
    )
```

（factory 在 `llm_client=None` 时调用 `doc_chunk.llm.openai_client.create_llm_client_from_env`，故 patch 此路径。）

- [ ] **Step 3: Run tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/test_refine_engine.py tests/integration/test_refine_cli.py tests/unit/agent_platform/ -v
```

Expected: 全部 PASS

- [ ] **Step 4: Run broader regression（doc_chunk 相关）**

Run:

```bash
.venv/bin/python -m pytest tests/unit/test_refine_engine.py tests/unit/test_refine_validator.py tests/integration/test_refine_cli.py tests/unit/agent_platform/ -v
```

Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add src/doc_chunk/api.py tests/integration/test_refine_cli.py
git commit -m "feat: wire refine_outline to create_agent_client_from_env"
```

---

### Task 9: 全量 agent_platform 测试与 spec 验收

**Files:**
- Modify: `docs/superpowers/specs/2026-07-06-agent-platform-invoke-design.md`（状态行）

- [ ] **Step 1: Run full agent_platform + refine test suite**

Run:

```bash
.venv/bin/python -m pytest tests/unit/agent_platform/ tests/unit/test_refine_engine.py tests/integration/test_refine_cli.py -v
```

Expected: 全部 PASS

- [ ] **Step 2: 确认 engine 无直接 LLM 调用**

Run:

```bash
rg "llm_client\.complete" src/doc_chunk/outline_refine/engine.py
```

Expected: 无匹配

- [ ] **Step 3: 更新设计文档状态**

将 `docs/superpowers/specs/2026-07-06-agent-platform-invoke-design.md` 第 4 行改为：

```markdown
> 状态：已实现（2026-07-06）
```

将 §11 验收标准 checkbox 全部改为 `[x]`。

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-07-06-agent-platform-invoke-design.md
git commit -m "docs: mark agent platform invoke design as implemented"
```

- [ ] **Step 5: （可选）platform 模式手动验证**

前置：df-agent-os-python 在 `localhost:8000` 运行，且已 provision `outline_refine`。

Run:

```bash
AGENT_INVOKE_MODE=platform .venv/bin/python -m pytest tests/unit/test_refine_engine.py -v -k "runs_with_fake"
```

Expected: 此测试仍用 LocalBackend 注入，应 PASS（不依赖平台）。

手动冒烟：

```bash
AGENT_INVOKE_MODE=platform .venv/bin/python -c "
from agent_platform.factory import create_agent_client_from_env
c = create_agent_client_from_env()
r = c.invoke('outline_refine', {
  'instruction': '重命名第一章',
  'original_outline': {'schema_version':'1.0','strategy':'heading_heuristic','nodes':[{'node_id':'n1','title':'第一章','level':1,'parent_id':None,'sort_order':0,'anchor':{'block_index':0},'needs_review':False,'source_refs':[]}]},
  'current_outline': {'schema_version':'1.0','strategy':'heading_heuristic','nodes':[{'node_id':'n1','title':'第一章','level':1,'parent_id':None,'sort_order':0,'anchor':{'block_index':0},'needs_review':False,'source_refs':[]}]},
})
print(r.status, r.structured_output is not None)
"
```

Expected: `completed True`

---

## Spec 覆盖自检

| 设计 § | 对应 Task |
|--------|-----------|
| §3 包结构 | Task 1–6 |
| §4 请求/响应格式 | Task 1, 3 |
| §5.1 LocalBackend + outline_refine handler | Task 4 |
| §5.2 PlatformBackend | Task 5 |
| §5.3 Factory + 环境变量 | Task 6 |
| §6 outline_refine 试点改动 | Task 7, 8 |
| §7 错误处理 | Task 4–5（AgentInvokeError）, Task 7（engine retry） |
| §8 测试策略 | Task 2–9 |
| §11 验收标准 | Task 9 |

无 placeholder；类型名 `AgentInvokeResult` / `AgentClient` / `create_agent_client_from_env` 全文一致。

---

## 平台集成验证（非 CI 阻塞）

CI 默认 `AGENT_INVOKE_MODE=local`，不依赖 df-agent-os。platform 模式验证见 Task 9 Step 5。
