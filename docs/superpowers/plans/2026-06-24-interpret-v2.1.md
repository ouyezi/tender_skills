# interpret v2.1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade `tender_insights.interpret` to schema 1.2 with two-level scoring trees, inferred directory requirements, and stronger prompts — without adding LLM calls.

**Architecture:** Extend Pydantic models; rewrite segment/overview prompts with section-path appendices; replace flat scoring dedupe with `merge_scoring_items`; add `normalize_directory_requirements` before overview; recursively flatten directory `structure` into `directory_outline`. Pipeline remains N segment LLM + 1 overview LLM.

**Tech Stack:** Python 3.11+, Pydantic v2, pytest, existing `FakeLLMClient`

**Spec:** `docs/superpowers/specs/2026-06-24-interpret-v2.1-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `src/tender_insights/interpret/models.py` | Modify | `ScoringCriterionNode`, `ScoringItem.children`, `DirectoryRequirement.inferred`, schema 1.2 |
| `src/tender_insights/interpret/merger.py` | Modify | `merge_scoring_items`, `normalize_directory_requirements` |
| `src/tender_insights/interpret/prompts.py` | Modify | Rewritten `SYSTEM_PROMPT`, segment appendices, overview prompts |
| `src/tender_insights/interpret/directory_outline.py` | Modify | Recursive `structure` flattening, `inferred` confidence |
| `src/tender_insights/interpret/extractor.py` | Modify | Wire new merge/normalize; anchor children |
| `src/tender_insights/interpret/overview.py` | Modify | Payload includes `children`, `inferred` |
| `tests/tender_insights/unit/test_interpret_models.py` | Modify | Roundtrip with children + inferred |
| `tests/tender_insights/unit/test_interpret_merger.py` | Modify | Scoring merge + directory normalize tests |
| `tests/tender_insights/unit/test_directory_outline.py` | Modify | Nested structure + inferred confidence |
| `tests/tender_insights/unit/test_interpret_prompts.py` | Create | Segment appendix keyword tests |
| `tests/tender_insights/contract/test_interpretation_schema.py` | Modify | schema 1.2 fixture + 1.1 backward compat |
| `tests/tender_insights/integration/test_pipeline_interpret.py` | Modify | Children in FakeLLM response |
| `.cursor/skills/tender-interpret/SKILL.md` | Modify | Document schema 1.2 fields |
| `README.md` | Modify | schema 1.2 mention (brief) |

---

### Task 1: Schema 1.2 models

**Files:**
- Modify: `src/tender_insights/interpret/models.py`
- Test: `tests/tender_insights/unit/test_interpret_models.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/tender_insights/unit/test_interpret_models.py`:

```python
from tender_insights.interpret.models import ScoringCriterionNode


def test_scoring_item_with_children_roundtrip() -> None:
    child = ScoringCriterionNode(
        id="sc-001-01",
        title="方案完整性",
        max_score=10.0,
        score_range="0-10",
        criteria="方案覆盖全部要求得10分",
        source_excerpt="原文",
    )
    payload = InterpretationFile(
        source_workspace="/tmp/ws",
        overview=_overview(),
        scoring_items=[
            ScoringItem(
                id="sc-001",
                title="技术部分",
                summary="技术评分",
                max_score=40.0,
                weight="40%",
                criteria="大类说明",
                children=[child],
                source_excerpt="技术40分",
                section_path=["第二章 响应人须知"],
                confidence=0.9,
            )
        ],
    )
    restored = InterpretationFile.model_validate_json(payload.model_dump_json())
    assert restored.schema_version == "1.2"
    assert len(restored.scoring_items[0].children) == 1
    assert restored.scoring_items[0].children[0].score_range == "0-10"


def test_directory_requirement_inferred_default_false() -> None:
    dr = DirectoryRequirement(
        id="dr-001",
        title="组成",
        required_sections=["投标函"],
        mandatory=True,
        source_excerpt="x",
        section_path=[],
        confidence=0.8,
    )
    assert dr.inferred is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/tender_insights/unit/test_interpret_models.py::test_scoring_item_with_children_roundtrip -v`

Expected: FAIL (`ScoringCriterionNode` or `children` not defined, or `schema_version` not 1.2)

- [ ] **Step 3: Implement models**

In `src/tender_insights/interpret/models.py`, add before `ScoringItem`:

```python
class ScoringCriterionNode(BaseModel):
    id: str
    title: str
    max_score: float | None = None
    score_range: str | None = None
    criteria: str
    source_excerpt: str
