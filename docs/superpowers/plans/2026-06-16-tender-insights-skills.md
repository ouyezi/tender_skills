# tender_insights 招标语义分析 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `doc_chunk` 工作区之上新建 `tender_insights` Python 包与四个 Cursor Skills，实现招标文件解读（废标/得分/风险/目录）、模版提取、法务审核，输出稳定 JSON。

**Architecture:** 独立包 `src/tender_insights/`，共享 `common/`（工作区解析、章节路由、锚点回填、LLM 封装、manifest 写入）；`interpret`/`template`/`legal` 三模块逻辑与产出完全独立；Skills 薄封装 CLI/API。输入支持工作区或原始文件（自动 `doc_chunk.run_pipeline`）。

**Tech Stack:** Python 3.11+, pydantic v2, typer, pyyaml, doc_chunk (editable), pytest, jsonschema, openai-compatible LLM

**设计来源:** [`docs/superpowers/specs/2026-06-16-tender-insights-skills-design.md`](../specs/2026-06-16-tender-insights-skills-design.md)

**Worktree / 分支:** `005-tender-insights-skills`（实现前从 `main` 创建）

---

## File Structure

```text
pyproject.toml                          # 追加 tender-insights console script
src/tender_insights/
├── __init__.py
├── api.py                              # skills 稳定入口
├── config.py
├── errors.py
├── cli/main.py                         # interpret | template | legal | all
├── common/
│   ├── workspace_resolver.py
│   ├── section_router.py
│   ├── anchor_backfill.py
│   ├── llm_extractor.py
│   └── output_writer.py
├── interpret/
│   ├── models.py
│   ├── routing.yaml
│   ├── prompts.py
│   ├── merger.py
│   └── extractor.py
├── template/
│   ├── models.py
│   ├── detector.py
│   ├── boundary.py
│   ├── classifier.py
│   └── extractor.py
└── legal/
    ├── models.py
    ├── routing.yaml
    ├── prompts.py
    └── extractor.py
tests/tender_insights/
├── conftest.py
├── unit/
│   ├── test_import.py
│   ├── test_workspace_resolver.py
│   ├── test_anchor_backfill.py
│   ├── test_section_router.py
│   ├── test_interpret_models.py
│   ├── test_interpret_merger.py
│   ├── test_template_detector.py
│   └── test_legal_models.py
├── contract/
│   ├── test_interpretation_schema.py
│   ├── test_legal_review_schema.py
│   └── test_templates_index_schema.py
└── integration/
    └── test_pipeline_interpret.py
.cursor/skills/
├── tender-extract/SKILL.md
├── tender-interpret/SKILL.md
├── tender-template/SKILL.md
└── tender-legal-review/SKILL.md
```

---

### Task 0: 创建 worktree 分支

**Files:**（无代码变更）

- [ ] **Step 1: 从 main 创建分支 worktree**

```bash
cd /Users/tongqianni/xlab/tender_skills
git fetch origin
git worktree add ../tender_skills-005 005-tender-insights-skills -b 005-tender-insights-skills
cd ../tender_skills-005
```

Expected: 新目录 `../tender_skills-005` 在分支 `005-tender-insights-skills`

- [ ] **Step 2: 验证环境**

```bash
source .venv/bin/activate  # 或 python -m venv .venv && pip install -e ".[dev]"
python -m pytest tests/ -q --co -q | head -5
```

Expected: 收集到现有 doc_chunk 测试

---

### Task 1: tender_insights 包脚手架

**Files:**
- Modify: `pyproject.toml`
- Create: `src/tender_insights/__init__.py`
- Create: `src/tender_insights/errors.py`
- Create: `tests/tender_insights/unit/test_import.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tender_insights/unit/test_import.py
def test_package_importable():
    import tender_insights
    assert tender_insights.__version__ == "0.1.0"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/tender_insights/unit/test_import.py -v
```

Expected: FAIL `ModuleNotFoundError: No module named 'tender_insights'`

- [ ] **Step 3: Write minimal implementation**

在 `pyproject.toml` 的 `[project.scripts]` 追加：

```toml
tender-insights = "tender_insights.cli.main:app"
```

```python
# src/tender_insights/__init__.py
__version__ = "0.1.0"
```

```python
# src/tender_insights/errors.py
from __future__ import annotations


class TenderInsightsError(Exception):
    """Base error for tender_insights."""


class WorkspaceResolveError(TenderInsightsError):
    pass


class AnalysisError(TenderInsightsError):
    pass


class LLMExtractionError(AnalysisError):
    pass
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pip install -e ".[dev]"
python -m pytest tests/tender_insights/unit/test_import.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/tender_insights/__init__.py src/tender_insights/errors.py tests/tender_insights/unit/test_import.py
git commit -m "chore: scaffold tender_insights package"
```

---

### Task 2: WorkspaceResolver

**Files:**
- Create: `src/tender_insights/common/workspace_resolver.py`
- Create: `tests/tender_insights/unit/test_workspace_resolver.py`
- Create: `tests/tender_insights/conftest.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tender_insights/conftest.py
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from docx import Document


@pytest.fixture
def sample_docx(tmp_path: Path) -> Path:
    path = tmp_path / "bid.docx"
    doc = Document()
    doc.add_heading("投标人须知", level=1)
    doc.add_paragraph("废标条款示例：未按规定递交投标文件。")
    doc.save(path)
    return path


@pytest.fixture
def sample_workspace(tmp_path: Path, sample_docx: Path) -> Path:
    from doc_chunk.api import run_pipeline
    ws = tmp_path / "ws"
    run_pipeline(sample_docx, ws, overwrite=True, skip_refine=True, skip_enrich=True)
    return ws
```

