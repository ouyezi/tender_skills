# gen-catalog 节点完善两步化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `gen_catalog_node` 改为 Plan（评估是否需要优化）→ 条件 Apply（执行优化），共享 System + User 前缀以命中 prompt cache；`needs_optimization=false` 时跳过 Apply。

**Architecture:** 在 `gen_catalog/` 内新增 `BidOutlinePlanLLMResponse` 与统一 `GEN_CATALOG_NODE_SYSTEM`；`context.py` 提供共享前缀构建器；`extractor.py` 编排 plan/apply 两次 LLM 调用；FakeLLM 按 User 任务尾段分流；Viewer 补充 call_type 标签。

**Tech Stack:** Python 3.11+、Pydantic v2、pytest、`GenCatalogFakeLLM`、现有 `extract_json_model` / `log_llm_prompt`

**Spec:** `docs/superpowers/specs/2026-06-26-gen-catalog-node-refine-design.md`

---

## File Map

| File | Responsibility |
|------|----------------|
| `src/tender_insights/gen_catalog/models.py` | 新增 `BidOutlinePlanLLMResponse`；`GenCatalogSession.last_plan` |
| `src/tender_insights/gen_catalog/prompts.py` | `GEN_CATALOG_NODE_SYSTEM`；删除 `GEN_CATALOG_REFINE_SYSTEM` |
| `src/tender_insights/gen_catalog/context.py` | 共享前缀 + plan/apply user prompt；删除 `build_refine_user_prompt` |
| `src/tender_insights/gen_catalog/extractor.py` | `run_gen_catalog_node_plan` / `run_gen_catalog_node_apply`；编排入口 |
| `tests/helpers/gen_catalog_fake_llm.py` | 按任务尾段返回 plan 或 apply JSON |
| `tests/tender_insights/unit/test_gen_catalog_context.py` | 新建：前缀一致性单元测试 |
| `tests/tender_insights/unit/test_gen_catalog.py` | 更新 prompt / 集成测试 |
| `viewer/viewer/static/gen-catalog.js` | `formatLlmCallLabel` 支持 plan/apply call_type |

---

### Task 1: Plan 响应模型与 Session 扩展

**Files:**
- Modify: `src/tender_insights/gen_catalog/models.py`
- Test: `tests/tender_insights/unit/test_gen_catalog.py`

- [ ] **Step 1: Write the failing test**

在 `tests/tender_insights/unit/test_gen_catalog.py` 末尾追加：

```python
def test_bid_outline_plan_requires_refinement_plan_when_optimizing() -> None:
    from pydantic import ValidationError

    from tender_insights.gen_catalog.models import BidOutlinePlanLLMResponse

    BidOutlinePlanLLMResponse(needs_optimization=False, refinement_plan="无需调整")
    with pytest.raises(ValidationError):
        BidOutlinePlanLLMResponse(needs_optimization=True, refinement_plan="")


def test_gen_catalog_session_last_plan_roundtrip(tmp_path: Path) -> None:
    ws = _open_ws(_minimal_interpretation(tmp_path))
    session = GenCatalogSession(
        mode="step",
        status="paused",
        last_plan={"node_id": "bid-001", "needs_optimization": False, "refinement_plan": "ok"},
    )
    save_session(ws, session)
    loaded = load_session(ws)
    assert loaded.last_plan is not None
    assert loaded.last_plan["node_id"] == "bid-001"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/tender_insights/unit/test_gen_catalog.py::test_bid_outline_plan_requires_refinement_plan_when_optimizing tests/tender_insights/unit/test_gen_catalog.py::test_gen_catalog_session_last_plan_roundtrip -v`

Expected: FAIL — `BidOutlinePlanLLMResponse` 不存在或 `last_plan` 字段缺失

- [ ] **Step 3: Implement models**

在 `src/tender_insights/gen_catalog/models.py` 中：

1. 顶部增加 `from pydantic import BaseModel, Field, model_validator`（若已有 BaseModel/Field 则只加 `model_validator`）
2. 在 `BidOutlineLLMResponse` **之前**插入：

