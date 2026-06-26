# LLM 模版提取 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 Plan → Extract → Merge 三阶段 LLM pipeline 替换关键词模版检测，支持整篇/分层分片、机械切片保真、Viewer 独立按钮与「开始解读」末尾共用同一逻辑。

**Architecture:** `sharder` 确定性分片（outline → heading → char）写 `templates/plan.json`；每片 `template_extract` LLM 返回全局 `char_start`/`char_end`；`slicer` 用 `slice_for_llm` 写 `.md`；`merger` 规则去重写 `index.json` v1.1。Viewer 新增 `job_kind=template` 与进度阶段。

**Tech Stack:** Python 3.11+, Pydantic v2, `doc_chunk`/`tender_insights`, FastAPI Viewer, pytest, FakeLLMClient

**Spec:** [`docs/superpowers/specs/2026-06-26-template-extraction-llm-design.md`](../specs/2026-06-26-template-extraction-llm-design.md)

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `src/tender_insights/config.py` | `TEMPLATE_*` 配置字段 |
| `src/tender_insights/template/models.py` | Plan/Shard/LLM response/index v1.1 |
| `src/tender_insights/template/sharder.py` | 三层回退分片 |
| `src/tender_insights/template/merger.py` | 跨片去重、重编号 |
| `src/tender_insights/template/slicer.py` | 边界校验 + `slice_for_llm` + 写 `.md` |
| `src/tender_insights/template/prompts.py` | `template_plan` / `template_extract` prompts |
| `src/tender_insights/template/planner.py` | 写 plan.json + 可选 LLM plan |
| `src/tender_insights/template/extractor.py` | 三阶段编排（替换旧规则主路径） |
| `src/tender_insights/api.py` | `run_template_job`；`run_interpret_job` 改调新逻辑 |
| `tests/helpers/template_fake_llm.py` | FakeLLM 按 call_type 返回 plan/extract JSON |
| `tests/tender_insights/unit/test_template_sharder.py` | sharder 单测 |
| `tests/tender_insights/unit/test_template_merger.py` | merger 单测 |
| `tests/tender_insights/integration/test_template_extract.py` | 端到端 FakeLLM |
| `viewer/viewer/models.py` | `job_kind`/`stage` 扩展 |
| `viewer/viewer/routes/interpret.py` | `POST .../template` |
| `viewer/viewer/services/interpret_pipeline.py` | `run_template_on_workspace` / `run_template_job` |
| `viewer/viewer/services/interpret_job_registry.py` | template job 初始 stage |
| `viewer/viewer/static/interpret.html` | 「提取模版」按钮 |
| `viewer/viewer/static/interpret.js` | 进度阶段、API、轮询 |
| `.env.example` | `TEMPLATE_*` 变量 |

---

### Task 1: 配置与数据模型

**Files:**
- Modify: `src/tender_insights/config.py`
- Modify: `src/tender_insights/template/models.py`
- Modify: `.env.example`
- Test: `tests/tender_insights/unit/test_insights_config.py`
- Test: `tests/tender_insights/contract/test_templates_index_schema.py`

- [ ] **Step 1: 写配置失败测试**

在 `tests/tender_insights/unit/test_insights_config.py` 追加：

```python
def test_template_config_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEMPLATE_WHOLE_DOC_MAX_CHARS", "100000")
    monkeypatch.setenv("TEMPLATE_SHARD_MAX_CHARS", "30000")
    monkeypatch.setenv("TEMPLATE_CHAR_CHUNK_OVERLAP", "600")
    monkeypatch.setenv("TEMPLATE_PLAN_ENABLED", "false")
    cfg = InsightsConfig.from_env()
    assert cfg.template_whole_doc_max_chars == 100000
    assert cfg.template_shard_max_chars == 30000
    assert cfg.template_char_chunk_overlap == 600
    assert cfg.template_plan_enabled is False
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/tender_insights/unit/test_insights_config.py::test_template_config_from_env -v`

Expected: FAIL `AttributeError`

