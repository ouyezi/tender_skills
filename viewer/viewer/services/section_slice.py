from __future__ import annotations

import re

from doc_chunk.models.outline import OutlineNode, OutlineTree

from viewer.models import SectionResponse
from viewer.services.outline_tree import PREFACE_NODE_ID

_HEADING_RE = re.compile(r"^(#{1,8})[ \t]+(.+?)[ \t#]*$", re.MULTILINE)


def _sorted_sliceable_nodes(nodes: list[OutlineNode]) -> list[OutlineNode]:
    return sorted(
        nodes,
        key=lambda n: (
            n.anchor.char_start if n.anchor.char_start is not None else 10**9,
            n.sort_order,
        ),
    )


def _is_descendant(node: OutlineNode, ancestor: OutlineNode, node_map: dict[str, OutlineNode]) -> bool:
    cursor_id = node.parent_id
    seen: set[str] = set()
    while cursor_id and cursor_id not in seen:
        if cursor_id == ancestor.node_id:
            return True
        seen.add(cursor_id)
        parent = node_map.get(cursor_id)
        cursor_id = parent.parent_id if parent else None
    return False


def _section_end_char(
    node: OutlineNode,
    ordered: list[OutlineNode],
    node_map: dict[str, OutlineNode],
    content_len: int,
) -> int:
    start = node.anchor.char_start or 0
    level = node.level
    for other in ordered:
        other_start = other.anchor.char_start
        if other_start is None or other_start <= start or other.node_id == node.node_id:
            continue
        if _is_descendant(other, node, node_map):
            return other_start
    for other in ordered:
        other_start = other.anchor.char_start
        if other_start is None or other_start <= start:
            continue
        if other.level <= level:
            return other_start
    return content_len


def _build_section_path(node: OutlineNode, node_map: dict[str, OutlineNode]) -> list[str]:
    chain: list[str] = []
    cursor: OutlineNode | None = node
    seen: set[str] = set()
    while cursor and cursor.node_id not in seen:
        seen.add(cursor.node_id)
        chain.append(cursor.title)
        cursor = node_map.get(cursor.parent_id) if cursor.parent_id else None
    return list(reversed(chain))


def _fallback_char_start(content_md: str, title: str) -> int | None:
    for match in _HEADING_RE.finditer(content_md):
        if match.group(2).strip() == title:
            return match.start()
    return None


def _heading_section_end_char(content_md: str, start: int, level: int, content_len: int) -> int:
    for match in _HEADING_RE.finditer(content_md):
        match_start = match.start()
        if match_start <= start:
            continue
        if len(match.group(1)) <= level:
            return match_start
    return content_len


def slice_section(content_md: str, outline_tree: OutlineTree, node_id: str) -> SectionResponse:
    if node_id == PREFACE_NODE_ID:
        ordered = _sorted_sliceable_nodes(outline_tree.nodes)
        first_start = ordered[0].anchor.char_start if ordered else None
        if first_start is None and ordered:
            first_start = _fallback_char_start(content_md, ordered[0].title)
        end = first_start or 0
        return SectionResponse(
            node_id=PREFACE_NODE_ID,
            title="前言",
            level=0,
            section_path=[],
            needs_review=False,
            char_start=0,
            char_end=end,
            markdown=content_md[:end],
        )

    node_map = {n.node_id: n for n in outline_tree.nodes}
    node = node_map.get(node_id)
    if node is None:
        raise KeyError(node_id)

    ordered = _sorted_sliceable_nodes(outline_tree.nodes)
    start = node.anchor.char_start
    if start is None:
        start = _fallback_char_start(content_md, node.title)
    if start is None:
        start = 0
    content_len = len(content_md)
    end = _section_end_char(node, ordered, node_map, content_len)
    if end == content_len:
        end = _heading_section_end_char(content_md, start, node.level, content_len)
    return SectionResponse(
        node_id=node.node_id,
        title=node.title,
        level=node.level,
        section_path=_build_section_path(node, node_map),
        needs_review=node.needs_review,
        char_start=start,
        char_end=end,
        markdown=content_md[start:end],
    )
