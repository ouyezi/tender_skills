# interpret v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `tender_insights.interpret` with full-document segmented extraction, OCR enrichment, overview summaries, and directory_outline — without modifying `doc_chunk`.

**Architecture:** Read doc_chunk workspace artifacts; OCR referenced images into `interpret/source_content.md`; plan 2k–12k token segments from chunks (fallback outline split); one LLM call per segment for all item types; merge; overview LLM; write schema 1.1 JSON.

**Tech Stack:** Python 3.11+, Pydantic v2, Pillow, OpenAI-compatible API (qwen-vl-ocr / qwen-plus), pytest

**Spec:** `docs/superpowers/specs/2026-06-24-interpret-v2-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `pyproject.toml` | Modify | Add `Pillow>=10.0.0` |
| `src/tender_insights/config.py` | Modify | OCR + segment env vars |
| `src/tender_insights/common/ocr/models.py` | Create | OcrCacheEntry, OcrCacheFile |
| `src/tender_insights/common/ocr/client.py` | Create | Vision OCR API client |
| `src/tender_insights/common/ocr/enricher.py` | Create | Hash cache, logo skip, compress, enrich |
| `src/tender_insights/common/content_source.py` | Create | InterpretSource + prepare |
| `src/tender_insights/common/segment_planner.py` | Create | Segment dataclass + plan_segments |
| `src/tender_insights/interpret/models.py` | Modify | overview, directory_outline, structure |
| `src/tender_insights/interpret/prompts.py` | Modify | Static system + segment/overview prompts |
| `src/tender_insights/interpret/overview.py` | Create | build_overview |
| `src/tender_insights/interpret/directory_outline.py` | Create | build_directory_outline |
| `src/tender_insights/interpret/merger.py` | Modify | Stronger dedupe key |
| `src/tender_insights/interpret/extractor.py` | Modify | v2 pipeline orchestration |
| `src/tender_insights/interpret/routing.yaml` | Delete | No longer used |
| `.env.example` | Modify | OCR_* vars |
| `.cursor/skills/tender-interpret/SKILL.md` | Modify | schema 1.1 docs |
| `tests/tender_insights/unit/test_segment_planner.py` | Create | |
| `tests/tender_insights/unit/test_ocr_enricher.py` | Create | |
| `tests/tender_insights/unit/test_overview.py` | Create | |
| `tests/tender_insights/unit/test_directory_outline.py` | Create | |
| `tests/tender_insights/contract/test_interpretation_schema.py` | Modify | schema 1.1 |
| `tests/tender_insights/integration/test_pipeline_interpret.py` | Modify | v2 assertions |

---

### Task 1: Config and dependency

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/tender_insights/config.py`
- Test: `tests/tender_insights/unit/test_insights_config.py` (create)

- [ ] **Step 1: Add Pillow dependency**

In `pyproject.toml` dependencies list add:

```toml
  "Pillow>=10.0.0",
```

- [ ] **Step 2: Extend InsightsConfig**

Replace `src/tender_insights/config.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass
import os


def _env_bool(key: str, default: bool) -> bool:
    raw = os.environ.get(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(key: str, default: int) -> int:
    raw = os.environ.get(key)
    if raw is None:
        return default
    return int(raw)


@dataclass(frozen=True, slots=True)
class InsightsConfig:
    llm_model: str = "qwen-plus"
    max_retries: int = 2
    ocr_enabled: bool = True
    ocr_model: str = "qwen-vl-ocr"
    segment_min_tokens: int = 2000
    segment_max_tokens: int = 12000
    ocr_logo_max_bytes: int = 10240
    ocr_logo_max_px: int = 128
    ocr_max_long_edge: int = 1500

    @classmethod
    def from_env(cls) -> InsightsConfig:
        provider = (os.environ.get("LLM_PROVIDER") or "qwen").lower()
        default_model = "qwen-plus" if provider == "qwen" else "gpt-4o-mini"
        return cls(
            llm_model=(
                os.environ.get("LLM_MODEL")
                or os.environ.get("DOC_CHUNK_LLM_MODEL")
                or default_model
            ),
            ocr_enabled=_env_bool("OCR_ENABLED", True),
            ocr_model=os.environ.get("OCR_MODEL") or "qwen-vl-ocr",
            segment_min_tokens=_env_int("SEGMENT_MIN_TOKENS", 2000),
            segment_max_tokens=_env_int("SEGMENT_MAX_TOKENS", 12000),
            ocr_logo_max_bytes=_env_int("OCR_LOGO_MAX_BYTES", 10240),
            ocr_logo_max_px=_env_int("OCR_LOGO_MAX_PX", 128),
            ocr_max_long_edge=_env_int("OCR_MAX_LONG_EDGE", 1500),
        )
```