- [ ] **Step 3: 实现 InsightsConfig 字段**

在 `src/tender_insights/config.py` 的 `InsightsConfig` 增加：

```python
template_whole_doc_max_chars: int = 80000
template_shard_max_chars: int = 24000
template_char_chunk_overlap: int = 500
template_plan_enabled: bool = True
```

`from_env()` 读取 `TEMPLATE_WHOLE_DOC_MAX_CHARS` 等（bool 用 `_env_bool`）。

- [ ] **Step 4: 扩展 template models**

在 `src/tender_insights/template/models.py` 增加：

```python
class TemplateShard(BaseModel):
    shard_id: str
    strategy: Literal["whole_doc", "outline_l1", "outline_child", "heading", "char"]
    section_path: list[str] = Field(default_factory=list)
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    char_count: int = Field(ge=0)


class TemplatePlanFile(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    planned_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    whole_doc_chars: int = 0
    shard_count: int = 0
    shards: list[TemplateShard] = Field(default_factory=list)
    merge_policy: str = "dedupe_by_char_overlap_and_title"
    llm_notes: str | None = None
    priority_sections: list[str] = Field(default_factory=list)


class TemplateHitLLM(BaseModel):
    title: str
    type: Literal["commitment", "authorization", "declaration", "other"]
    type_label: str
    char_start: int
    char_end: int
    confidence: float = Field(ge=0.0, le=1.0)
    source_excerpt: str = ""


class TemplateExtractResponse(BaseModel):
    templates: list[TemplateHitLLM] = Field(default_factory=list)


class TemplatePlanLLMResponse(BaseModel):
    shard_count: int
    priority_sections: list[str] = Field(default_factory=list)
    notes: str = ""
```

将 `TemplatesIndexFile.schema_version` 改为 `Literal["1.0", "1.1"]`，默认 `"1.1"`；`TemplateEntry` 增加 `extraction_method: Literal["llm", "rule"] = "llm"`、`shard_id: str | None = None`；顶层增加 `plan_ref: str | None = None`、`shard_count: int | None = None`。

- [ ] **Step 5: 更新契约测试**

```python
def test_templates_index_schema_v11_accepts_llm_fields() -> None:
    fixture = {
        "schema_version": "1.1",
        "analyzed_at": "2026-06-26T00:00:00+00:00",
        "plan_ref": "templates/plan.json",
        "shard_count": 2,
        "templates": [{
            "id": "tpl-001",
            "type": "authorization",
            "type_label": "授权书",
            "title": "授权书",
            "section_path": ["第四章"],
            "file": "templates/authorization-001.md",
            "char_start": 100,
            "char_end": 200,
            "confidence": 0.9,
            "extraction_method": "llm",
            "shard_id": "shard-001",
        }],
    }
    jsonschema.validate(fixture, TemplatesIndexFile.model_json_schema())
```

- [ ] **Step 6: 更新 `.env.example`**

```bash
# Template extraction
TEMPLATE_WHOLE_DOC_MAX_CHARS=80000
TEMPLATE_SHARD_MAX_CHARS=24000
TEMPLATE_CHAR_CHUNK_OVERLAP=500
TEMPLATE_PLAN_ENABLED=true
```

- [ ] **Step 7: 运行测试**

Run: `.venv/bin/pytest tests/tender_insights/unit/test_insights_config.py tests/tender_insights/contract/test_templates_index_schema.py -v`

Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/tender_insights/config.py src/tender_insights/template/models.py .env.example tests/
git commit -m "feat(template): add config and v1.1 data models for LLM extraction"
```

---

### Task 2: Sharder（确定性分片）

**Files:**
- Create: `src/tender_insights/template/sharder.py`
- Test: `tests/tender_insights/unit/test_template_sharder.py`

- [ ] **Step 1: 写 whole_doc 测试**

```python
from doc_chunk.models.outline import OutlineNode, OutlineTree
from tender_insights.config import InsightsConfig
from tender_insights.template.sharder import build_template_shards

