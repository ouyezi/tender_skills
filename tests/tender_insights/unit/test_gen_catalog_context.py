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