```python
class BidOutlinePlanLLMResponse(BaseModel):
    needs_optimization: bool
    refinement_plan: str = ""

    @model_validator(mode="after")
    def refinement_plan_required_when_optimizing(self) -> BidOutlinePlanLLMResponse:
        if self.needs_optimization and not self.refinement_plan.strip():
            raise ValueError("refinement_plan required when needs_optimization is true")
        return self
```

3. 在 `GenCatalogSession` 中增加：

```python
last_plan: dict | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/tender_insights/unit/test_gen_catalog.py::test_bid_outline_plan_requires_refinement_plan_when_optimizing tests/tender_insights/unit/test_gen_catalog.py::test_gen_catalog_session_last_plan_roundtrip -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tender_insights/gen_catalog/models.py tests/tender_insights/unit/test_gen_catalog.py
git commit -m "feat(gen-catalog): add plan response model and session last_plan"
```

---

### Task 2: 统一 System Prompt

**Files:**
- Modify: `src/tender_insights/gen_catalog/prompts.py`
- Test: `tests/tender_insights/unit/test_gen_catalog.py`

- [ ] **Step 1: Write the failing test**

将 `test_prompts_are_static` 替换为：

```python
def test_prompts_are_static() -> None:
    from tender_insights.gen_catalog.prompts import GEN_CATALOG_INITIAL_SYSTEM, GEN_CATALOG_NODE_SYSTEM

    assert "JSON" in GEN_CATALOG_INITIAL_SYSTEM
    assert "bid-root" in GEN_CATALOG_NODE_SYSTEM
    assert "needs_optimization" not in GEN_CATALOG_NODE_SYSTEM
    assert "refinement_plan" not in GEN_CATALOG_NODE_SYSTEM
```

同时删除文件顶部对 `GEN_CATALOG_REFINE_SYSTEM` 的 import。

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/tender_insights/unit/test_gen_catalog.py::test_prompts_are_static -v`

Expected: FAIL — `GEN_CATALOG_NODE_SYSTEM` 未定义

- [ ] **Step 3: Replace refine system with node system**

在 `src/tender_insights/gen_catalog/prompts.py` 中，将 `GEN_CATALOG_REFINE_SYSTEM` 整段替换为：

```python
GEN_CATALOG_NODE_SYSTEM = """你是投标目录规划专家。用户消息包含招标概要、当前目录树与招标文件摘录；
具体本轮任务与输出格式见用户消息末尾「## 任务」节。

通用规则：
1. 目录节点 id 使用 bid-NNN 格式，根节点 id=bid-root；禁止 dir-* 前缀。
2. 涉及返回目录树时，必须返回完整 outline（替换整棵树），保持已有节点 id 不变。
3. 不得遗漏 mandatory 章节，不得破坏整体结构。
4. 严格遵循用户消息中的招标摘录与任务说明。"""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/tender_insights/unit/test_gen_catalog.py::test_prompts_are_static -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tender_insights/gen_catalog/prompts.py tests/tender_insights/unit/test_gen_catalog.py
git commit -m "feat(gen-catalog): add unified GEN_CATALOG_NODE_SYSTEM prompt"
```

---

### Task 3: User Prompt 构建器（共享前缀）

**Files:**
- Modify: `src/tender_insights/gen_catalog/context.py`
- Create: `tests/tender_insights/unit/test_gen_catalog_context.py`

- [ ] **Step 1: Write the failing tests**

创建 `tests/tender_insights/unit/test_gen_catalog_context.py`：

```python
from __future__ import annotations

import json

from tender_insights.brief.models import TenderBriefFields, TenderBriefFile
from tender_insights.gen_catalog.context import (
    build_node_apply_user_prompt,
    build_node_plan_user_prompt,
    build_node_shared_user_prefix,
)
from tender_insights.gen_catalog.models import BidOutlineNode


