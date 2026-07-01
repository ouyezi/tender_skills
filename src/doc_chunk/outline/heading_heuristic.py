from __future__ import annotations

import re

from doc_chunk.extract.promote_headings import PromoteHeadingsState
from doc_chunk.models.outline import Anchor, OutlineNode, OutlineTree

_MD_HEADING_RE = re.compile(r"^(#{1,8})[ \t]+(.+?)[ \t#]*$", re.MULTILINE)


def extract_heading_outline(content_md: str) -> OutlineTree | None:
    matches = list(_MD_HEADING_RE.finditer(content_md))
    if not matches:
        return None

    nodes: list[OutlineNode] = []
    last_seen_by_level: dict[int, str] = {}
    for idx, match in enumerate(matches):
        level = len(match.group(1))
        title = match.group(2).strip()
        if not title:
            continue
        parent_id = None
        if level > 1:
            for parent_level in range(level - 1, 0, -1):
                parent_id = last_seen_by_level.get(parent_level)
                if parent_id:
                    break
        node_id = f"n{len(nodes) + 1}"
        nodes.append(
            OutlineNode(
                node_id=node_id,
                title=title,
                level=level,
                parent_id=parent_id,
                sort_order=idx,
                anchor=Anchor(block_index=idx),
            )
        )
        last_seen_by_level[level] = node_id
        for stale_level in list(last_seen_by_level):
            if stale_level > level:
                last_seen_by_level.pop(stale_level, None)

    if not nodes:
        return None
    return OutlineTree(strategy="heading_heuristic", nodes=nodes)


def extract_content_heuristic_outline(content_md: str) -> OutlineTree | None:
    nodes: list[OutlineNode] = []
    last_seen_by_level: dict[int, str] = {}
    promote_state = PromoteHeadingsState()
    for idx, raw_line in enumerate(content_md.splitlines()):
        parsed = promote_state.parse(raw_line)
        if parsed is None:
            continue
        level, title = parsed

        parent_id = None
        if level > 1:
            for parent_level in range(level - 1, 0, -1):
                parent_id = last_seen_by_level.get(parent_level)
                if parent_id:
                    break

        node_id = f"n{len(nodes) + 1}"
        nodes.append(
            OutlineNode(
                node_id=node_id,
                title=title,
                level=level,
                parent_id=parent_id,
                sort_order=len(nodes),
                anchor=Anchor(block_index=idx),
            )
        )
        last_seen_by_level[level] = node_id
        for stale_level in list(last_seen_by_level):
            if stale_level > level:
                last_seen_by_level.pop(stale_level, None)

    if not nodes:
        return None
    return OutlineTree(strategy="content_heuristic", nodes=nodes)