CONTENT = "# 第一章\n\n" + ("正文 " * 100)

def test_sharder_whole_doc_when_small() -> None:
    outline = OutlineTree(nodes=[
        OutlineNode(node_id="n1", title="第一章", level=1, parent_id=None, sort_order=0),
    ])
    cfg = InsightsConfig(template_whole_doc_max_chars=100_000)
    shards = build_template_shards(CONTENT, outline, config=cfg)
    assert len(shards) == 1
    assert shards[0].strategy == "whole_doc"
    assert shards[0].char_start == 0
    assert shards[0].char_end == len(CONTENT)
```

- [ ] **Step 2: 写 heading 回退测试**

```python
CHAPTER4 = (
    "# 第四章参选文件格式\n\n"
    "## 授权书\n\n授权正文\n\n"
    "## 声明函\n\n声明正文\n"
)
LONG_PREFIX = "x" * 30_000

def test_sharder_splits_by_heading_when_l1_too_large() -> None:
    content = LONG_PREFIX + CHAPTER4
    start = len(LONG_PREFIX)
    outline = OutlineTree(nodes=[
        OutlineNode(
            node_id="n4", title="第四章参选文件格式", level=1, parent_id=None, sort_order=0,
            anchor=__import__("doc_chunk.models.outline", fromlist=["OutlineAnchor"]).OutlineAnchor(
                char_start=start, char_end=len(content),
            ),
        ),
    ])
    cfg = InsightsConfig(template_whole_doc_max_chars=1000, template_shard_max_chars=5000)
    shards = build_template_shards(content, outline, config=cfg)
    strategies = {s.strategy for s in shards}
    assert "heading" in strategies or "outline_l1" in strategies
    assert sum(1 for s in shards if "授权" in "".join(s.section_path) or s.char_start >= start) >= 1
```

（实现时 `OutlineNode` 需正确构造 `anchor`；参考 `test_template_detector.py` 或现有 outline fixture。）

- [ ] **Step 3: 运行确认失败**

Run: `.venv/bin/pytest tests/tender_insights/unit/test_template_sharder.py -v`

Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 4: 实现 `build_template_shards`**

`sharder.py` 核心逻辑：

```python
def build_template_shards(
    content_md: str,
    outline: OutlineTree,
    *,
    config: InsightsConfig,
) -> list[TemplateShard]:
    n = len(content_md)
    if n <= config.template_whole_doc_max_chars:
        return [_shard("shard-001", "whole_doc", [], 0, n)]

    l1_nodes = sorted(
        [node for node in outline.nodes if node.level == 1],
        key=lambda node: node.anchor.char_start if node.anchor else 0,
    )
    if not l1_nodes:
        return _char_shards(content_md, config)

    raw: list[TemplateShard] = []
    for i, node in enumerate(l1_nodes, start=1):
        start, end = node_char_range_from_outline(content_md, outline, node.node_id)
        path = _section_path(node.node_id, outline)
        raw.extend(_refine_shard(content_md, outline, node, start, end, path, config, index=i))
    return _reindex_shards(raw)
```

`_refine_shard`：若 `end-start > template_shard_max_chars`，先找 `parent_id==node.node_id` 的子节点；无子节点则 `_heading_shards`；仍大则 `_char_shards`。

`_heading_shards`：在 `[start,end)` 内用 `boundary._HEADING_RE` 找 `##` 级标题切分。

`_char_shards`：步长 `template_shard_max_chars - overlap`。

复用 `tender_insights.common.section_slice.node_char_range`（或内联同等逻辑）。

- [ ] **Step 5: 运行测试**

Run: `.venv/bin/pytest tests/tender_insights/unit/test_template_sharder.py -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/tender_insights/template/sharder.py tests/tender_insights/unit/test_template_sharder.py
git commit -m "feat(template): add hierarchical sharder with heading and char fallback"
```

---

### Task 3: Merger（跨片去重）

**Files:**
- Create: `src/tender_insights/template/merger.py`
- Test: `tests/tender_insights/unit/test_template_merger.py`