```

Update `ScoringItem`:

```python
class ScoringItem(BaseModel):
    id: str
    title: str
    summary: str
    max_score: float | None = None
    weight: str | None = None
    criteria: str
    children: list[ScoringCriterionNode] = Field(default_factory=list)
    source_excerpt: str
    section_path: list[str]
    char_start: int | None = None
    char_end: int | None = None
    confidence: float = Field(ge=0.0, le=1.0)
```

Update `DirectoryRequirement`:

```python
class DirectoryRequirement(BaseModel):
    id: str
    title: str
    required_sections: list[str]
    mandatory: bool
    inferred: bool = False
    structure: list[DirectoryStructureNode] = Field(default_factory=list)
    ...
```

Update `InterpretationFile`:

```python
class InterpretationFile(InterpretationLLMResponse):
    schema_version: Literal["1.0", "1.1", "1.2"] = "1.2"
    ...
```

Add at bottom:

```python
ScoringCriterionNode.model_rebuild()
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/tender_insights/unit/test_interpret_models.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tender_insights/interpret/models.py tests/tender_insights/unit/test_interpret_models.py
git commit -m "feat(interpret): add schema 1.2 scoring children and directory inferred flag"
```

---

### Task 2: Scoring merge logic

**Files:**
- Modify: `src/tender_insights/interpret/merger.py`
- Test: `tests/tender_insights/unit/test_interpret_merger.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/tender_insights/unit/test_interpret_merger.py`:

```python
from tender_insights.interpret.merger import merge_scoring_items
from tender_insights.interpret.models import ScoringCriterionNode, ScoringItem


def _scoring(title: str, *, max_score: float | None = None, children: list[ScoringCriterionNode] | None = None) -> ScoringItem:
    return ScoringItem(
        id="sc-x",
        title=title,
        summary="s",
        max_score=max_score,
        criteria="c",
        children=children or [],
        source_excerpt="ex",
        section_path=[],
        confidence=0.9,
    )


def test_merge_scoring_items_unions_children_same_parent() -> None:
    items = [
        _scoring(
            "技术部分",
            max_score=40.0,
            children=[
                ScoringCriterionNode(
                    id="sc-001-01", title="方案完整性", criteria="a", source_excerpt="a"
                )
            ],
        ),
        _scoring(
            "技术部分",
            max_score=40.0,
            children=[
                ScoringCriterionNode(
                    id="sc-001-02", title="人员配置", criteria="b", source_excerpt="b"
                )
            ],
        ),
    ]
    out = merge_scoring_items(items)
    assert len(out) == 1
    titles = {c.title for c in out[0].children}
    assert titles == {"方案完整性", "人员配置"}


def test_merge_scoring_items_prefers_longer_child_criteria() -> None:
    items = [
        _scoring(
            "商务部分",
            children=[
                ScoringCriterionNode(
                    id="1", title="报价", criteria="短", source_excerpt="x"
                )
            ],
        ),
        _scoring(
            "商务部分",
            children=[
                ScoringCriterionNode(
                    id="2", title="报价", criteria="更长的评分细则说明", source_excerpt="y"
                )
            ],
        ),
    ]
    out = merge_scoring_items(items)
    assert len(out[0].children) == 1
    assert out[0].children[0].criteria == "更长的评分细则说明"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/tender_insights/unit/test_interpret_merger.py::test_merge_scoring_items_unions_children_same_parent -v`

Expected: FAIL (`merge_scoring_items` not defined)

- [ ] **Step 3: Implement merge_scoring_items**

Append to `src/tender_insights/interpret/merger.py`:

```python
from tender_insights.interpret.models import ScoringCriterionNode, ScoringItem


def _child_score(child: ScoringCriterionNode) -> tuple[int, float]:
    return len(child.criteria or ""), len(child.source_excerpt or "")