```python
# tests/tender_insights/unit/test_workspace_resolver.py
from __future__ import annotations

from pathlib import Path

import pytest
from doc_chunk.workspace.layout import OutputWorkspace

from tender_insights.common.workspace_resolver import resolve_workspace
from tender_insights.errors import WorkspaceResolveError


def test_resolve_existing_workspace(sample_workspace: Path) -> None:
    ws = resolve_workspace(sample_workspace)
    assert isinstance(ws, OutputWorkspace)
    assert ws.content_path.exists()


def test_resolve_raw_file_creates_workspace(sample_docx: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    ws = resolve_workspace(sample_docx, output_dir=out, overwrite=True)
    assert ws.content_path.exists()
    assert ws.manifest_path.exists()


def test_resolve_raw_file_requires_output_dir(sample_docx: Path) -> None:
    with pytest.raises(WorkspaceResolveError, match="output_dir"):
        resolve_workspace(sample_docx)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/tender_insights/unit/test_workspace_resolver.py -v
```

Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/tender_insights/common/workspace_resolver.py
from __future__ import annotations

from pathlib import Path

from doc_chunk.api import run_pipeline
from doc_chunk.workspace.layout import OutputWorkspace

from tender_insights.errors import WorkspaceResolveError


def _is_workspace(path: Path) -> bool:
    return path.is_dir() and (path / "manifest.json").is_file() and (path / "content.md").is_file()


def resolve_workspace(
    path: Path,
    *,
    output_dir: Path | None = None,
    overwrite: bool = False,
) -> OutputWorkspace:
    path = Path(path)
    if _is_workspace(path):
        return OutputWorkspace.open_existing(path)

    if not path.is_file():
        raise WorkspaceResolveError(f"Path is neither workspace nor file: {path}")

    if output_dir is None:
        raise WorkspaceResolveError("output_dir is required when input is a raw document file")

    out = Path(output_dir)
    result = run_pipeline(path, out, overwrite=overwrite, skip_refine=True, skip_enrich=False)
    if result.status not in {"success", "partial"}:
        raise WorkspaceResolveError(f"doc_chunk pipeline failed: {result.status}")
    return OutputWorkspace.open_existing(out)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/tender_insights/unit/test_workspace_resolver.py -v
```

Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/tender_insights/common/workspace_resolver.py tests/tender_insights/conftest.py tests/tender_insights/unit/test_workspace_resolver.py
git commit -m "feat(tender_insights): add WorkspaceResolver with auto pipeline"
```

---

### Task 3: AnchorBackfill

**Files:**
- Create: `src/tender_insights/common/anchor_backfill.py`
- Create: `tests/tender_insights/unit/test_anchor_backfill.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tender_insights/unit/test_anchor_backfill.py
from tender_insights.common.anchor_backfill import backfill_char_range


CONTENT = "前言\n\n# 第一章\n\n投标人须具备资质。\n\n# 第二章\n\n其他内容。"


def test_backfill_exact_excerpt() -> None:
    excerpt = "投标人须具备资质。"
    start, end = backfill_char_range(CONTENT, excerpt)
    assert start is not None
    assert CONTENT[start:end] == excerpt


def test_backfill_missing_returns_none() -> None:
    start, end = backfill_char_range(CONTENT, "完全不存在的句子")
    assert start is None
    assert end is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/tender_insights/unit/test_anchor_backfill.py -v
```

Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# src/tender_insights/common/anchor_backfill.py
from __future__ import annotations


def _normalize_ws(text: str) -> str:
    return " ".join(text.split())