- [ ] **Step 1: 写重叠去重测试**

```python
from tender_insights.template.merger import dedupe_template_hits
from tender_insights.template.models import TemplateHitLLM

def test_merger_keeps_higher_confidence_on_overlap() -> None:
    hits = [
        TemplateHitLLM(title="授权书", type="authorization", type_label="授权书",
                       char_start=100, char_end=500, confidence=0.7, source_excerpt="a"),
        TemplateHitLLM(title="授权书", type="authorization", type_label="授权书",
                       char_start=120, char_end=480, confidence=0.95, source_excerpt="a"),
    ]
    out = dedupe_template_hits(hits)
    assert len(out) == 1
    assert out[0].confidence == 0.95
```

- [ ] **Step 2: 实现 `dedupe_template_hits`**

```python
def _overlap_ratio(a_start: int, a_end: int, b_start: int, b_end: int) -> float:
    inter = max(0, min(a_end, b_end) - max(a_start, b_start))
    shorter = min(a_end - a_start, b_end - b_start)
    return inter / shorter if shorter else 0.0

def dedupe_template_hits(hits: list[TemplateHitLLM]) -> list[TemplateHitLLM]:
    sorted_hits = sorted(hits, key=lambda h: (-h.confidence, h.char_start))
    kept: list[TemplateHitLLM] = []
    for hit in sorted_hits:
        if any(_overlap_ratio(hit.char_start, hit.char_end, k.char_start, k.char_end) > 0.5 for k in kept):
            continue
        if any(_normalized_title(hit.title) == _normalized_title(k.title) and _jaccard(hit.source_excerpt, k.source_excerpt) > 0.8 for k in kept):
            continue
        kept.append(hit)
    return sorted(kept, key=lambda h: h.char_start)
```

- [ ] **Step 3: 运行测试**

Run: `.venv/bin/pytest tests/tender_insights/unit/test_template_merger.py -v`

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/tender_insights/template/merger.py tests/tender_insights/unit/test_template_merger.py
git commit -m "feat(template): add cross-shard hit deduplication"
```

---

### Task 4: Prompts 与 FakeLLM

**Files:**
- Create: `src/tender_insights/template/prompts.py`
- Create: `tests/helpers/template_fake_llm.py`

- [ ] **Step 1: 实现 prompts**

`prompts.py`：

```python
TEMPLATE_PLAN_SYSTEM = """你是招标文件分析专家。根据目录与各分片摘要，补充模版提取计划说明。
只输出 JSON：{"shard_count": number, "priority_sections": ["..."], "notes": "..."}
不要修改分片边界。"""

TEMPLATE_EXTRACT_SYSTEM = """你是招标文件模版提取专家。
模版 = 发标单位要求投标人填写、签字、盖章并按格式提交的范本/表格/函件。
只输出 JSON：{"templates": [{"title","type","type_label","char_start","char_end","confidence","source_excerpt"}]}
char_start/char_end 为相对整篇 content.md 的全局字符下标。不要改写正文，只标边界。
排除：纯采购需求、合同正文、评审办法说明。"""

def build_plan_user_prompt(*, doc_title: str, shard_summaries: list[dict]) -> str: ...
def build_extract_user_prompt(*, shard: TemplateShard, shard_markdown: str) -> str: ...
```

`build_extract_user_prompt` 必须写明：`本片段全局偏移 char_start={shard.char_start}`，LLM 返回的坐标须为全局坐标。

- [ ] **Step 2: 实现 TemplateFakeLLM**

```python
class TemplateFakeLLM(FakeLLMClient):
    def __init__(self, *, plan_json: str, extract_json: str) -> None:
        super().__init__()
        self._plan_json = plan_json
        self._extract_json = extract_json

    def complete_with_meta(self, messages, **kwargs):
        user = " ".join(m.get("content", "") for m in messages if m.get("role") == "user")
        if "分片摘要" in user or "shard" in user.lower():
            return LLMCompletionResult(text=self._plan_json)
        return LLMCompletionResult(text=self._extract_json)
