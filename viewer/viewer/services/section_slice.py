from __future__ import annotations

from dataclasses import dataclass

from doc_chunk.locate.heading_starts import (
    build_node_heading_starts,
    fallback_char_start,
    parse_body_headings,
    section_end_by_heading,
)
from doc_chunk.models.outline import OutlineNode, OutlineTree

from viewer.models import SectionResponse
from viewer.services.outline_tree import PREFACE_NODE_ID


@dataclass(frozen=True, slots=True)
class SectionCharRange:
    node_id: str
    char_start: int
    char_end: int


def _build_section_path(node: OutlineNode, node_map: dict[str, OutlineNode]) -> list[str]:
    chain: list[str] = []
    cursor: OutlineNode | None = node
    seen: set[str] = set()
    while cursor and cursor.node_id not in seen:
        seen.add(cursor.node_id)
        chain.append(cursor.title)
        cursor = node_map.get(cursor.parent_id) if cursor.parent_id else None
    return list(reversed(chain))


def _preface_end(content_md: str, heading_starts: dict[str, int]) -> int:
    headings = parse_body_headings(content_md)
    if headings:
        return headings[0].char_start
    if heading_starts:
        return min(heading_starts.values())
    return 0


def build_section_char_ranges(content_md: str, outline_tree: OutlineTree) -> list[SectionCharRange]:
    heading_starts = build_node_heading_starts(outline_tree, content_md)
    preface_end = _preface_end(content_md, heading_starts)
    ranges: list[SectionCharRange] = [
        SectionCharRange(PREFACE_NODE_ID, 0, preface_end),
    ]
    for node in outline_tree.nodes:
        start = heading_starts.get(node.node_id)
        if start is None:
            start = fallback_char_start(content_md, node.title, level=node.level) or 0
        end = section_end_by_heading(content_md, start, node.level)
        ranges.append(SectionCharRange(node.node_id, start, end))
    return ranges


def slice_section(content_md: str, outline_tree: OutlineTree, node_id: str) -> SectionResponse:
    heading_starts = build_node_heading_starts(outline_tree, content_md)
    node_map = {n.node_id: n for n in outline_tree.nodes}

    if node_id == PREFACE_NODE_ID:
        end = _preface_end(content_md, heading_starts)
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

    node = node_map.get(node_id)
    if node is None:
        raise KeyError(node_id)

    start = heading_starts.get(node_id)
    if start is None:
        start = fallback_char_start(content_md, node.title, level=node.level) or 0

    end = section_end_by_heading(content_md, start, node.level)
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