def _merge_children(existing: list[ScoringCriterionNode], incoming: list[ScoringCriterionNode]) -> list[ScoringCriterionNode]:
    best: dict[str, ScoringCriterionNode] = {}
    for child in [*existing, *incoming]:
        key = child.title.strip().lower()
        if not key:
            key = f"__empty__:{child.id}"
        prev = best.get(key)
        if prev is None or _child_score(child) > _child_score(prev):
            best[key] = child
    return list(best.values())


def merge_scoring_items(items: list[ScoringItem]) -> list[ScoringItem]:
    merged: dict[tuple[str, float | None], ScoringItem] = {}
    order: list[tuple[str, float | None]] = []
    for item in items:
        key = (item.title.strip().lower(), item.max_score)
        if key not in merged:
            merged[key] = item.model_copy(deep=True)
            order.append(key)
            continue
        existing = merged[key]
        if _score(item) > _score(existing):
            existing.summary = item.summary
            existing.criteria = item.criteria
            existing.weight = item.weight or existing.weight
            existing.source_excerpt = item.source_excerpt
            existing.confidence = item.confidence
            existing.section_path = item.section_path or existing.section_path
        existing.children = _merge_children(existing.children, item.children)
    return [merged[k] for k in order]
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/tender_insights/unit/test_interpret_merger.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tender_insights/interpret/merger.py tests/tender_insights/unit/test_interpret_merger.py
git commit -m "feat(interpret): merge scoring items with children union"
```

---

### Task 3: Directory normalization

**Files:**
- Modify: `src/tender_insights/interpret/merger.py`
- Test: `tests/tender_insights/unit/test_interpret_merger.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/tender_insights/unit/test_interpret_merger.py`:

```python
from tender_insights.interpret.merger import normalize_directory_requirements
from tender_insights.interpret.models import DirectoryRequirement


def test_normalize_directory_keeps_explicit_structure() -> None:
    explicit = DirectoryRequirement(
        id="dr-1",
        title="投标文件组成",
        required_sections=[],
        mandatory=True,
        inferred=False,
        structure=[DirectoryStructureNode(order=1, title="投标函", mandatory=True)],
        source_excerpt="x",
        section_path=["格式"],
        confidence=0.9,
    )
    out = normalize_directory_requirements([explicit])
    assert len(out) == 1
    assert out[0].inferred is False


def test_normalize_directory_merges_scattered_into_inferred() -> None:
    scattered = [
        DirectoryRequirement(
            id="dr-1",
            title="材料A",
            required_sections=["投标函"],
            mandatory=True,
            source_excerpt="a",
            section_path=[],
            confidence=0.7,
        ),
        DirectoryRequirement(
            id="dr-2",
            title="材料B",
            required_sections=["资质证明"],
            mandatory=True,
            source_excerpt="b",
            section_path=[],
            confidence=0.6,
        ),
    ]
    out = normalize_directory_requirements(scattered)
    assert len(out) == 1
    assert out[0].inferred is True
    assert out[0].title == "推断投标文件组成"
    titles = [n.title for n in out[0].structure]
    assert titles == ["投标函", "资质证明"]
```

Add import at top: `from tender_insights.interpret.models import DirectoryStructureNode`

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/tender_insights/unit/test_interpret_merger.py::test_normalize_directory_merges_scattered_into_inferred -v`

Expected: FAIL

- [ ] **Step 3: Implement normalize_directory_requirements**

Add to `merger.py`:

```python
from tender_insights.interpret.models import DirectoryRequirement, DirectoryStructureNode


def _has_explicit_structure(req: DirectoryRequirement) -> bool:
    return not req.inferred and bool(req.structure)


def normalize_directory_requirements(
    items: list[DirectoryRequirement],
) -> list[DirectoryRequirement]:
    explicit = [r for r in items if _has_explicit_structure(r)]
    if explicit:
        return dedupe_by_title(explicit)

    flat_titles: list[str] = []
    seen: set[str] = set()
    best_confidence = 0.0
    for req in items:
        best_confidence = max(best_confidence, req.confidence)
        for title in req.required_sections:
            key = title.strip().lower()
            if key and key not in seen:
                seen.add(key)
                flat_titles.append(title.strip())
        for node in req.structure:
            key = node.title.strip().lower()
            if key and key not in seen:
                seen.add(key)
                flat_titles.append(node.title.strip())

    if not flat_titles:
        return dedupe_by_title(items)

    structure = [
        DirectoryStructureNode(order=i + 1, title=title, mandatory=True)
        for i, title in enumerate(flat_titles)
    ]
    return [
        DirectoryRequirement(
            id="dr-inferred-001",
            title="推断投标文件组成",
            required_sections=[],
            mandatory=True,
            inferred=True,
            structure=structure,
            source_excerpt="",
            section_path=[],
            confidence=min(best_confidence, 0.65),
        )
    ]
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/tender_insights/unit/test_interpret_merger.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tender_insights/interpret/merger.py tests/tender_insights/unit/test_interpret_merger.py
git commit -m "feat(interpret): normalize scattered directory requirements into inferred tree"
```

---

### Task 4: Prompts and segment appendices

**Files:**
- Modify: `src/tender_insights/interpret/prompts.py`
- Create: `tests/tender_insights/unit/test_interpret_prompts.py`

- [ ] **Step 1: Write the failing test**

Create `tests/tender_insights/unit/test_interpret_prompts.py`:

```python
from tender_insights.interpret.prompts import build_segment_appendix, build_segment_prompt


def test_build_segment_appendix_for_respondent_notice() -> None:
    appendix = build_segment_appendix(["第二章 响应人须知", "评审办法"])
    assert "scoring_items" in appendix
    assert "children" in appendix


def test_build_segment_appendix_empty_when_no_keywords() -> None:
    assert build_segment_appendix(["第一章 总则"]) == ""


def test_build_segment_prompt_includes_appendix() -> None:
    prompt = build_segment_prompt("seg-001", ["第二章 响应人须知"], "正文内容")
    assert "正文内容" in prompt
    assert "scoring_items" in prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/tender_insights/unit/test_interpret_prompts.py -v`

Expected: FAIL (`build_segment_appendix` not defined)

- [ ] **Step 3: Rewrite prompts.py**

Replace `src/tender_insights/interpret/prompts.py` with:

```python
from __future__ import annotations

SYSTEM_PROMPT = """你是招标文件解读专家。从给定正文片段中提取结构化信息。
只输出 JSON，字段：
- disqualification_items: 废标项（含 trigger_condition）
- scoring_items: 得分项（含 max_score, weight, criteria, children[]）
  - children[] 为评分细则：id, title, max_score, score_range, criteria, source_excerpt
  - 响应人须知/投标人须知内嵌的评审办法、分值表、加扣分项也必须提取为 scoring_items
  - 有分值表时建父项+children；细则 criteria 须含评分档位与加扣分规则，禁止笼统摘要
  - 本段有评分相关内容时禁止返回空 scoring_items
- bid_risk_items: 投标视角风险（severity: high|medium|low, risk_category）
  - 资格、符合性、实质性响应风险；有明确分值的评分细则不要放这里
- directory_requirements: 目录/文件组成（inferred, required_sections, mandatory, structure 树形）
  - 明确「投标文件组成/格式/目录」章节：inferred=false，输出完整 structure 树，禁止拆成零散 required_sections
  - 无明确目录章节：本段 directory_requirements 返回 []
每条必须有 id, title, summary, source_excerpt, section_path, confidence。
若无某类内容，对应数组返回 []。"""

_SEGMENT_APPENDIX_RULES: list[tuple[tuple[str, ...], str]] = [
    (
        ("响应人须知", "投标人须知", "供应商须知"),
        "【分段提示】本段常含评审/评分办法，请重点提取 scoring_items（含 children 细则）。",
    ),
    (
        ("评标", "评审", "评分", "分值", "得分"),
        "【分段提示】本段为评分核心章节，须提取完整 scoring_items 树（父项+children 细则）。",
    ),
    (
        ("废标", "无效投标", "否决"),
        "【分段提示】本段重点提取 disqualification_items。",
    ),
    (
        ("投标文件组成", "文件格式", "目录", "装订"),
        "【分段提示】本段重点提取 directory_requirements（inferred=false，完整 structure 树）。",
    ),
]


def build_segment_appendix(section_path: list[str]) -> str:
    haystack = " ".join(section_path).lower()
    lines: list[str] = []
    for keywords, message in _SEGMENT_APPENDIX_RULES:
        if any(kw.lower() in haystack for kw in keywords):
            lines.append(message)
    return "\n".join(lines)


def build_segment_prompt(segment_id: str, section_path: list[str], markdown: str) -> str:
    path = " > ".join(section_path) if section_path else "(root)"
    appendix = build_segment_appendix(section_path)
    parts = [f"segment_id: {segment_id}", f"section_path: {path}"]
    if appendix:
        parts.append(appendix)
    parts.append(f"\n正文:\n{markdown}")
    return "\n".join(parts)


OVERVIEW_SYSTEM_PROMPT = """你是招标文件解读专家。根据已提取的结构化明细，生成概要描述。
只输出 JSON：{ summary, disqualification_summary, scoring_summary, bid_risk_summary, directory_summary }
要求：
- scoring_summary 须写清总分结构、各大类要点及关键评分细则（来自 children）
- directory_summary 须区分明确目录与推断目录（inferred=true 时说明推断性质）"""


def build_overview_prompt(items_json: str) -> str:
    return f"已提取明细:\n{items_json}"
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/tender_insights/unit/test_interpret_prompts.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tender_insights/interpret/prompts.py tests/tender_insights/unit/test_interpret_prompts.py
git commit -m "feat(interpret): strengthen prompts and section-path appendices for v2.1"
```