```

- [ ] **Step 3: Commit**

```bash
git add src/tender_insights/template/prompts.py tests/helpers/template_fake_llm.py
git commit -m "feat(template): add LLM prompts and test fake client"
```

---

### Task 5: Slicer 与 Planner

**Files:**
- Create: `src/tender_insights/template/slicer.py`
- Create: `src/tender_insights/template/planner.py`
- Test: `tests/tender_insights/unit/test_template_slicer.py`

- [ ] **Step 1: 写 slicer 边界测试**

```python
def test_slicer_rejects_out_of_range(tmp_path):
    # 用最小 OutputWorkspace + content.md
    hit = TemplateHitLLM(title="t", type="other", type_label="其他",
                         char_start=-1, char_end=10, confidence=0.5, source_excerpt="")
    assert slice_template_hit(workspace, content_md, hit) is None
```

- [ ] **Step 2: 实现 `slice_template_hit`**

返回 `tuple[str, int, int] | None`；内部 `slice_for_llm(workspace, content_md, start, end)`。

- [ ] **Step 3: 实现 `write_template_plan` / `run_template_plan_llm`**

`planner.py`：
- `build_deterministic_plan(content_md, outline, config) -> TemplatePlanFile`
- `run_template_plan_llm(client, plan, doc_title, config) -> TemplatePlanFile`（`TEMPLATE_PLAN_ENABLED` 为 false 时跳过）

LLM 调用：

```python
log_llm_prompt(call_type="template_plan", messages=messages, workspace=str(workspace.root), segment_id="plan")
extract_json_model(client, messages, TemplatePlanLLMResponse, log_context={"call_type": "template_plan", "segment_id": "plan"})
```

将 `notes`/`priority_sections` 写入 `plan.llm_notes` / `plan.priority_sections`。

- [ ] **Step 4: Commit**

```bash
git add src/tender_insights/template/slicer.py src/tender_insights/template/planner.py tests/
git commit -m "feat(template): add slicer and plan writer with optional LLM plan"
```

---

### Task 6: Extractor 编排（核心）

**Files:**
- Modify: `src/tender_insights/template/extractor.py`
- Test: `tests/tender_insights/integration/test_template_extract.py`

- [ ] **Step 1: 写端到端失败测试**

```python
@pytest.mark.asyncio
def test_extract_templates_llm_pipeline(tmp_path, sample_docx, monkeypatch):
    monkeypatch.setenv("TEMPLATE_PLAN_ENABLED", "false")
    from doc_chunk.api import run_pipeline
    ws_dir = tmp_path / "ws"
    run_pipeline(sample_docx, ws_dir, overwrite=True, skip_refine=True, skip_enrich=True)
    workspace = OutputWorkspace.open_existing(ws_dir)

    extract_json = json.dumps({
        "templates": [{
            "title": "授权书", "type": "authorization", "type_label": "授权书",
            "char_start": 0, "char_end": min(200, len(workspace.content_path.read_text(encoding="utf-8"))),
            "confidence": 0.9, "source_excerpt": "授权",
        }]
    })
    client = TemplateFakeLLM(
        plan_json='{"shard_count":1,"priority_sections":[],"notes":""}',
        extract_json=extract_json,
    )
    result = extract_templates_workspace(workspace, client)
    assert len(result.templates) >= 1
    assert (ws_dir / "templates" / "plan.json").exists()
    assert (ws_dir / "templates" / "index.json").exists()