- [ ] **Step 3: Write config test**

Create `tests/tender_insights/unit/test_insights_config.py`:

```python
from tender_insights.config import InsightsConfig


def test_from_env_defaults(monkeypatch) -> None:
    monkeypatch.delenv("OCR_ENABLED", raising=False)
    cfg = InsightsConfig.from_env()
    assert cfg.ocr_model == "qwen-vl-ocr"
    assert cfg.segment_max_tokens == 12000
    assert cfg.ocr_enabled is True


def test_from_env_overrides(monkeypatch) -> None:
    monkeypatch.setenv("OCR_ENABLED", "false")
    monkeypatch.setenv("SEGMENT_MAX_TOKENS", "8000")
    cfg = InsightsConfig.from_env()
    assert cfg.ocr_enabled is False
    assert cfg.segment_max_tokens == 8000
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/tongqianni/xlab/tender_skills && pip install -e ".[dev]" -q && pytest tests/tender_insights/unit/test_insights_config.py -v
```

Expected: PASS

---

### Task 2: OCR models and client

**Files:**
- Create: `src/tender_insights/common/ocr/__init__.py`
- Create: `src/tender_insights/common/ocr/models.py`
- Create: `src/tender_insights/common/ocr/client.py`
- Test: `tests/tender_insights/unit/test_ocr_client.py`

- [ ] **Step 1: OCR models**

`src/tender_insights/common/ocr/models.py`:

```python
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class OcrCacheEntry(BaseModel):
    image_ref: str
    text: str = ""
    status: Literal["success", "skipped", "failed"] = "success"
    model: str = ""
    skipped_reason: str | None = None


class OcrCacheFile(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    entries: dict[str, OcrCacheEntry] = Field(default_factory=dict)
```

- [ ] **Step 2: OCR client**

`src/tender_insights/common/ocr/client.py`:

```python
from __future__ import annotations

import base64
import os

from openai import OpenAI

from doc_chunk.llm.openai_client import resolve_llm_settings_from_env


class OcrClient:
    def __init__(self, *, model: str, api_key: str, base_url: str) -> None:
        self.model = model
        self._client = OpenAI(api_key=api_key, base_url=base_url)

    @classmethod
    def from_env(cls, *, model: str) -> OcrClient:
        api_key, _, base_url = resolve_llm_settings_from_env()
        return cls(model=model, api_key=api_key, base_url=base_url)

    def recognize_image_bytes(self, image_bytes: bytes, *, mime: str = "image/png") -> str:
        b64 = base64.standard_b64encode(image_bytes).decode("ascii")
        data_url = f"data:{mime};base64,{b64}"
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "请识别图片中的全部文字，按阅读顺序输出纯文本，不要解释。"},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
            timeout=120.0,
        )
        return (response.choices[0].message.content or "").strip()
```

- [ ] **Step 3: Client test with mock**

`tests/tender_insights/unit/test_ocr_client.py` — use `unittest.mock.patch` on `OpenAI` to return fixed text; assert `recognize_image_bytes` returns it.

- [ ] **Step 4: Run test**

```bash
pytest tests/tender_insights/unit/test_ocr_client.py -v
```

---

### Task 3: OCR enricher

**Files:**
- Create: `src/tender_insights/common/ocr/enricher.py`
- Test: `tests/tender_insights/unit/test_ocr_enricher.py`

- [ ] **Step 1: Write failing tests**

Test cases:
- `_is_logo_skip(width=64, height=64, size=5000)` → True
- `_is_logo_skip(width=200, height=200, size=5000)` → False
- `_file_sha256` stable for same bytes
- `enrich_content_with_ocr` inserts `<!-- ocr:... -->` block after image line
- cache hit skips second API call (mock OcrClient, call count == 1 for same image twice)

- [ ] **Step 2: Implement enricher**

Key functions in `enricher.py`:

```python
_IMAGE_REF_RE = re.compile(r"!\[[^\]]*]\(([^)]+)\)")

def list_image_refs(content_md: str) -> list[str]: ...
def _is_logo_skip(width: int, height: int, size_bytes: int, *, max_bytes: int, max_px: int) -> bool: ...
def _compress_image_bytes(raw: bytes, *, max_long_edge: int) -> tuple[bytes, str]: ...  # returns (bytes, mime)
def _file_sha256(path: Path) -> str: ...
def enrich_content_with_ocr(
    workspace: OutputWorkspace,
    content_md: str,
    *,
    config: InsightsConfig,
    client: OcrClient | None = None,
) -> tuple[str, OcrCacheFile, int]:
    """Returns (source_content_md, cache, ocr_api_call_count)."""
```

Logic:
1. Load existing `interpret/ocr_cache.json` if present
2. For each unique image ref in content_md (resolve relative to workspace.root)
3. Hash file → cache hit → reuse text
4. Logo skip → entry status=skipped, skipped_reason=logo
5. Else compress + OCR → cache entry status=success
6. Build source_content: after each `![...](ref)` line append OCR block if text non-empty
7. Write `interpret/source_content.md` and `interpret/ocr_cache.json`

- [ ] **Step 3: Run tests**

```bash
pytest tests/tender_insights/unit/test_ocr_enricher.py -v
```

---

### Task 4: Content source

**Files:**
- Create: `src/tender_insights/common/content_source.py`
- Test: extend `test_ocr_enricher.py` or new `test_content_source.py`

- [ ] **Step 1: Implement**

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from doc_chunk.models.content_block import ContentBlocksFile
from doc_chunk.workspace.layout import OutputWorkspace

from tender_insights.common.ocr.enricher import enrich_content_with_ocr
from tender_insights.common.section_slice import load_content_blocks
from tender_insights.config import InsightsConfig


@dataclass(frozen=True, slots=True)
class InterpretSource:
    markdown: str
    source_path: Path
    blocks: ContentBlocksFile | None
    ocr_image_count: int


def prepare_interpret_source(
    workspace: OutputWorkspace,
    *,
    config: InsightsConfig,
) -> InterpretSource:
    content_md = workspace.content_path.read_text(encoding="utf-8")
    blocks = load_content_blocks(workspace)
    interpret_dir = workspace.root / "interpret"
    interpret_dir.mkdir(parents=True, exist_ok=True)
    source_path = interpret_dir / "source_content.md"

    if config.ocr_enabled:
        enriched, _, ocr_count = enrich_content_with_ocr(workspace, content_md, config=config)
    else:
        enriched = content_md
        ocr_count = 0

    source_path.write_text(enriched, encoding="utf-8")
    return InterpretSource(
        markdown=enriched,
        source_path=source_path,
        blocks=blocks,
        ocr_image_count=ocr_count,
    )
```

- [ ] **Step 2: Test** — mock OCR; assert `source_path` written and markdown returned.

---

### Task 5: Segment planner

**Files:**
- Create: `src/tender_insights/common/segment_planner.py`
- Test: `tests/tender_insights/unit/test_segment_planner.py`

- [ ] **Step 1: Write failing tests**

Fixtures: small synthetic markdown + outline; verify:
- single short section → 1 segment
- two tiny adjacent sections same path → merged to 1 if under min
- oversized section → split into 2+

- [ ] **Step 2: Implement**

```python
@dataclass(frozen=True, slots=True)
class Segment:
    segment_id: str
    section_path: list[str]
    markdown: str
    char_start: int
    char_end: int
    token_estimate: int


def plan_segments(
    workspace: OutputWorkspace,
    source: InterpretSource,
    outline: OutlineTree,
    *,
    config: InsightsConfig,
) -> list[Segment]:
    ...
```

Implementation notes:
- Try load `workspace.chunks_dir / "index.json"` → read chunk JSON files
- If missing: `_split_markdown_sections` copied/adapted from doc_chunk planner logic (regex headings) — **in this file only**
- Apply `_merge_small_segments` then `_split_large_segments`
- For each segment, run `slice_for_llm` equivalent on char range with blocks
- Assign `char_start`/`char_end` relative to `source.markdown`

- [ ] **Step 3: Run tests**

```bash
pytest tests/tender_insights/unit/test_segment_planner.py -v
```

---

### Task 6: Interpret models (schema 1.1)

**Files:**
- Modify: `src/tender_insights/interpret/models.py`
- Modify: `tests/tender_insights/unit/test_interpret_models.py`
- Modify: `tests/tender_insights/contract/test_interpretation_schema.py`

- [ ] **Step 1: Add models**

Add to `models.py`:

```python
class DirectoryStructureNode(BaseModel):
    order: int
    number: str | None = None
    title: str
    mandatory: bool = True
    children: list[DirectoryStructureNode] = Field(default_factory=list)