def backfill_char_range(content_md: str, excerpt: str) -> tuple[int | None, int | None]:
    if not excerpt or not excerpt.strip():
        return None, None

    idx = content_md.find(excerpt)
    if idx >= 0:
        return idx, idx + len(excerpt)

    norm_content = _normalize_ws(content_md)
    norm_excerpt = _normalize_ws(excerpt)
    if not norm_excerpt:
        return None, None

    # 滑动窗口：在归一化文本中找最长匹配子串对应的原位置近似
    best_len = 0
    best_start: int | None = None
    words = excerpt.strip()
    for length in range(len(words), max(8, len(words) // 3), -1):
        candidate = words[:length]
        pos = content_md.find(candidate)
        if pos >= 0 and length > best_len:
            best_len = length
            best_start = pos
            break

    if best_start is not None:
        return best_start, best_start + best_len

    norm_pos = norm_content.find(norm_excerpt[: min(40, len(norm_excerpt))])
    if norm_pos >= 0:
        # 兜底：无法在原文精确定位时返回 None
        return None, None

    return None, None
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/tender_insights/unit/test_anchor_backfill.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tender_insights/common/anchor_backfill.py tests/tender_insights/unit/test_anchor_backfill.py
git commit -m "feat(tender_insights): add anchor backfill for source excerpts"
```

---

### Task 4: SectionRouter

**Files:**
- Create: `src/tender_insights/common/section_router.py`
- Create: `src/tender_insights/interpret/routing.yaml`
- Create: `tests/tender_insights/unit/test_section_router.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tender_insights/unit/test_section_router.py
from doc_chunk.models.outline import OutlineNode, OutlineTree

from tender_insights.common.section_router import SectionRouter, load_routing_rules


def test_route_nodes_by_keyword() -> None:
    tree = OutlineTree(
        nodes=[
            OutlineNode(node_id="n1", title="投标人须知", level=1, parent_id=None, sort_order=0),
            OutlineNode(node_id="n2", title="评标办法", level=1, parent_id=None, sort_order=1),
            OutlineNode(node_id="n3", title="附件：承诺书", level=1, parent_id=None, sort_order=2),
        ]
    )
    rules = {
        "disqualification": {"keywords": ["须知", "废标"]},
        "scoring": {"keywords": ["评标"]},
        "template": {"keywords": ["附件", "承诺书"]},
    }
    router = SectionRouter(rules)
    dq = router.match_nodes(tree, "disqualification")
    assert [n.node_id for n in dq] == ["n1"]
    sc = router.match_nodes(tree, "scoring")
    assert [n.node_id for n in sc] == ["n2"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/tender_insights/unit/test_section_router.py -v
```

Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```yaml
# src/tender_insights/interpret/routing.yaml
disqualification:
  keywords: ["投标人须知", "废标", "否决", "无效投标"]
scoring:
  keywords: ["评标", "评分", "分值", "评审办法"]
bid_risk:
  keywords: ["须知", "资格", "符合性", "实质性"]
directory:
  keywords: ["投标文件格式", "文件组成", "目录", "编制要求"]
```

```python
# src/tender_insights/common/section_router.py
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from doc_chunk.models.outline import OutlineNode, OutlineTree


def load_routing_rules(path: Path) -> dict[str, dict[str, list[str]]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data


class SectionRouter:
    def __init__(self, rules: dict[str, dict[str, list[str]]]) -> None:
        self._rules = rules

    def match_nodes(self, outline: OutlineTree, route_key: str) -> list[OutlineNode]:
        keywords = self._rules.get(route_key, {}).get("keywords", [])
        if not keywords:
            return []
        matched: list[OutlineNode] = []
        for node in outline.nodes:
            title = node.title
            if any(kw in title for kw in keywords):
                matched.append(node)
        return sorted(matched, key=lambda n: n.sort_order)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/tender_insights/unit/test_section_router.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tender_insights/common/section_router.py src/tender_insights/interpret/routing.yaml tests/tender_insights/unit/test_section_router.py
git commit -m "feat(tender_insights): add SectionRouter with interpret routing rules"
```

---

### Task 5: OutputWriter + LLMExtractor

**Files:**
- Create: `src/tender_insights/common/output_writer.py`
- Create: `src/tender_insights/common/llm_extractor.py`
- Create: `src/tender_insights/config.py`

- [ ] **Step 1: Write config**

```python
# src/tender_insights/config.py
from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True, slots=True)
class InsightsConfig:
    llm_model: str = "gpt-4o-mini"
    max_retries: int = 2
    chunks_per_batch: int = 3

    @classmethod
    def from_env(cls) -> InsightsConfig:
        return cls(
            llm_model=os.environ.get("DOC_CHUNK_LLM_MODEL", "gpt-4o-mini"),
        )
```

- [ ] **Step 2: Write OutputWriter**

```python
# src/tender_insights/common/output_writer.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from doc_chunk.models.manifest import StageStatus
from doc_chunk.workspace.layout import OutputWorkspace
from doc_chunk.workspace.manifest_io import load_manifest, save_manifest


def write_json_artifact(
    workspace: OutputWorkspace,
    filename: str,
    payload: dict[str, Any],
    *,
    stage_name: str,
    output_key: str,
) -> Path:
    path = workspace.root / filename
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if workspace.manifest_path.exists():
        manifest = load_manifest(workspace.manifest_path)
        manifest.stages[stage_name] = StageStatus(status="success")
        manifest.outputs[output_key] = filename
        save_manifest(workspace, manifest)
    return path
```

- [ ] **Step 3: Write LLMExtractor**

```python
# src/tender_insights/common/llm_extractor.py
from __future__ import annotations

import json
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from doc_chunk.llm.client import LLMClient
from tender_insights.errors import LLMExtractionError

T = TypeVar("T", bound=BaseModel)


def extract_json_model(
    client: LLMClient,
    messages: list[dict[str, str]],
    model_type: type[T],
    *,
    max_retries: int = 2,
) -> T:
    last_error: Exception | None = None
    for _ in range(max_retries + 1):
        raw = client.complete(messages, response_format="json")
        try:
            data = json.loads(raw)
            return model_type.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as exc:
            last_error = exc
            messages = messages + [
                {"role": "user", "content": f"Previous JSON invalid: {exc}. Return valid JSON only."},
            ]
    raise LLMExtractionError(f"LLM JSON extraction failed after retries: {last_error}")
```

- [ ] **Step 4: Commit**

```bash
git add src/tender_insights/config.py src/tender_insights/common/output_writer.py src/tender_insights/common/llm_extractor.py
git commit -m "feat(tender_insights): add config, OutputWriter, and LLMExtractor"
```

---

### Task 6: Interpret 数据模型

**Files:**
- Create: `src/tender_insights/interpret/models.py`
- Create: `tests/tender_insights/unit/test_interpret_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tender_insights/unit/test_interpret_models.py
from tender_insights.interpret.models import (
    BidRiskItem,
    DirectoryRequirement,
    DisqualificationItem,
    InterpretationFile,
    ScoringItem,
    Severity,
)


def test_interpretation_file_roundtrip() -> None:
    payload = InterpretationFile(
        source_workspace="/tmp/ws",
        disqualification_items=[
            DisqualificationItem(
                id="dq-001",
                title="未递交文件",
                summary="未按时递交",
                trigger_condition="逾期递交",
                source_excerpt="逾期递交作废",
                section_path=["须知"],
                confidence=0.9,
            )
        ],
        scoring_items=[
            ScoringItem(
                id="sc-001",
                title="技术分",
                summary="技术评分",
                max_score=30.0,
                weight="30%",
                criteria="方案完整性",
                source_excerpt="技术30分",
                section_path=["评标"],
                confidence=0.85,
            )
        ],
        bid_risk_items=[
            BidRiskItem(
                id="br-001",
                title="资质风险",
                summary="资质不足",
                severity=Severity.high,
                risk_category="资质",
                source_excerpt="须具备一级资质",
                section_path=["须知"],
                confidence=0.8,
            )
        ],
        directory_requirements=[
            DirectoryRequirement(
                id="dr-001",
                title="文件组成",
                required_sections=["投标函", "资质证明"],
                mandatory=True,
                source_excerpt="投标文件包括...",
                section_path=["格式"],
                confidence=0.9,
            )
        ],
    )
    restored = InterpretationFile.model_validate_json(payload.model_dump_json())
    assert restored.disqualification_items[0].id == "dq-001"
    assert restored.scoring_items[0].max_score == 30.0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/tender_insights/unit/test_interpret_models.py -v
```

Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# src/tender_insights/interpret/models.py
from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class Severity(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class DisqualificationItem(BaseModel):
    id: str
    title: str
    summary: str
    trigger_condition: str
    source_excerpt: str
    section_path: list[str]
    char_start: int | None = None
    char_end: int | None = None
    confidence: float = Field(ge=0.0, le=1.0)


class ScoringItem(BaseModel):
    id: str
    title: str
    summary: str
    max_score: float | None = None
    weight: str | None = None
    criteria: str
    source_excerpt: str
    section_path: list[str]
    char_start: int | None = None
    char_end: int | None = None
    confidence: float = Field(ge=0.0, le=1.0)


class BidRiskItem(BaseModel):
    id: str
    title: str
    summary: str
    severity: Severity
    risk_category: str
    source_excerpt: str
    section_path: list[str]
    char_start: int | None = None
    char_end: int | None = None
    confidence: float = Field(ge=0.0, le=1.0)


class DirectoryRequirement(BaseModel):
    id: str
    title: str
    required_sections: list[str]
    mandatory: bool
    source_excerpt: str
    section_path: list[str]
    char_start: int | None = None
    char_end: int | None = None
    confidence: float = Field(ge=0.0, le=1.0)


class InterpretationLLMResponse(BaseModel):
    disqualification_items: list[DisqualificationItem] = Field(default_factory=list)
    scoring_items: list[ScoringItem] = Field(default_factory=list)
    bid_risk_items: list[BidRiskItem] = Field(default_factory=list)
    directory_requirements: list[DirectoryRequirement] = Field(default_factory=list)


class InterpretationFile(InterpretationLLMResponse):
    schema_version: Literal["1.0"] = "1.0"
    source_workspace: str
    analyzed_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/tender_insights/unit/test_interpret_models.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tender_insights/interpret/models.py tests/tender_insights/unit/test_interpret_models.py
git commit -m "feat(tender_insights): add interpret Pydantic models"
```

---

### Task 7: Interpret merger + prompts + extractor

**Files:**
- Create: `src/tender_insights/interpret/merger.py`
- Create: `src/tender_insights/interpret/prompts.py`
- Create: `src/tender_insights/interpret/extractor.py`
- Create: `tests/tender_insights/unit/test_interpret_merger.py`

- [ ] **Step 1: Write merger test**

```python
# tests/tender_insights/unit/test_interpret_merger.py
from tender_insights.interpret.merger import dedupe_by_title
from tender_insights.interpret.models import DisqualificationItem


def test_dedupe_by_title_keeps_higher_confidence() -> None:
    items = [
        DisqualificationItem(
            id="dq-001", title="逾期", summary="a", trigger_condition="t",
            source_excerpt="x", section_path=[], confidence=0.5,
        ),
        DisqualificationItem(
            id="dq-002", title="逾期", summary="b", trigger_condition="t",
            source_excerpt="y", section_path=[], confidence=0.9,
        ),
    ]
    out = dedupe_by_title(items)
    assert len(out) == 1
    assert out[0].confidence == 0.9
```

- [ ] **Step 2: Implement merger**

```python
# src/tender_insights/interpret/merger.py
from __future__ import annotations

from typing import Callable, TypeVar

T = TypeVar("T")


def dedupe_by_title(items: list[T], *, title_getter: Callable[[T], str] = lambda x: getattr(x, "title")) -> list[T]:
    best: dict[str, T] = {}
    for item in items:
        key = title_getter(item).strip().lower()
        existing = best.get(key)
        if existing is None or getattr(item, "confidence", 0) > getattr(existing, "confidence", 0):
            best[key] = item
    return list(best.values())
```

- [ ] **Step 3: Implement prompts**

```python
# src/tender_insights/interpret/prompts.py
from __future__ import annotations

SYSTEM_PROMPT = """你是招标文件解读专家。从给定章节文本中提取结构化信息。
只输出 JSON，字段：
- disqualification_items: 废标项（含 trigger_condition）
- scoring_items: 得分项（含 max_score, weight, criteria）
- bid_risk_items: 投标视角风险（severity: high|medium|low, risk_category）
- directory_requirements: 目录/文件组成要求（required_sections 数组, mandatory）
每条必须有 source_excerpt（原文摘录）和 section_path。"""


def build_user_prompt(section_title: str, section_path: list[str], markdown: str) -> str:
    return (
        f"章节: {section_title}\n"
        f"路径: {' > '.join(section_path)}\n\n"
        f"正文:\n{markdown[:12000]}"
    )
```

- [ ] **Step 4: Implement extractor（核心逻辑）**

```python
# src/tender_insights/interpret/extractor.py
from __future__ import annotations

from pathlib import Path

from doc_chunk.llm.client import LLMClient
from doc_chunk.models.outline import OutlineTree
from doc_chunk.workspace.layout import OutputWorkspace

from tender_insights.common.anchor_backfill import backfill_char_range
from tender_insights.common.llm_extractor import extract_json_model
from tender_insights.common.output_writer import write_json_artifact
from tender_insights.common.section_router import SectionRouter, load_routing_rules
from tender_insights.config import InsightsConfig
from tender_insights.interpret.merger import dedupe_by_title
from tender_insights.interpret.models import InterpretationFile, InterpretationLLMResponse
from tender_insights.interpret.prompts import SYSTEM_PROMPT, build_user_prompt

_ROUTING_PATH = Path(__file__).with_name("routing.yaml")


def _section_path(node_id: str, outline: OutlineTree) -> list[str]:
    node_map = {n.node_id: n for n in outline.nodes}
    chain: list[str] = []
    cur = node_map.get(node_id)
    while cur:
        chain.append(cur.title)
        cur = node_map.get(cur.parent_id) if cur.parent_id else None
    return list(reversed(chain))


def _slice_node_markdown(content_md: str, outline: OutlineTree, node_id: str) -> str:
    node = next(n for n in outline.nodes if n.node_id == node_id)
    start = node.anchor.char_start if node.anchor and node.anchor.char_start is not None else 0
    # 简化：取到下一同级节点
    siblings = sorted(
        [n for n in outline.nodes if n.level == node.level and (n.anchor.char_start or 0) > start],
        key=lambda n: n.anchor.char_start or 10**9,
    )
    end = siblings[0].anchor.char_start if siblings and siblings[0].anchor else len(content_md)
    return content_md[start:end]


def _apply_anchors(items: list, content_md: str) -> None:
    for item in items:
        start, end = backfill_char_range(content_md, item.source_excerpt)
        item.char_start = start
        item.char_end = end


def interpret_workspace(
    workspace: OutputWorkspace,
    client: LLMClient,
    *,
    config: InsightsConfig | None = None,
) -> InterpretationFile:
    config = config or InsightsConfig.from_env()
    outline = OutlineTree.model_validate_json(workspace.outline_path.read_text(encoding="utf-8"))
    content_md = workspace.content_path.read_text(encoding="utf-8")
    router = SectionRouter(load_routing_rules(_ROUTING_PATH))

    route_keys = ["disqualification", "scoring", "bid_risk", "directory"]
    target_node_ids: set[str] = set()
    for key in route_keys:
        for node in router.match_nodes(outline, key):
            target_node_ids.add(node.node_id)

    aggregated = InterpretationLLMResponse()
    for node_id in sorted(target_node_ids):
        node = next(n for n in outline.nodes if n.node_id == node_id)
        md = _slice_node_markdown(content_md, outline, node_id)
        path = _section_path(node_id, outline)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(node.title, path, md)},
        ]
        batch = extract_json_model(client, messages, InterpretationLLMResponse, max_retries=config.max_retries)
        aggregated.disqualification_items.extend(batch.disqualification_items)
        aggregated.scoring_items.extend(batch.scoring_items)
        aggregated.bid_risk_items.extend(batch.bid_risk_items)
        aggregated.directory_requirements.extend(batch.directory_requirements)

    dq = dedupe_by_title(aggregated.disqualification_items)
    sc = dedupe_by_title(aggregated.scoring_items)
    br = dedupe_by_title(aggregated.bid_risk_items)
    dr = dedupe_by_title(aggregated.directory_requirements)
    _apply_anchors(dq, content_md)
    _apply_anchors(sc, content_md)
    _apply_anchors(br, content_md)
    _apply_anchors(dr, content_md)

    result = InterpretationFile(
        source_workspace=str(workspace.root),
        disqualification_items=dq,
        scoring_items=sc,
        bid_risk_items=br,
        directory_requirements=dr,
    )
    write_json_artifact(
        workspace,
        "interpretation.json",
        result.model_dump(mode="json"),
        stage_name="interpret",
        output_key="interpretation",
    )
    return result
```

- [ ] **Step 5: Run merger test**

```bash
python -m pytest tests/tender_insights/unit/test_interpret_merger.py -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/tender_insights/interpret/merger.py src/tender_insights/interpret/prompts.py src/tender_insights/interpret/extractor.py tests/tender_insights/unit/test_interpret_merger.py
git commit -m "feat(tender_insights): add interpret extractor with merger and prompts"
```

---

### Task 8: Template 模块

**Files:**
- Create: `src/tender_insights/template/models.py`
- Create: `src/tender_insights/template/detector.py`
- Create: `src/tender_insights/template/boundary.py`
- Create: `src/tender_insights/template/classifier.py`
- Create: `src/tender_insights/template/extractor.py`
- Create: `tests/tender_insights/unit/test_template_detector.py`

- [ ] **Step 1: Write detector test**

```python
# tests/tender_insights/unit/test_template_detector.py
from doc_chunk.models.outline import OutlineNode, OutlineTree

from tender_insights.template.detector import detect_template_nodes


def test_detect_template_nodes_by_keyword() -> None:
    tree = OutlineTree(
        nodes=[
            OutlineNode(node_id="n1", title="投标人须知", level=1, parent_id=None, sort_order=0),
            OutlineNode(node_id="n2", title="附件：承诺书格式", level=1, parent_id=None, sort_order=1),
            OutlineNode(node_id="n3", title="授权委托书", level=2, parent_id="n2", sort_order=2),
        ]
    )
    hits = detect_template_nodes(tree)
    assert {h.node_id for h in hits} == {"n2", "n3"}
```

- [ ] **Step 2: Implement template subsystem**

```python
# src/tender_insights/template/models.py
from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class TemplateEntry(BaseModel):
    id: str
    type: Literal["commitment", "authorization", "declaration", "other"]
    type_label: str
    title: str
    section_path: list[str]
    file: str
    char_start: int | None = None
    char_end: int | None = None
    confidence: float = Field(ge=0.0, le=1.0)


class TemplatesIndexFile(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    templates: list[TemplateEntry] = Field(default_factory=list)
    analyzed_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
```

```python
# src/tender_insights/template/detector.py
from __future__ import annotations

from dataclasses import dataclass

from doc_chunk.models.outline import OutlineNode, OutlineTree

_KEYWORDS = ["附件", "承诺书", "授权", "声明", "委托"]


@dataclass(frozen=True, slots=True)
class TemplateHit:
    node_id: str
    title: str


def detect_template_nodes(outline: OutlineTree) -> list[TemplateHit]:
    hits: list[TemplateHit] = []
    for node in outline.nodes:
        if any(kw in node.title for kw in _KEYWORDS):
            hits.append(TemplateHit(node_id=node.node_id, title=node.title))
    return hits
```

```python
# src/tender_insights/template/boundary.py
from __future__ import annotations

import re

_HEADING_RE = re.compile(r"^(#{1,8})[ \t]+(.+?)[ \t#]*$", re.MULTILINE)


def slice_by_heading_level(content_md: str, start: int, level: int) -> tuple[str, int]:
    end = len(content_md)
    for match in _HEADING_RE.finditer(content_md):
        if match.start() <= start:
            continue
        if len(match.group(1)) <= level:
            end = match.start()
            break
    return content_md[start:end].strip(), end
```

```python
# src/tender_insights/template/classifier.py
from __future__ import annotations

from tender_insights.template.models import TemplateEntry


def classify_template(title: str, markdown: str) -> tuple[str, str, float]:
    text = f"{title}\n{markdown[:500]}"
    if "承诺书" in text or "承诺" in text:
        return "commitment", "承诺书", 0.95
    if "授权" in text:
        return "authorization", "授权书", 0.95
    if "声明" in text:
        return "declaration", "声明函", 0.95
    return "other", "其他", 0.6
```

`extractor.py` 组合 detector + boundary + classifier，写入 `workspace/templates/*.md` 与 `templates/index.json`，并调用 `write_json_artifact`（`stage_name="template"`, `output_key="templates"`）。实现模式与 `interpret/extractor.py` 相同，从 outline 节点切片。

- [ ] **Step 3: Run test**

```bash
python -m pytest tests/tender_insights/unit/test_template_detector.py -v
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/tender_insights/template/
git commit -m "feat(tender_insights): add template detection and extraction"
```

---

### Task 9: Legal 模块

**Files:**
- Create: `src/tender_insights/legal/models.py`
- Create: `src/tender_insights/legal/routing.yaml`
- Create: `src/tender_insights/legal/prompts.py`
- Create: `src/tender_insights/legal/extractor.py`
- Create: `tests/tender_insights/unit/test_legal_models.py`

- [ ] **Step 1: Write models test**（结构同 Task 6，覆盖 `LegalRiskItem`、`PendingConfirmation`、`LegalReviewFile`）

- [ ] **Step 2: Implement models**

```python
# src/tender_insights/legal/models.py — 关键字段
class LegalRiskItem(BaseModel):
    id: str
    description: str
    clause_excerpt: str
    risk_type: str
    severity: Severity
    section_path: list[str]
    char_start: int | None = None
    char_end: int | None = None
    confidence: float

class PendingConfirmation(BaseModel):
    id: str
    description: str
    confirm_with: str
    suggested_question: str
    section_path: list[str]
    char_start: int | None = None
    char_end: int | None = None
    confidence: float

class LegalReviewFile(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    source_workspace: str
    analyzed_at: str
    risk_items: list[LegalRiskItem]
    pending_confirmations: list[PendingConfirmation]
```

```yaml
# src/tender_insights/legal/routing.yaml
legal_risk:
  keywords: ["合同", "通用条款", "违约责任", "付款", "争议", "知识产权"]
pending:
  keywords: ["待定", "另行", "协商", "以...为准", "不明确"]
```

`legal/extractor.py`：**独立**调用 SectionRouter + LLM（不复用 `interpretation.json`），写入 `legal_review.json`。

- [ ] **Step 3: Run tests**

```bash
python -m pytest tests/tender_insights/unit/test_legal_models.py -v
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/tender_insights/legal/
git commit -m "feat(tender_insights): add independent legal review module"
```

---

### Task 10: CLI + Python API

**Files:**
- Create: `src/tender_insights/cli/main.py`
- Create: `src/tender_insights/api.py`

- [ ] **Step 1: Implement api.py**

```python
# src/tender_insights/api.py
from __future__ import annotations

from pathlib import Path

from doc_chunk.llm.client import LLMClient
from doc_chunk.llm.openai_client import create_llm_client_from_env
from doc_chunk.workspace.layout import OutputWorkspace

from tender_insights.common.workspace_resolver import resolve_workspace
from tender_insights.interpret.extractor import interpret_workspace
from tender_insights.legal.extractor import review_legal_workspace
from tender_insights.template.extractor import extract_templates_workspace


def resolve_workspace_path(path: Path, *, output_dir: Path | None = None, overwrite: bool = False) -> OutputWorkspace:
    return resolve_workspace(path, output_dir=output_dir, overwrite=overwrite)


def interpret_document(workspace: OutputWorkspace, *, client: LLMClient | None = None):
    client = client or create_llm_client_from_env()
    return interpret_workspace(workspace, client)


def extract_templates(workspace: OutputWorkspace, *, client: LLMClient | None = None):
    client = client or create_llm_client_from_env()
    return extract_templates_workspace(workspace, client)


def review_legal(workspace: OutputWorkspace, *, client: LLMClient | None = None):
    client = client or create_llm_client_from_env()
    return review_legal_workspace(workspace, client)
```

- [ ] **Step 2: Implement CLI**

```python
# src/tender_insights/cli/main.py
from __future__ import annotations

from pathlib import Path

import typer

from tender_insights.api import extract_templates, interpret_document, resolve_workspace_path, review_legal

app = typer.Typer(name="tender-insights", no_args_is_help=True)


def _resolve(path: Path, output: Path | None, overwrite: bool):
    return resolve_workspace_path(path, output_dir=output, overwrite=overwrite)


@app.command("interpret")
def interpret_cmd(
    path: Path,
    output: Path | None = typer.Option(None, "-o", "--output"),
    overwrite: bool = typer.Option(False, "--overwrite"),
) -> None:
    ws = _resolve(path, output, overwrite)
    interpret_document(ws)
    typer.echo(f"Wrote {ws.root / 'interpretation.json'}")


@app.command("template")
def template_cmd(
    path: Path,
    output: Path | None = typer.Option(None, "-o", "--output"),
    overwrite: bool = typer.Option(False, "--overwrite"),
) -> None:
    ws = _resolve(path, output, overwrite)
    extract_templates(ws)
    typer.echo(f"Wrote {ws.root / 'templates'}")


@app.command("legal")
def legal_cmd(
    path: Path,
    output: Path | None = typer.Option(None, "-o", "--output"),
    overwrite: bool = typer.Option(False, "--overwrite"),
) -> None:
    ws = _resolve(path, output, overwrite)
    review_legal(ws)
    typer.echo(f"Wrote {ws.root / 'legal_review.json'}")


@app.command("all")
def all_cmd(
    path: Path,
    output: Path | None = typer.Option(None, "-o", "--output"),
    overwrite: bool = typer.Option(False, "--overwrite"),
) -> None:
    ws = _resolve(path, output, overwrite)
    interpret_document(ws)
    extract_templates(ws)
    review_legal(ws)
```

- [ ] **Step 3: Verify CLI**

```bash
tender-insights --help
```

Expected: 显示 interpret / template / legal / all 子命令

- [ ] **Step 4: Commit**

```bash
git add src/tender_insights/api.py src/tender_insights/cli/main.py
git commit -m "feat(tender_insights): add CLI and public API"
```

---

### Task 11: 契约测试

**Files:**
- Create: `tests/tender_insights/contract/test_interpretation_schema.py`
- Create: `tests/tender_insights/contract/test_legal_review_schema.py`
- Create: `tests/tender_insights/contract/test_templates_index_schema.py`

- [ ] **Step 1: Write contract tests**

每个测试：`InterpretationFile.model_json_schema()` 经 `jsonschema.validate` 校验 fixture 样例；templates 与 legal 同理。

```python
# tests/tender_insights/contract/test_interpretation_schema.py
import jsonschema
from tender_insights.interpret.models import InterpretationFile

def test_interpretation_schema_accepts_minimal_fixture():
    schema = InterpretationFile.model_json_schema()
    fixture = {
        "schema_version": "1.0",
        "source_workspace": "/tmp/ws",
        "analyzed_at": "2026-06-16T00:00:00+00:00",
        "disqualification_items": [],
        "scoring_items": [],
        "bid_risk_items": [],
        "directory_requirements": [],
    }
    jsonschema.validate(fixture, schema)
```

- [ ] **Step 2: Run**

```bash
python -m pytest tests/tender_insights/contract/ -v
```

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/tender_insights/contract/
git commit -m "test(tender_insights): add JSON schema contract tests"
```

---

### Task 12: 集成测试（FakeLLM）

**Files:**
- Create: `tests/tender_insights/integration/test_pipeline_interpret.py`

- [ ] **Step 1: Write integration test with FakeLLMClient**

```python
# tests/tender_insights/integration/test_pipeline_interpret.py
import json
from doc_chunk.llm.client import FakeLLMClient
from tender_insights.api import interpret_document, resolve_workspace_path
from tender_insights.interpret.models import InterpretationFile


def test_interpret_writes_json(sample_docx, tmp_path):
    ws = resolve_workspace_path(sample_docx, output_dir=tmp_path / "ws", overwrite=True)
    fake = FakeLLMClient(
        default_response=json.dumps({
            "disqualification_items": [{
                "id": "dq-001", "title": "测试废标", "summary": "s",
                "trigger_condition": "t", "source_excerpt": "废标条款",
                "section_path": ["投标人须知"], "confidence": 0.9,
            }],
            "scoring_items": [],
            "bid_risk_items": [],
            "directory_requirements": [],
        })
    )
    result = interpret_document(ws, client=fake)
    assert isinstance(result, InterpretationFile)
    assert (ws.root / "interpretation.json").exists()
    assert len(result.disqualification_items) >= 1
```

- [ ] **Step 2: Run**

```bash
python -m pytest tests/tender_insights/integration/test_pipeline_interpret.py -v
```

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/tender_insights/integration/
git commit -m "test(tender_insights): add interpret integration test with FakeLLM"
```

---

### Task 13: 四个 Cursor Skills

**Files:**
- Create: `.cursor/skills/tender-extract/SKILL.md`
- Create: `.cursor/skills/tender-interpret/SKILL.md`
- Create: `.cursor/skills/tender-template/SKILL.md`
- Create: `.cursor/skills/tender-legal-review/SKILL.md`

- [ ] **Step 1: tender-extract skill**（调用 `doc-chunk pipeline`，说明工作区结构）

- [ ] **Step 2: tender-interpret skill**（触发词：解读招标、废标项、得分项；命令 `tender-insights interpret`；读 `interpretation.json`）

- [ ] **Step 3: tender-template skill**（触发词：承诺书模版、授权书；命令 `tender-insights template`）

- [ ] **Step 4: tender-legal-review skill**（触发词：法务审核、合规风险；命令 `tender-insights legal`；强调与 interpret 的 `bid_risk_items` 区分）

每个 SKILL.md 须包含：
- 何时触发
- 前置条件（`.venv`、`pip install -e ".[dev]"`、LLM 环境变量）
- 命令示例（工作区 + 原始文件两种）
- 输出文件路径与字段说明
- `--no-llm` 仅用于测试的说明

- [ ] **Step 5: Commit**

```bash
git add .cursor/skills/tender-extract/ .cursor/skills/tender-interpret/ .cursor/skills/tender-template/ .cursor/skills/tender-legal-review/
git commit -m "docs: add four tender analysis Cursor skills"
```

---

### Task 14: README 与验证

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 在 README 追加 tender_insights 章节**

包含：安装、`tender-insights` 命令示例、产出文件说明、skills 索引、设计文档链接。

- [ ] **Step 2: 全量测试**

```bash
python -m pytest tests/tender_insights/ -v
python -m pytest tests/ -q
```

Expected: 全部 PASS

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document tender_insights usage in README"
```

---

## Spec Coverage Self-Review

| 设计规格章节 | 对应 Task |
|-------------|-----------|
| 混合输入 C | Task 2 WorkspaceResolver |
| 解读/法务独立 | Task 7 vs Task 9，无交叉读取 |
| interpretation.json 四类字段 | Task 6–7 |
| templates/ 嵌入正文 | Task 8 |
| legal_review.json | Task 9 |
| CLI interpret/template/legal/all | Task 10 |
| Python API | Task 10 api.py |
| manifest 扩展 | Task 5 OutputWriter |
| 四 Skills | Task 13 |
| 契约 + 集成测试 | Task 11–12 |
| worktree 005 | Task 0 |

无 TBD/占位符；类型名 `InterpretationFile`、`LegalReviewFile`、`TemplatesIndexFile` 全计划一致。

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-16-tender-insights-skills.md`. Two execution options:

**1. Subagent-Driven (recommended)** — 每个 Task 派发独立 subagent，任务间做 review，迭代快

**2. Inline Execution** — 在本会话用 executing-plans 按 Task 批量执行，checkpoint 处暂停确认

你想用哪种方式开始实现？