```

- [ ] **Step 2: 重写 `extract_templates_workspace`**

```python
def extract_templates_workspace(
    workspace: OutputWorkspace,
    client: LLMClient,
    *,
    config: InsightsConfig | None = None,
    on_progress: Callable[[str, dict], None] | None = None,
) -> TemplatesIndexFile:
    config = config or InsightsConfig.from_env()
    content_md = workspace.content_path.read_text(encoding="utf-8")
    outline = OutlineTree.model_validate_json(workspace.outline_path.read_text(encoding="utf-8"))
    doc_title = _read_manifest_title(workspace)

    plan = build_deterministic_plan(content_md, outline, config)
    if config.template_plan_enabled:
        plan = run_template_plan_llm(workspace, client, plan, doc_title, config)
    _write_plan_json(workspace, plan)

    total_steps = plan.shard_count + 2
    _progress(on_progress, "template_plan", {"current": 0, "total": total_steps, "shard_count": plan.shard_count})

    all_hits: list[TemplateHitLLM] = []
    for i, shard in enumerate(plan.shards, start=1):
        _progress(on_progress, "template_extract", {"current": i, "total": total_steps, "shard_id": shard.shard_id, "detail": " > ".join(shard.section_path)})
        shard_md = slice_for_llm(workspace, content_md, shard.char_start, shard.char_end)
        messages = [
            {"role": "system", "content": TEMPLATE_EXTRACT_SYSTEM},
            {"role": "user", "content": build_extract_user_prompt(shard=shard, shard_markdown=shard_md)},
        ]
        log_llm_prompt(call_type="template_extract", messages=messages, workspace=str(workspace.root), segment_id=shard.shard_id, section_path=shard.section_path)
        try:
            batch = extract_json_model(client, messages, TemplateExtractResponse, max_retries=config.max_retries, log_context={"call_type": "template_extract", "segment_id": shard.shard_id})
            all_hits.extend(batch.templates)
        except LLMExtractionError:
            logger.warning("template extract failed for %s", shard.shard_id)

    _progress(on_progress, "template_merge", {"current": total_steps - 1, "total": total_steps})
    merged = dedupe_template_hits(all_hits)
    entries, warnings = _materialize_templates(workspace, content_md, merged, plan)

    result = TemplatesIndexFile(
        schema_version="1.1",
        templates=entries,
        plan_ref="templates/plan.json",
        shard_count=plan.shard_count,
    )
    write_json_artifact(workspace, "templates/index.json", result.model_dump(mode="json"), stage_name="template", output_key="templates")
    if not entries:
        _append_manifest_warning(workspace, "no templates identified")
    return result
```

`_materialize_templates`：遍历 merged hits，调用 `slice_template_hit`，写 `templates/{type}-{seq:03d}.md`，构建 `TemplateEntry(extraction_method="llm", shard_id=...)`。

删除主路径对 `detect_template_nodes` / `classifier` 的调用（文件保留）。

- [ ] **Step 3: 运行集成测试**

Run: `.venv/bin/pytest tests/tender_insights/integration/test_template_extract.py -v`

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/tender_insights/template/extractor.py tests/tender_insights/integration/test_template_extract.py
git commit -m "feat(template): replace keyword extractor with LLM plan-extract-merge pipeline"
```

---

### Task 7: API 层与 interpret 集成

**Files:**
- Modify: `src/tender_insights/api.py`
- Modify: `tests/tender_insights/unit/test_import.py`
- Modify: `viewer/viewer/services/interpret_pipeline.py`

- [ ] **Step 1: 添加 `run_template_job`**

```python
def run_template_job(
    workspace: OutputWorkspace,
    *,
    client: LLMClient | None = None,
    on_progress: Callable[[str, dict], None] | None = None,
    setup_logging: bool = True,
) -> TemplatesIndexFile:
    client = client or create_llm_client_from_env()
    if setup_logging:
        setup_interpret_llm_logging(workspace)
    return extract_templates_workspace(workspace, client, on_progress=on_progress)
```

- [ ] **Step 2: 修改 `run_interpret_job`**

将 `extract_templates_workspace(workspace, client)` 改为：

```python
if include_template:
    extract_templates_workspace(workspace, client, on_progress=_wrap_template_progress(on_progress))
```

或统一调用 `run_template_job` 的 extract 部分（避免重复 setup logging）。确保 template 阶段 `on_progress` stage 为 `template_plan`/`template_extract`/`template_merge` 而非旧 `template`。