def _root() -> BidOutlineNode:
    return BidOutlineNode(
        id="bid-root",
        title="投标文件",
        level=0,
        order=0,
        children=[
            BidOutlineNode(id="bid-001", title="投标函", level=1, order=1),
        ],
    )


def _brief() -> TenderBriefFile:
    return TenderBriefFile(
        source_workspace="/tmp/ws",
        summary_text="概要",
        fields=TenderBriefFields(
            issuer_company="甲公司",
            procurement_subject="采购标的",
            budget_info="100万",
            qualification_requirements="资质A",
            key_timelines="30天",
        ),
    )


def test_shared_prefix_omits_brief_when_none() -> None:
    text = build_node_shared_user_prefix(None, _root(), "摘录正文")
    assert "## 招标概要" not in text
    assert "## 当前完整目录树" in text
    assert "## 招标文件相关摘录" in text
    assert "摘录正文" in text


def test_plan_and_apply_share_identical_prefix() -> None:
    root = _root()
    brief = _brief()
    excerpt = "投标函须盖章"
    plan = build_node_plan_user_prompt(brief, root, excerpt)
    apply = build_node_apply_user_prompt(brief, root, excerpt, "补充子节")
    prefix = build_node_shared_user_prefix(brief, root, excerpt)
    assert plan.startswith(prefix)
    assert apply.startswith(prefix)
    assert plan[len(prefix) :].startswith("\n\n## 任务：目录优化评估")
    assert "## 优化或细化方案" in apply[len(prefix) :]
    assert "补充子节" in apply