---

### Task 5: Recursive directory outline

**Files:**
- Modify: `src/tender_insights/interpret/directory_outline.py`
- Test: `tests/tender_insights/unit/test_directory_outline.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/tender_insights/unit/test_directory_outline.py`:

```python
def test_build_directory_outline_recurses_children() -> None:
    reqs = [
        DirectoryRequirement(
            id="dr-1",
            title="组成",
            required_sections=[],
            mandatory=True,
            inferred=False,
            structure=[
                DirectoryStructureNode(
                    order=1,
                    number="一",
                    title="商务文件",
                    mandatory=True,
                    children=[
                        DirectoryStructureNode(order=1, title="投标函", mandatory=True),
                    ],
                )
            ],
            source_excerpt="x",
            section_path=["格式"],
            confidence=0.9,
        )
    ]
    outline = build_directory_outline(reqs)
    assert len(outline.nodes) == 2
    assert outline.nodes[0].level == 1
    assert outline.nodes[1].level == 2
    assert outline.nodes[1].title == "投标函"


def test_build_directory_outline_lower_confidence_for_inferred() -> None:
    reqs = [
        DirectoryRequirement(
            id="dr-1",
            title="推断投标文件组成",
            required_sections=[],
            mandatory=True,
            inferred=True,
            structure=[DirectoryStructureNode(order=1, title="投标函", mandatory=True)],
            source_excerpt="",
            section_path=[],
            confidence=0.65,
        )
    ]
    outline = build_directory_outline(reqs)
    assert outline.confidence == 0.55
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/tender_insights/unit/test_directory_outline.py::test_build_directory_outline_recurses_children -v`

Expected: FAIL (only 1 node returned)

- [ ] **Step 3: Implement recursive flatten**

Replace `src/tender_insights/interpret/directory_outline.py` with:

```python
from __future__ import annotations

from tender_insights.interpret.models import (
    DirectoryOutline,
    DirectoryOutlineNode,
    DirectoryRequirement,
    DirectoryStructureNode,
)


def _flatten_structure(
    nodes: list[DirectoryStructureNode],
    *,
    level: int,
    order_counter: list[int],
    output: list[DirectoryOutlineNode],
) -> None:
    for node in nodes:
        output.append(
            DirectoryOutlineNode(
                id=f"dir-{order_counter[0]:03d}",
                title=node.title,
                level=level,
                order=order_counter[0],
                mandatory=node.mandatory,
                number=node.number,
            )
        )
        order_counter[0] += 1
        if node.children:
            _flatten_structure(node.children, level=level + 1, order_counter=order_counter, output=output)


def build_directory_outline(
    directory_requirements: list[DirectoryRequirement],
) -> DirectoryOutline:
    explicit = [r for r in directory_requirements if not r.inferred and r.structure]
    inferred = [r for r in directory_requirements if r.inferred and r.structure]
    sources = explicit or inferred or directory_requirements

    nodes: list[DirectoryOutlineNode] = []
    order_counter = [1]
    has_explicit = bool(explicit)
    has_inferred = bool(inferred) and not explicit

    for req in sources:
        if req.structure:
            _flatten_structure(req.structure, level=1, order_counter=order_counter, output=nodes)
        else:
            for title in req.required_sections:
                nodes.append(
                    DirectoryOutlineNode(
                        id=f"dir-{order_counter[0]:03d}",
                        title=title,
                        level=1,
                        order=order_counter[0],
                        mandatory=req.mandatory,
                    )
                )
                order_counter[0] += 1

    if has_explicit:
        confidence = 0.85
    elif has_inferred:
        confidence = 0.55
    elif nodes:
        confidence = 0.6
    else:
        confidence = 0.0
    return DirectoryOutline(confidence=confidence, nodes=nodes)
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/tender_insights/unit/test_directory_outline.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tender_insights/interpret/directory_outline.py tests/tender_insights/unit/test_directory_outline.py
git commit -m "feat(interpret): recursively flatten directory structure into outline"
```

---

### Task 6: Overview payload and extractor wiring

**Files:**
- Modify: `src/tender_insights/interpret/overview.py`
- Modify: `src/tender_insights/interpret/extractor.py`
- Test: `tests/tender_insights/integration/test_pipeline_interpret.py`

- [ ] **Step 1: Update overview payload**

In `src/tender_insights/interpret/overview.py`, update payload:

```python
        "scoring_items": [
            {
                **i.model_dump(include={"title", "summary", "max_score", "weight", "criteria"}),
                "children": [
                    c.model_dump(include={"title", "max_score", "score_range", "criteria"})
                    for c in i.children
                ],
            }
            for i in sc
        ],
        "directory_requirements": [
            i.model_dump(include={"title", "required_sections", "mandatory", "inferred"})
            for i in dr
        ],
```

- [ ] **Step 2: Wire extractor pipeline**

In `src/tender_insights/interpret/extractor.py`:

Replace imports:

```python
from tender_insights.interpret.merger import dedupe_by_title, merge_scoring_items, normalize_directory_requirements
from tender_insights.interpret.models import InterpretationFile, InterpretationLLMResponse, ScoringItem
```

Replace merge block (after aggregation loop):

```python
    dq = dedupe_by_title(aggregated.disqualification_items)
    sc = merge_scoring_items(aggregated.scoring_items)
    br = dedupe_by_title(aggregated.bid_risk_items)
    dr = normalize_directory_requirements(aggregated.directory_requirements)
```

Add child anchor helper and call after parent anchors:

```python
def _apply_scoring_anchors(items: list[ScoringItem], content_md: str) -> None:
    for item in items:
        _apply_anchors([item], content_md)
        for child in item.children:
            start, end = backfill_char_range(content_md, child.source_excerpt)
            # ScoringCriterionNode has no char fields; anchors optional for viewer later
            _ = (start, end)
```

(If keeping child anchors out of schema, the helper can remain a no-op stub — spec allows child char fields absent.)

- [ ] **Step 3: Update integration test**

In `tests/tender_insights/integration/test_pipeline_interpret.py`, extend FakeLLM segment response:

```python
            "scoring_items": [
                {
                    "id": "sc-001",
                    "title": "技术部分",
                    "summary": "技术评分",
                    "max_score": 40.0,
                    "weight": "40%",
                    "criteria": "大类",
                    "children": [
                        {
                            "id": "sc-001-01",
                            "title": "方案完整性",
                            "max_score": 10.0,
                            "score_range": "0-10",
                            "criteria": "细则",
                            "source_excerpt": "原文",
                        }
                    ],
                    "source_excerpt": "技术40分",
                    "section_path": ["第二章 响应人须知"],
                    "confidence": 0.9,
                }
            ],
```

