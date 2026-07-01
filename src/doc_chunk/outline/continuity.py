from __future__ import annotations

import re

from doc_chunk.extract.promote_headings import is_cn_local_enum_paragraph
from doc_chunk.models.outline import OutlineNode, OutlineTree

_CN_ENUM_RE = re.compile(r"^[一二三四五六七八九十]+、")
_NUM_SECTION_RE = re.compile(r"^\d+(?:\.\d+)")


def _rebuild_outline_parents(nodes: list[OutlineNode]) -> None:
    last_seen: dict[int, str] = {}
    for node in sorted(nodes, key=lambda item: item.sort_order):
        parent_id = None
        if node.level > 1:
            for parent_level in range(node.level - 1, 0, -1):
                parent_id = last_seen.get(parent_level)
                if parent_id:
                    break
        node.parent_id = parent_id
        last_seen[node.level] = node.node_id
        for stale_level in [level for level in last_seen if level > node.level]:
            last_seen.pop(stale_level, None)


def _local_cn_series_precedes(
    nodes: list[OutlineNode],
    current_node: OutlineNode,
    content_md: str,
) -> bool:
    if current_node.anchor is None or current_node.anchor.block_index is None:
        return False
    cur_block = current_node.anchor.block_index
    prev_nodes = [
        node
        for node in nodes
        if node.sort_order < current_node.sort_order
        and node.anchor is not None
        and node.anchor.block_index is not None
    ]
    start_block = 0
    if prev_nodes:
        prev = max(prev_nodes, key=lambda item: item.anchor.block_index)
        start_block = prev.anchor.block_index + 1

    lines = content_md.splitlines()
    end_block = min(cur_block, len(lines))
    return any(is_cn_local_enum_paragraph(line) for line in lines[start_block:end_block])


def normalize_outline_cn_continuity(tree: OutlineTree, *, content_md: str = "") -> OutlineTree:
    """Nest stray L1「X、」nodes that continue a numeric section's local 一、…： list."""
    nodes = sorted(tree.nodes, key=lambda item: item.sort_order)
    changed = False
    for index, node in enumerate(nodes):
        if node.level != 1 or not _CN_ENUM_RE.match(node.title or ""):
            continue
        if not _local_cn_series_precedes(nodes, node, content_md):
            continue
        anchor: OutlineNode | None = None
        for prev in reversed(nodes[:index]):
            if _NUM_SECTION_RE.match(prev.title or "") and prev.level >= 2:
                anchor = prev
                break
        if anchor is None:
            continue
        node.level = anchor.level + 1
        node.parent_id = anchor.node_id
        changed = True
    if changed:
        _rebuild_outline_parents(nodes)
    return tree