def test_shared_prefix_json_format() -> None:
    brief = _brief()
    text = build_node_shared_user_prefix(brief, _root(), "x")
    assert "## 招标概要（tender_brief）" in text
    payload = text.split("## 招标概要（tender_brief）\n", 1)[1].split("\n\n## 当前完整目录树", 1)[0]
    data = json.loads(payload)
    assert data["summary_text"] == "概要"
    assert "issuer_company" in data["fields"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/tender_insights/unit/test_gen_catalog_context.py -v`

Expected: FAIL — import 错误，函数未定义

- [ ] **Step 3: Implement context builders**

在 `src/tender_insights/gen_catalog/context.py` 中：

1. 增加 `from tender_insights.brief.models import TenderBriefFile`
2. 删除 `build_refine_user_prompt` 与 `_find_node_title`（若无其他引用）
3. 在 `build_initial_user_prompt` 之后追加：

```python
def build_node_shared_user_prefix(
    brief: TenderBriefFile | None,
    root: BidOutlineNode,
    excerpt: str,
) -> str:
    parts: list[str] = []
    if brief is not None:
        parts.extend(
            [
                "## 招标概要（tender_brief）",
                json.dumps(
                    {
                        "summary_text": brief.summary_text,
                        "fields": brief.fields.model_dump(),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            ]
        )
    parts.extend(
        [
            "## 当前完整目录树",
            json.dumps(root.model_dump(), ensure_ascii=False, indent=2),
            "## 招标文件相关摘录",
            excerpt,
        ]
    )
    return "\n\n".join(parts)


def build_node_plan_task_suffix() -> str:
    return """## 任务：目录优化评估

分析「招标文件相关摘录」是否要求对「当前完整目录树」进行优化或细化。

只输出 JSON：
{"needs_optimization": <bool>, "refinement_plan": "<方案说明>"}

- needs_optimization=false：无需改动，refinement_plan 简述原因
- needs_optimization=true：refinement_plan 描述具体动作（合并、拆分、补充子节等）
- 禁止输出 outline 字段"""


def build_node_apply_task_suffix(refinement_plan: str) -> str:
    return f"""## 优化或细化方案
{refinement_plan}

## 任务：执行目录更新

根据上述方案更新完整目录树。

只输出 JSON：
{{"outline": <BidOutlineNode>, "changes_summary": "<本步调整说明>"}}

- outline 为完整树，根 id=bid-root，已有 bid-NNN id 保持不变
- 仅执行方案中描述的调整，不超出方案范围"""


def build_node_plan_user_prompt(
    brief: TenderBriefFile | None,
    root: BidOutlineNode,
    excerpt: str,
) -> str:
    return build_node_shared_user_prefix(brief, root, excerpt) + "\n\n" + build_node_plan_task_suffix()


def build_node_apply_user_prompt(
    brief: TenderBriefFile | None,
    root: BidOutlineNode,
    excerpt: str,
    refinement_plan: str,
) -> str:
    return (
        build_node_shared_user_prefix(brief, root, excerpt)
        + "\n\n"
        + build_node_apply_task_suffix(refinement_plan)
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/tender_insights/unit/test_gen_catalog_context.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tender_insights/gen_catalog/context.py tests/tender_insights/unit/test_gen_catalog_context.py
git commit -m "feat(gen-catalog): add shared-prefix plan/apply user prompts"
```

---

### Task 4: Extractor 两步编排

**Files:**
- Modify: `src/tender_insights/gen_catalog/extractor.py`

- [ ] **Step 1: Write the failing integration tests**

在 `tests/tender_insights/unit/test_gen_catalog.py` 追加：

```python
def _write_brief(ws_root: Path) -> None:
    from tender_insights.brief.models import TenderBriefFields, TenderBriefFile

    brief = TenderBriefFile(
        source_workspace=str(ws_root),
        summary_text="招标概要",
        fields=TenderBriefFields(
            issuer_company="甲",
            procurement_subject="标的",
            budget_info="预算",
            qualification_requirements="资质",
            key_timelines="工期",
        ),
    )
    (ws_root / "tender_brief.json").write_text(brief.model_dump_json(), encoding="utf-8")


def test_gen_catalog_node_skips_apply_when_no_optimization(tmp_path: Path) -> None:
    ws_root = _minimal_interpretation(tmp_path)
    _write_brief(ws_root)
    ws = _open_ws(ws_root)
    client = GenCatalogFakeLLM()
    gen_catalog_workspace(ws, client, mode="step", run_limit=2)
    session = load_session(ws)
    assert "bid-001" in session.completed_steps
    assert session.last_plan is not None
    assert session.last_plan["needs_optimization"] is False
    node_calls = [c for c in client.calls if "目录优化评估" in str(c["messages"])]
    apply_calls = [c for c in client.calls if "执行目录更新" in str(c["messages"])]
    assert len(node_calls) >= 1
    assert len(apply_calls) == 0


def test_gen_catalog_node_apply_updates_tree(tmp_path: Path) -> None:
    ws_root = _minimal_interpretation(tmp_path)
    _write_brief(ws_root)
    ws = _open_ws(ws_root)
    client = GenCatalogFakeLLM()
    result = gen_catalog_workspace(ws, client, mode="auto")
    assert result.status == "awaiting_accept"
    tech = next(c for c in result.root.children if c.id == "bid-002")
    assert "得分点" in tech.writing_spec
    plan_calls = sum(1 for c in client.calls if "目录优化评估" in str(c["messages"]))
    apply_calls = sum(1 for c in client.calls if "执行目录更新" in str(c["messages"]))
    assert plan_calls == 2
    assert apply_calls == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/tender_insights/unit/test_gen_catalog.py::test_gen_catalog_node_skips_apply_when_no_optimization tests/tender_insights/unit/test_gen_catalog.py::test_gen_catalog_node_apply_updates_tree -v`

Expected: FAIL — FakeLLM / extractor 仍为单步逻辑

- [ ] **Step 3: Refactor extractor**

在 `src/tender_insights/gen_catalog/extractor.py` 中：

**Imports 变更：**

```python
from tender_insights.gen_catalog.context import (
    build_initial_user_prompt,
    build_node_apply_user_prompt,
    build_node_plan_user_prompt,
)
from tender_insights.gen_catalog.models import (
    BidOutlineFile,
    BidOutlineLLMResponse,
    BidOutlineNode,
    BidOutlinePlanLLMResponse,
    GenCatalogSession,
)
from tender_insights.gen_catalog.prompts import GEN_CATALOG_INITIAL_SYSTEM, GEN_CATALOG_NODE_SYSTEM
```

删除 `build_refine_user_prompt`、`GEN_CATALOG_REFINE_SYSTEM` 引用。

**新增 `run_gen_catalog_node_plan`：**

```python
def run_gen_catalog_node_plan(
    workspace: OutputWorkspace,
    client: LLMClient,
    *,
    report: PrerequisiteReport,
    draft: BidOutlineFile,
    node_id: str,
    excerpt: str,
    title: str,
    config: InsightsConfig | None = None,
) -> BidOutlinePlanLLMResponse:
    config = config or InsightsConfig.from_env()
    user_content = build_node_plan_user_prompt(report.brief, draft.root, excerpt)
    messages = [
        {"role": "system", "content": GEN_CATALOG_NODE_SYSTEM},
        {"role": "user", "content": user_content},
    ]
    log_llm_prompt(
        call_type="gen_catalog_node_plan",
        messages=messages,
        workspace=str(workspace.root),
        segment_id=node_id,
        section_path=[title],
    )
    return extract_json_model(
        client,
        messages,
        BidOutlinePlanLLMResponse,
        max_retries=config.max_retries,
        log_context={"call_type": "gen_catalog_node_plan", "segment_id": node_id},
    )
```

**新增 `run_gen_catalog_node_apply`：**

```python
def run_gen_catalog_node_apply(
    workspace: OutputWorkspace,
    client: LLMClient,
    *,
    report: PrerequisiteReport,
    draft: BidOutlineFile,
    node_id: str,
    excerpt: str,
    title: str,
    refinement_plan: str,
    config: InsightsConfig | None = None,
) -> BidOutlineLLMResponse:
    config = config or InsightsConfig.from_env()
    user_content = build_node_apply_user_prompt(
        report.brief, draft.root, excerpt, refinement_plan
    )
    messages = [
        {"role": "system", "content": GEN_CATALOG_NODE_SYSTEM},
        {"role": "user", "content": user_content},
    ]
    log_llm_prompt(
        call_type="gen_catalog_node_apply",
        messages=messages,
        workspace=str(workspace.root),
        segment_id=node_id,
        section_path=[title],
    )
    response = extract_json_model(
        client,
        messages,
        BidOutlineLLMResponse,
        max_retries=config.max_retries,
        log_context={"call_type": "gen_catalog_node_apply", "segment_id": node_id},
    )
    normalize_outline_ids(response.outline)
    if response.outline.id != "bid-root":
        raise ValueError("outline root id must be bid-root")
    return response
```

**重写 `run_gen_catalog_node` 为编排入口：**

```python
def run_gen_catalog_node(
    workspace: OutputWorkspace,
    client: LLMClient,
    *,
    report: PrerequisiteReport,
    draft: BidOutlineFile,
    session: GenCatalogSession,
    node_id: str,
    config: InsightsConfig | None = None,
) -> BidOutlineFile:
    config = config or InsightsConfig.from_env()
    node = find_node(draft.root, node_id)
    title = node.title if node is not None else node_id
    excerpt = pick_node_excerpt(
        _source_markdown(workspace),
        node_title=title,
        max_chars=config.gen_catalog_excerpt_max_chars,
        min_chars=config.gen_catalog_excerpt_min_chars,
    )

    plan = run_gen_catalog_node_plan(
        workspace,
        client,
        report=report,
        draft=draft,
        node_id=node_id,
        excerpt=excerpt,
        title=title,
        config=config,
    )
    session.last_plan = {
        "node_id": node_id,
        "needs_optimization": plan.needs_optimization,
        "refinement_plan": plan.refinement_plan,
    }
    session.current_node_id = node_id
    session.current_node_title = title

    if plan.needs_optimization:
        response = run_gen_catalog_node_apply(
            workspace,
            client,
            report=report,
            draft=draft,
            node_id=node_id,
            excerpt=excerpt,
            title=title,
            refinement_plan=plan.refinement_plan,
            config=config,
        )
        draft = _build_draft_shell(
            report,
            response.outline,
            mode=session.mode,
            status=draft.status,
            step_index=session.step_index + 1,
            step_total=session.step_total,
        )
        save_draft(workspace, draft)

    session.step_index += 1
    session.completed_steps.append(node_id)
    save_session(workspace, session)
    return draft
```

**更新 `gen_catalog_workspace` 进度 detail（约 L292 行 `_emit_progress` 调用前）：**

在调用 `run_gen_catalog_node` 之前可先 emit plan 评估消息；或在 `run_gen_catalog_node` 返回后根据 `session.last_plan` 设置 detail。最小改法：保持现有 `_emit_progress` message，将 `detail` 改为：

```python
detail=f"节点 {session.step_index} / {session.step_total}",
```

（进度语义不变；详细 plan/apply 状态由 `last_plan` 与 llm_calls 展示。）

- [ ] **Step 4: Run tests — expect still failing until Task 5**

Run: `.venv/bin/pytest tests/tender_insights/unit/test_gen_catalog.py::test_gen_catalog_node_skips_apply_when_no_optimization tests/tender_insights/unit/test_gen_catalog.py::test_gen_catalog_node_apply_updates_tree -v`

Expected: FAIL — FakeLLM 未更新

- [ ] **Step 5: Commit extractor (optional intermediate; or combine with Task 5)**

```bash
git add src/tender_insights/gen_catalog/extractor.py tests/tender_insights/unit/test_gen_catalog.py
git commit -m "feat(gen-catalog): orchestrate node plan and conditional apply"
```

---

### Task 5: 更新 GenCatalogFakeLLM

**Files:**
- Modify: `tests/helpers/gen_catalog_fake_llm.py`

- [ ] **Step 1: Replace FakeLLM implementation**

将整个 `complete_with_meta` 替换为：

```python
class GenCatalogFakeLLM(FakeLLMClient):
    def complete_with_meta(self, messages, *, response_format="text", timeout=None):
        user = "\n".join(str(m.get("content", "")) for m in messages if m.get("role") == "user")

        if "目录优化评估" in user:
            node_id = "bid-002" if "bid-002" in user else "bid-001"
            if node_id == "bid-002":
                payload = {
                    "needs_optimization": True,
                    "refinement_plan": "补充技术方案撰写规范与得分点对应说明",
                }
            else:
                payload = {
                    "needs_optimization": False,
                    "refinement_plan": "摘录未要求调整投标函结构",
                }
        elif "执行目录更新" in user:
            outline = json.loads(json.dumps(_INITIAL["outline"]))
            for child in outline["children"]:
                if child["id"] == "bid-002":
                    child["writing_spec"] = "详述技术路线与得分点对应"
            payload = {"outline": outline, "changes_summary": "refined"}
        else:
            payload = _INITIAL

        text = json.dumps(payload, ensure_ascii=False)
        self.calls.append({"messages": messages, "response_format": response_format, "timeout": timeout})
        return LLMCompletionResult(text=text)
```

- [ ] **Step 2: Run integration tests**

Run: `.venv/bin/pytest tests/tender_insights/unit/test_gen_catalog.py -v`

Expected: PASS（全部 gen_catalog 单测）

- [ ] **Step 3: Commit**

```bash
git add tests/helpers/gen_catalog_fake_llm.py
git commit -m "test(gen-catalog): update FakeLLM for plan/apply two-step flow"
```

---

### Task 6: Viewer LLM 调用标签

**Files:**
- Modify: `viewer/viewer/static/gen-catalog.js`
- Test: `viewer/tests/unit/test_gen_catalog_static_assets.py`

- [ ] **Step 1: Write the failing test**

在 `viewer/tests/unit/test_gen_catalog_static_assets.py` 追加：

```python
def test_gen_catalog_js_labels_plan_apply() -> None:
    js = (Path(__file__).resolve().parents[2] / "viewer/static/gen-catalog.js").read_text(encoding="utf-8")
    assert "gen_catalog_node_plan" in js
    assert "gen_catalog_node_apply" in js
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest viewer/tests/unit/test_gen_catalog_static_assets.py::test_gen_catalog_js_labels_plan_apply -v`

Expected: FAIL

- [ ] **Step 3: Update formatLlmCallLabel**

在 `viewer/viewer/static/gen-catalog.js` 的 `formatLlmCallLabel` 中，在 `gen_catalog_initial` 分支之后插入：

```javascript
  if (type === "gen_catalog_node_plan") {
    const seg = call.segment_id || "";
    const title = call.section_path?.[0] || findNodeTitle(state.draft?.root, seg) || "";
    return title ? `评估章节「${title}」（${seg}）` : `评估章节（${seg}）`;
  }
  if (type === "gen_catalog_node_apply") {
    const seg = call.segment_id || "";
    const title = call.section_path?.[0] || findNodeTitle(state.draft?.root, seg) || "";
    return title ? `执行优化「${title}」（${seg}）` : `执行优化（${seg}）`;
  }
```

保留原 `gen_catalog_node` 分支作为向后兼容（历史 llm_calls.jsonl）。

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest viewer/tests/unit/test_gen_catalog_static_assets.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add viewer/viewer/static/gen-catalog.js viewer/tests/unit/test_gen_catalog_static_assets.py
git commit -m "feat(viewer): label gen-catalog plan/apply LLM calls"
```

---

### Task 7: 全量回归与母规格注记

**Files:**
- Modify: `docs/superpowers/specs/2026-06-25-tender-generate-design.md`（§4.2 / §5.1 加注）

- [ ] **Step 1: Run full regression**

Run:

```bash
.venv/bin/pytest tests/tender_insights/unit/test_gen_catalog.py tests/tender_insights/unit/test_gen_catalog_context.py viewer/tests/unit/test_gen_catalog_static_assets.py viewer/tests/api/test_gen_catalog_api.py -v
```

Expected: PASS

- [ ] **Step 2: Add cross-reference note to parent spec**

在 `docs/superpowers/specs/2026-06-25-tender-generate-design.md` 的 §4.2 流水线 `Step 1…N` 段落后追加一句：

```markdown
> **2026-06-26 更新：** 节点完善步已升级为 Plan → 条件 Apply 两步流程，详见 `docs/superpowers/specs/2026-06-26-gen-catalog-node-refine-design.md`。
```

在 §5.1 表格 `节点完善` 行 `call_type` 改为 `gen_catalog_node_plan` / `gen_catalog_node_apply`。

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-06-25-tender-generate-design.md
git commit -m "docs: cross-reference gen-catalog node refine v2 in parent spec"
```

---

## Spec Self-Review（计划自检）

| Spec 要求 | 对应 Task |
|-----------|-----------|
| Plan → 条件 Apply 流水线 | Task 4 |
| 单一 System + 共享 User 前缀 | Task 2, 3 |
| `needs_optimization=false` 跳过 apply | Task 4, 5 |
| 仅 tender_brief 作概要 | Task 3 (`report.brief`) |
| `BidOutlinePlanLLMResponse` + validator | Task 1 |
| `GenCatalogSession.last_plan` | Task 1, 4 |
| call_type plan/apply | Task 4 |
| FakeLLM 分流 | Task 5 |
| Viewer 标签 | Task 6 |
| 测试覆盖前缀一致性 | Task 3 |
| initial 步不变 | 未修改 `run_gen_catalog_initial` |

无 TBD / 占位步骤。

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-26-gen-catalog-node-refine.md`. Two execution options:

**1. Subagent-Driven (recommended)** — 每个 Task 派发独立 subagent，任务间做审查，迭代快

**2. Inline Execution** — 在本会话用 executing-plans 按 Task 批量执行，检查点处暂停审阅

Which approach?