class InterpretationOverview(BaseModel):
    summary: str
    disqualification_summary: str
    scoring_summary: str
    bid_risk_summary: str
    directory_summary: str


class DirectoryOutlineNode(BaseModel):
    id: str
    title: str
    level: int
    order: int
    mandatory: bool = True
    number: str | None = None


class DirectoryOutline(BaseModel):
    confidence: float = Field(ge=0.0, le=1.0)
    nodes: list[DirectoryOutlineNode] = Field(default_factory=list)
```

Extend `DirectoryRequirement` with optional `structure: list[DirectoryStructureNode]`.

Change `InterpretationFile`:
- `schema_version: Literal["1.0", "1.1"] = "1.1"`
- Add `overview: InterpretationOverview`
- Add `directory_outline: DirectoryOutline`
- Add `segment_count: int = 0`
- Add `ocr_image_count: int = 0`

- [ ] **Step 2: Update contract test** — validate overview + directory_outline required for 1.1.

---

### Task 7: Prompts

**Files:**
- Modify: `src/tender_insights/interpret/prompts.py`

- [ ] **Step 1: Replace prompts**

```python
SYSTEM_PROMPT = """你是招标文件解读专家。从给定正文片段中提取结构化信息。
只输出 JSON，字段：
- disqualification_items: 废标项（含 trigger_condition）
- scoring_items: 得分项（含 max_score, weight, criteria）
- bid_risk_items: 投标视角风险（severity: high|medium|low, risk_category）
- directory_requirements: 目录/文件组成（required_sections, mandatory, structure 可选树形）
每条必须有 id, title, summary, source_excerpt, section_path, confidence。
若无某类内容，对应数组返回 []。"""


def build_segment_prompt(segment_id: str, section_path: list[str], markdown: str) -> str:
    path = " > ".join(section_path) if section_path else "(root)"
    return f"segment_id: {segment_id}\nsection_path: {path}\n\n正文:\n{markdown}"


OVERVIEW_SYSTEM_PROMPT = """你是招标文件解读专家。根据已提取的结构化明细，生成概要描述。
只输出 JSON：{ summary, disqualification_summary, scoring_summary, bid_risk_summary, directory_summary }"""


def build_overview_prompt(items_json: str) -> str:
    return f"已提取明细:\n{items_json}"
```

Remove `markdown[:12000]` truncation entirely.

---

### Task 8: Overview and directory_outline builders

**Files:**
- Create: `src/tender_insights/interpret/overview.py`
- Create: `src/tender_insights/interpret/directory_outline.py`
- Test: `tests/tender_insights/unit/test_overview.py`, `test_directory_outline.py`

- [ ] **Step 1: directory_outline.py**

```python
def build_directory_outline(
    directory_requirements: list[DirectoryRequirement],
) -> DirectoryOutline:
    nodes: list[DirectoryOutlineNode] = []
    order = 1
    has_structure = False
    for req in directory_requirements:
        if req.structure:
            has_structure = True
            for item in req.structure:
                nodes.append(DirectoryOutlineNode(
                    id=f"dir-{order:03d}",
                    title=item.title,
                    level=1,
                    order=order,
                    mandatory=item.mandatory,
                    number=item.number,
                ))
                order += 1
        else:
            for title in req.required_sections:
                nodes.append(DirectoryOutlineNode(
                    id=f"dir-{order:03d}",
                    title=title,
                    level=1,
                    order=order,
                    mandatory=req.mandatory,
                ))
                order += 1
    confidence = 0.85 if has_structure else (0.6 if nodes else 0.0)
    return DirectoryOutline(confidence=confidence, nodes=nodes)
```

- [ ] **Step 2: overview.py**

```python
class OverviewLLMResponse(BaseModel):
    summary: str
    disqualification_summary: str
    scoring_summary: str
    bid_risk_summary: str
    directory_summary: str


def build_overview(
    client: LLMClient,
    *,
    dq, sc, br, dr,
    max_retries: int = 2,
) -> InterpretationOverview:
    payload = {
        "disqualification_items": [i.model_dump(include={"title", "summary", "trigger_condition"}) for i in dq],
        "scoring_items": [i.model_dump(include={"title", "summary", "max_score", "weight", "criteria"}) for i in sc],
        "bid_risk_items": [i.model_dump(include={"title", "summary", "severity", "risk_category"}) for i in br],
        "directory_requirements": [i.model_dump(include={"title", "required_sections", "mandatory"}) for i in dr],
    }
    messages = [
        {"role": "system", "content": OVERVIEW_SYSTEM_PROMPT},
        {"role": "user", "content": build_overview_prompt(json.dumps(payload, ensure_ascii=False))},
    ]
    resp = extract_json_model(client, messages, OverviewLLMResponse, max_retries=max_retries)
    return InterpretationOverview(**resp.model_dump())