- [ ] **Step 3: 更新 `interpret_pipeline.py`**

`run_job` / `run_interpret_on_workspace` 中，解读完成后不要再单独 `_report(stage="template")` 而不调 API——`run_interpret_job` 内 progress 应已覆盖。若 `run_interpret_job` 的 template progress 通过 `on_progress` 传出，Viewer 映射 stage：

```python
def _interpret_progress(stage, payload):
    if stage.startswith("template_"):
        # 映射到 job stage
        ...
```

- [ ] **Step 4: 更新 `test_interpret_pipeline.py`**

注入 `TemplateFakeLLM` 替代仅 `InterpretFakeLLM`，或扩展 `InterpretFakeLLM` 处理 template call_type。断言 `templates/index.json` 在 FakeLLM 提供 extract 响应时非空。

- [ ] **Step 5: 运行测试**

Run: `.venv/bin/pytest tests/tender_insights/unit/test_import.py viewer/tests/unit/test_interpret_pipeline.py -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/tender_insights/api.py viewer/viewer/services/interpret_pipeline.py viewer/tests/
git commit -m "feat(api): add run_template_job and wire template progress through interpret"
```

---

### Task 8: Viewer 后端（独立模版 job）

**Files:**
- Modify: `viewer/viewer/models.py`
- Modify: `viewer/viewer/services/interpret_job_registry.py`
- Modify: `viewer/viewer/routes/interpret.py`
- Modify: `viewer/viewer/services/interpret_pipeline.py`
- Test: `viewer/tests/api/test_interpret_api.py`

- [ ] **Step 1: 扩展 models**

`InterpretJobState.job_kind` 增加 `"template"`。

`stage` Literal 增加 `"template_plan"`, `"template_extract"`, `"template_merge"`（保留 `"template"` 兼容或移除）。

- [ ] **Step 2: 实现 `_start_session_template_job`**

仿 `_start_session_brief_job`：

```python
def _start_session_template_job(session_id: str, background_tasks: BackgroundTasks) -> InterpretUploadResponse:
    ...
    get_interpret_job_registry().create(job_id, session_id, dual_file=dual_file, job_kind="template")
    if _workspace_is_ready(workspace_dir):
        background_tasks.add_task(service.run_template_on_workspace, ...)
    else:
        background_tasks.add_task(service.run_template_job, ...)
```

- [ ] **Step 3: 路由**

```python
@router.post("/sessions/{session_id}/template", response_model=InterpretUploadResponse)
def run_template_on_session(session_id: str, background_tasks: BackgroundTasks) -> InterpretUploadResponse:
    return _start_session_template_job(session_id, background_tasks)
```

`_enqueue_upload_job` 的 `job_kind` 扩展为 `Literal["interpret", "brief", "template"]`。

- [ ] **Step 4: `run_template_on_workspace` / `run_template_job`**

```python
async def run_template_on_workspace(self, *, job_id, session_id, workspace_dir, dual_file=False):
    step_total = ...  # 先 open workspace 调 build_deterministic_plan 得 shard_count，或动态更新
    await asyncio.to_thread(run_template_job, ws, client=client, on_progress=_template_progress)
```

`_template_progress` 更新 `InterpretJobRegistry` 的 stage/message/step_current。

- [ ] **Step 5: API 测试**

```python
def test_run_template_on_existing_session(viewer_data_dir, pipeline_workspace):
    # 创建 interpret session 指向 pipeline_workspace
    resp = client.post(f"/api/interpret/sessions/{session_id}/template")
    assert resp.status_code == 200
    assert "job_id" in resp.json()
```

- [ ] **Step 6: 运行测试**

Run: `.venv/bin/pytest viewer/tests/api/test_interpret_api.py -v`

- [ ] **Step 7: Commit**

```bash
git add viewer/viewer/models.py viewer/viewer/routes/interpret.py viewer/viewer/services/
git commit -m "feat(viewer): add template extraction job API and pipeline service"
```

---

