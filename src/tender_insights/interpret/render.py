from __future__ import annotations

from tender_insights.interpret.models import (
    BidRiskItem,
    DirectoryOutlineNode,
    DirectoryRequirement,
    DisqualificationItem,
    InterpretationFile,
    InterpretationOverview,
    ScoringItem,
)


def _section_path_label(section_path: list[str]) -> str:
    return " / ".join(section_path) if section_path else "—"


def _render_overview(overview: InterpretationOverview) -> str:
    lines = ["## 解读概要", ""]
    if overview.summary:
        lines.extend([overview.summary, ""])
    for key, label in (
        ("disqualification_summary", "废标项"),
        ("scoring_summary", "得分项"),
        ("bid_risk_summary", "投标风险"),
        ("directory_summary", "目录要求"),
    ):
        text = getattr(overview, key)
        if text:
            lines.append(f"**{label}：** {text}")
    lines.append("")
    return "\n".join(lines)


def _render_disqualification_items(items: list[DisqualificationItem]) -> str:
    lines = ["## 废标项", ""]
    if not items:
        lines.append("_（无）_\n")
        return "\n".join(lines)
    for item in items:
        lines.append(f"### {item.title}")
        lines.append(f"- **摘要：** {item.summary}")
        lines.append(f"- **触发条件：** {item.trigger_condition}")
        lines.append(f"- **章节：** {_section_path_label(item.section_path)}")
        if item.source_excerpt:
            lines.append(f"- **原文摘录：** {item.source_excerpt}")
        lines.append("")
    return "\n".join(lines)


def _render_scoring_children(children: list, depth: int = 0) -> list[str]:
    lines: list[str] = []
    indent = "  " * depth
    for child in children:
        score = f"（{child.max_score}分）" if child.max_score is not None else ""
        lines.append(f"{indent}- **{child.title}**{score}：{child.criteria}")
        if child.source_excerpt:
            lines.append(f"{indent}  - 原文：{child.source_excerpt}")
    return lines


def _render_scoring_items(items: list[ScoringItem]) -> str:
    lines = ["## 得分项", ""]
    if not items:
        lines.append("_（无）_\n")
        return "\n".join(lines)
    for item in items:
        weight = f"（权重 {item.weight}）" if item.weight else ""
        score = f"（满分 {item.max_score}）" if item.max_score is not None else ""
        lines.append(f"### {item.title}{weight}{score}")
        lines.append(f"- **摘要：** {item.summary}")
        lines.append(f"- **评分标准：** {item.criteria}")
        lines.append(f"- **章节：** {_section_path_label(item.section_path)}")
        if item.source_excerpt:
            lines.append(f"- **原文摘录：** {item.source_excerpt}")
        if item.children:
            lines.extend(_render_scoring_children(item.children))
        lines.append("")
    return "\n".join(lines)


def _render_bid_risk_items(items: list[BidRiskItem]) -> str:
    lines = ["## 投标风险", ""]
    if not items:
        lines.append("_（无）_\n")
        return "\n".join(lines)
    for item in items:
        lines.append(f"### {item.title}（{item.severity.value} / {item.risk_category}）")
        lines.append(f"- **摘要：** {item.summary}")
        lines.append(f"- **章节：** {_section_path_label(item.section_path)}")
        if item.source_excerpt:
            lines.append(f"- **原文摘录：** {item.source_excerpt}")
        lines.append("")
    return "\n".join(lines)


def _render_structure_tree(nodes: list, depth: int = 0) -> list[str]:
    lines: list[str] = []
    indent = "  " * depth
    for node in nodes:
        number = f"{node.number} " if getattr(node, "number", None) else ""
        mandatory = "" if getattr(node, "mandatory", True) else "（可选）"
        lines.append(f"{indent}- {number}{node.title}{mandatory}")
        children = getattr(node, "children", None) or []
        if children:
            lines.extend(_render_structure_tree(children, depth + 1))
    return lines


def _render_directory_requirements(items: list[DirectoryRequirement]) -> str:
    lines = ["## 目录要求", ""]
    if not items:
        lines.append("_（无）_\n")
        return "\n".join(lines)
    for item in items:
        mandatory = "必须" if item.mandatory else "可选"
        inferred = "（推断）" if item.inferred else ""
        lines.append(f"### {item.title}（{mandatory}）{inferred}")
        if item.required_sections:
            lines.append("- **要求章节：** " + "、".join(item.required_sections))
        if item.structure:
            lines.append("- **结构：**")
            lines.extend(_render_structure_tree(item.structure, depth=1))
        if item.source_excerpt:
            lines.append(f"- **原文摘录：** {item.source_excerpt}")
        lines.append("")
    return "\n".join(lines)


def _render_directory_outline(nodes: list[DirectoryOutlineNode]) -> str:
    lines = ["## 推荐目录", ""]
    if not nodes:
        lines.append("_（无）_\n")
        return "\n".join(lines)
    for node in sorted(nodes, key=lambda n: (n.level, n.order)):
        number = f"{node.number} " if node.number else ""
        mandatory = "" if node.mandatory else "（可选）"
        indent = "  " * max(node.level - 1, 0)
        lines.append(f"{indent}- {number}{node.title}{mandatory}")
    lines.append("")
    return "\n".join(lines)


def render_interpretation_markdown(data: InterpretationFile) -> str:
    sections = [
        "# 招标解读报告",
        "",
        f"- **工作区：** {data.source_workspace}",
        f"- **分析时间：** {data.analyzed_at}",
        f"- **分段数：** {data.segment_count}",
        "",
        _render_overview(data.overview),
        _render_disqualification_items(data.disqualification_items),
        _render_scoring_items(data.scoring_items),
        _render_bid_risk_items(data.bid_risk_items),
        _render_directory_requirements(data.directory_requirements),
        _render_directory_outline(data.directory_outline.nodes),
    ]
    return "\n".join(sections).rstrip() + "\n"
