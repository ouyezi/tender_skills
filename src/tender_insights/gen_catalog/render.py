from __future__ import annotations

from tender_insights.gen_catalog.models import BidOutlineFile, BidOutlineNode


def render_bid_outline_markdown(draft: BidOutlineFile) -> str:
    lines = [
        f"# {draft.root.title}",
        "",
        f"- 工作区: `{draft.source_workspace}`",
        f"- 状态: {draft.status}",
        f"- 模式: {draft.mode}",
        "",
    ]
    lines.extend(_render_node(draft.root, depth=0))
    return "\n".join(lines).strip() + "\n"


def _render_node(node: BidOutlineNode, *, depth: int) -> list[str]:
    if node.id == "bid-root":
        lines: list[str] = []
        for child in node.children:
            lines.extend(_render_node(child, depth=0))
        return lines

    indent = "  " * depth
    heading = "#" * min(depth + 2, 6)
    lines = [
        f"{heading} {node.title}",
        "",
        f"{indent}- 必填: {'是' if node.mandatory else '否'}",
    ]
    if node.summary:
        lines.extend([f"{indent}- 概要: {node.summary}", ""])
    if node.writing_spec:
        lines.extend([f"{indent}- 撰写规范: {node.writing_spec}", ""])
    if node.template_ref is not None:
        lines.append(f"{indent}- 模板: `{node.template_ref.file}`")
    if node.scoring_refs:
        lines.append(f"{indent}- 评分引用: {', '.join(node.scoring_refs)}")
    if node.disqualification_refs:
        lines.append(f"{indent}- 废标引用: {', '.join(node.disqualification_refs)}")
    lines.append("")
    for child in node.children:
        lines.extend(_render_node(child, depth=depth + 1))
    return lines