### Task 9: Viewer 前端

**Files:**
- Modify: `viewer/viewer/static/interpret.html`
- Modify: `viewer/viewer/static/interpret.js`
- Test: `viewer/tests/unit/test_interpret_static_assets.py`

- [ ] **Step 1: HTML 增加按钮**

在 `brief-btn` 旁增加：

```html
<button type="button" id="template-btn">提取模版</button>
```

- [ ] **Step 2: JS 阶段与事件**

```javascript
const TEMPLATE_ONLY_STAGES = ["pipeline_1", "pipeline_2", "merge", "template_plan", "template_extract", "template_merge"];
const STAGE_LABELS = {
  ...
  template_plan: "制定模版计划",
  template_extract: "提取模版",
  template_merge: "合并模版",
};
```

`template-btn` click handler 仿 `brief-btn`：

```javascript
result = await api(`/api/interpret/sessions/${sessionId}/template`, { method: "POST" });
// 或 upload?job_kind=template
```

`pollJob` 中：

```javascript
if (job.stage?.startsWith("template") || job.job_kind === "template") {
  await refreshLlmCalls(job.session_id, { render: state.activeTab === "llm" });
}
```

- [ ] **Step 3: 静态资源测试**

```python
def test_interpret_html_has_template_button():
    html = (STATIC / "interpret.html").read_text(encoding="utf-8")
    assert 'id="template-btn"' in html
    assert "提取模版" in html
```

- [ ] **Step 4: Commit**

```bash
git add viewer/viewer/static/interpret.html viewer/viewer/static/interpret.js viewer/tests/
git commit -m "feat(viewer): add standalone template extraction button and progress stages"
```

---

### Task 10: 粗 outline 集成 fixture 与文档

**Files:**
- Create: `tests/fixtures/template_coarse_outline/`（minimal content.md + outline.json）
- Modify: `tests/tender_insights/integration/test_template_extract.py`
- Modify: `.cursor/skills/tender-template/SKILL.md`

- [ ] **Step 1: 鼎信类 fixture**

`outline.json`：6 个一级节点，第四章 `char_start` 指向含 `# 授权书` / `# 声明函` 的 `content.md`。

FakeLLM `extract_json` 返回两个 hit 的全局坐标。

断言 `len(result.templates) == 2`。

- [ ] **Step 2: 全量测试**

Run: `.venv/bin/pytest tests/tender_insights/ viewer/tests/ -v --tb=short`

Expected: 全部 PASS

- [ ] **Step 3: 更新 tender-template SKILL**

说明新 pipeline、plan.json、`run_template_job`、Viewer 按钮、`TEMPLATE_*` 配置；标注旧关键词检测已废弃。

- [ ] **Step 4: Commit**

```bash
git add tests/ .cursor/skills/tender-template/SKILL.md
git commit -m "test(template): add coarse-outline fixture and update skill docs"
```

---

## Spec 覆盖自检

| Spec 章节 | Task |
|-----------|------|
| 分片三层回退 | Task 2 |
| LLM plan | Task 4, 5 |
| LLM extract + 全局坐标 | Task 4, 6 |
| 机械切片保真 | Task 5 |
| Merger | Task 3 |
| index v1.1 | Task 1, 6 |
| LLM 日志 | Task 5, 6 |
| 进度回调 | Task 6, 7, 8 |
| Viewer 按钮/API | Task 8, 9 |
| 开始解读末尾 | Task 7 |
| 配置 | Task 1 |
| 不测 interpretation.json | 全 pipeline 不 import interpret models |
| 错误处理（单片失败继续） | Task 6 try/except |

---

## 执行后验证清单

1. 对鼎信工作区重跑：`POST /api/interpret/sessions/{id}/template`
2. 检查 `templates/plan.json` shard 列表含第四章子 heading 片
3. 检查 `templates/index.json` 非空
4. 检查 `llm_calls.jsonl` 含 `template_plan`、`template_extract`
5. 「开始解读」完成后模版 Tab 有数据
