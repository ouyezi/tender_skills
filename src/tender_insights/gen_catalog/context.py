from __future__ import annotations

import json

from tender_insights.brief.models import TenderBriefFile
from tender_insights.gen_catalog.models import BidOutlineNode
from tender_insights.gen_catalog.prerequisites import PrerequisiteReport


def _item_table(items: list, *, fields: list[str]) -> str:
    rows = []
    for item in items:
        row = {field: getattr(item, field, None) for field in fields}
        rows.append(row)
    return json.dumps(rows, ensure_ascii=False, indent=2)


def build_initial_user_prompt(report: PrerequisiteReport) -> str:
    interp = report.interpretation
    parts = [
        "## 解读概要",
        json.dumps(interp.overview.model_dump(), ensure_ascii=False, indent=2),
        "## 废标项（id 表）",
        _item_table(interp.disqualification_items, fields=["id", "title", "summary", "trigger_condition"]),
        "## 评分项（id 表）",
        _item_table(
            interp.scoring_items,
            fields=["id", "title", "summary", "max_score", "weight", "criteria"],
        ),
    ]
    if report.brief is not None:
        parts.extend(
            [
                "## 招标概要（tender_brief）",
                json.dumps(
                    {
                        "summary_text": report.brief.summary_text,
                        "fields": report.brief.fields.model_dump(),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            ]
        )
    parts.extend(
        [
            "## 目录要求",
            json.dumps(
                [dr.model_dump() for dr in interp.directory_requirements],
                ensure_ascii=False,
                indent=2,
            ),
            "## 目录大纲",
            json.dumps(interp.directory_outline.model_dump(), ensure_ascii=False, indent=2),
        ]
    )
    if report.templates is not None:
        parts.extend(
            [
                "## 模板清单",
                json.dumps(
                    [t.model_dump() for t in report.templates.templates],
                    ensure_ascii=False,
                    indent=2,
                ),
            ]
        )
    return "\n\n".join(parts)


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