```

- [ ] **Step 3: Unit tests** for `build_directory_outline` with structure and flat fallback.

---

### Task 9: Rewrite extractor (v2 orchestration)

**Files:**
- Modify: `src/tender_insights/interpret/extractor.py`
- Delete usage of: `routing.yaml`, `SectionRouter`, `node_char_range` in extractor

- [ ] **Step 1: Rewrite interpret_workspace**

```python
def interpret_workspace(
    workspace: OutputWorkspace,
    client: LLMClient,
    *,
    config: InsightsConfig | None = None,
) -> InterpretationFile:
    config = config or InsightsConfig.from_env()
    outline = OutlineTree.model_validate_json(workspace.outline_path.read_text(encoding="utf-8"))

    source = prepare_interpret_source(workspace, config=config)
    segments = plan_segments(workspace, source, outline, config=config)

    aggregated = InterpretationLLMResponse()
    for seg in segments:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_segment_prompt(seg.segment_id, seg.section_path, seg.markdown)},
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

    anchor_md = source.markdown
    for items in (dq, sc, br, dr):
        _apply_anchors(items, anchor_md)

    overview = build_overview(client, dq=dq, sc=sc, br=br, dr=dr, max_retries=config.max_retries)
    directory_outline = build_directory_outline(dr)

    result = InterpretationFile(
        source_workspace=str(workspace.root),
        overview=overview,
        disqualification_items=dq,
        scoring_items=sc,
        bid_risk_items=br,
        directory_requirements=dr,
        directory_outline=directory_outline,
        segment_count=len(segments),
        ocr_image_count=source.ocr_image_count,
    )
    write_json_artifact(workspace, "interpretation.json", result.model_dump(mode="json"), stage_name="interpret", output_key="interpretation")
    return result
```

- [ ] **Step 2: Delete `src/tender_insights/interpret/routing.yaml`**

- [ ] **Step 3: Update integration test** — FakeLLMClient returns segment JSON + overview JSON (use `push_response` for second call).

---

### Task 10: Merger improvement

**Files:**
- Modify: `src/tender_insights/interpret/merger.py`

- [ ] **Step 1: Add excerpt-aware dedupe**

When titles match, keep item with longer `source_excerpt` or higher confidence (existing logic keeps higher confidence — extend to compare excerpt length on tie).

---

### Task 11: Docs and env

**Files:**
- Modify: `.env.example`
- Modify: `.cursor/skills/tender-interpret/SKILL.md`

- [ ] **Step 1: Add to `.env.example`:**

```bash
OCR_ENABLED=true
OCR_MODEL=qwen-vl-ocr
SEGMENT_MIN_TOKENS=2000
SEGMENT_MAX_TOKENS=12000
```

- [ ] **Step 2: Update SKILL.md** — document schema 1.1 fields, OCR behavior, remove routing mention.

---

### Task 12: Full test suite

- [ ] **Step 1: Run all tender_insights tests**

```bash
pytest tests/tender_insights/ -v
```

Expected: all PASS

- [ ] **Step 2: Run ruff if configured**

```bash
ruff check src/tender_insights tests/tender_insights
```

---

## Plan Self-Review (spec coverage)

| Spec § | Task |
|--------|------|
| §2 决策 | Task 1, 3, 9 |
| §3 架构 | Task 4, 5, 9 |
| §4 数据模型 | Task 6 |
| §5 分段 | Task 5 |
| §6 LLM | Task 7, 8, 9 |
| §7 OCR | Task 2, 3, 4 |
| §8 directory_outline | Task 8 |
| §9 合并锚点 | Task 9, 10 |
| §10 manifest | Task 3 (ocr_cache write), Task 9 |
| §11 测试 | All test tasks |
| 不改 doc_chunk | Enforced throughout |

No TBD placeholders remain.

---

## Execution Handoff

Plan saved to `docs/superpowers/plans/2026-06-24-interpret-v2.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks  
2. **Inline Execution** — execute tasks in this session with checkpoints

Which approach?