Add assertion:

```python
    assert len(result.scoring_items[0].children) == 1
    assert result.schema_version == "1.2"
```

Ensure FakeLLM returns one response per segment + overview (multiply segment_json if multiple segments).

- [ ] **Step 4: Run full interpret tests**

Run: `.venv/bin/pytest tests/tender_insights/ -v --ignore=tests/tender_insights/integration 2>/dev/null; .venv/bin/pytest tests/tender_insights/integration/test_pipeline_interpret.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tender_insights/interpret/overview.py src/tender_insights/interpret/extractor.py tests/tender_insights/integration/test_pipeline_interpret.py
git commit -m "feat(interpret): wire v2.1 merge, normalize, and overview payload"
```

---

### Task 7: Contract tests and docs

**Files:**
- Modify: `tests/tender_insights/contract/test_interpretation_schema.py`
- Modify: `.cursor/skills/tender-interpret/SKILL.md`
- Modify: `README.md` (schema version line only)

- [ ] **Step 1: Add schema 1.2 contract test**

Add to `tests/tender_insights/contract/test_interpretation_schema.py`:

```python
def test_interpretation_schema_accepts_v12_fixture() -> None:
    schema = InterpretationFile.model_json_schema()
    fixture = {
        "schema_version": "1.2",
        "source_workspace": "/tmp/ws",
        "analyzed_at": "2026-06-24T00:00:00+00:00",
        "segment_count": 1,
        "ocr_image_count": 0,
        "overview": {
            "summary": "概要",
            "disqualification_summary": "废标",
            "scoring_summary": "得分",
            "bid_risk_summary": "风险",
            "directory_summary": "目录",
        },
        "disqualification_items": [],
        "scoring_items": [
            {
                "id": "sc-001",
                "title": "技术部分",
                "summary": "s",
                "max_score": 40.0,
                "weight": "40%",
                "criteria": "c",
                "children": [
                    {
                        "id": "sc-001-01",
                        "title": "细则",
                        "criteria": "细则全文",
                        "source_excerpt": "x",
                    }
                ],
                "source_excerpt": "x",
                "section_path": [],
                "confidence": 0.9,
            }
        ],
        "bid_risk_items": [],
        "directory_requirements": [
            {
                "id": "dr-001",
                "title": "推断投标文件组成",
                "required_sections": [],
                "mandatory": True,
                "inferred": True,
                "structure": [],
                "source_excerpt": "",
                "section_path": [],
                "confidence": 0.6,
            }
        ],
        "directory_outline": {"confidence": 0.0, "nodes": []},
    }
    jsonschema.validate(fixture, schema)
```

Keep existing 1.1 test unchanged for backward compat.

- [ ] **Step 2: Update SKILL.md**

In `.cursor/skills/tender-interpret/SKILL.md`:

- Change `schema_version` description to `"1.2"`
- Add `ScoringItem.children[]` table (`title`, `max_score`, `score_range`, `criteria`, `source_excerpt`)
- Add `DirectoryRequirement.inferred` field description

- [ ] **Step 3: Update README**

Change interpret schema reference from 1.1 to 1.2 in the interpretation.json section (one line).

- [ ] **Step 4: Run full test suite**

Run: `.venv/bin/pytest tests/tender_insights/ -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/tender_insights/contract/test_interpretation_schema.py .cursor/skills/tender-interpret/SKILL.md README.md
git commit -m "docs(interpret): document schema 1.2 and add contract test"
```

---

## Spec Coverage Checklist

| Spec requirement | Task |
|------------------|------|
| ScoringCriterionNode + children | Task 1 |
| DirectoryRequirement.inferred | Task 1, 3 |
| merge_scoring_items | Task 2 |
| normalize_directory_requirements | Task 3 |
| System prompt + segment appendix | Task 4 |
| Recursive directory_outline | Task 5 |
| Overview payload with children/inferred | Task 6 |
| Extractor pipeline wiring | Task 6 |
| No extra LLM calls | All tasks (no new LLM modules) |
| Contract + integration tests | Task 7 |
| SKILL/README docs | Task 7 |
