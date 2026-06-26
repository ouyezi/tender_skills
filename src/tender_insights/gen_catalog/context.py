from __future__ import annotations

import json

from tender_insights.gen_catalog.models import BidOutlineFile, BidOutlineNode
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


def build_refine_user_prompt(
    report: PrerequisiteReport,
    *,
    draft: BidOutlineFile,
    target_node_id: str,
    excerpt: str,
) -> str:
    interp = report.interpretation
    target = _find_node_title(draft.root, target_node_id)
    parts = [
        "## 废标项（id 表）",
        _item_table(interp.disqualification_items, fields=["id", "title", "summary", "trigger_condition"]),
        "## 评分项（id 表）",
        _item_table(
            interp.scoring_items,
            fields=["id", "title", "summary", "max_score", "weight", "criteria"],
        ),
        "## 当前完整目录树",
        json.dumps(draft.root.model_dump(), ensure_ascii=False, indent=2),
        f"## 目标节点\ntarget_node_id: {target_node_id}\ntitle: {target}",
        "## 招标文件相关摘录",
        excerpt,
    ]
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


def _find_node_title(root: BidOutlineNode, node_id: str) -> str:
    if root.id == node_id:
        return root.title
    for child in root.children:
        title = _find_node_title(child, node_id)
        if title:
            return title
    return ""
