from __future__ import annotations

import re
from dataclasses import dataclass

from doc_chunk.models.outline import OutlineNode, OutlineTree

from viewer.models import SectionResponse
from viewer.services.outline_tree import PREFACE_NODE_ID

_HEADING_RE = re.compile(r"^(#{1,8})[ \t]+(.+?)[ \t#]*$", re.MULTILINE)
_NUM_PREFIX_RE = re.compile(r"^(\d+(?:\.\d+)*[\s、.．]+)")


@dataclass(frozen=True, slots=True)
class _Heading:
    char_start: int
    level: int
    title: str


def _normalize_title(text: str) -> str:
    return _NUM_PREFIX_RE.sub("", text).strip().lower()


def _parse_headings(content_md: str) -> list[_Heading]:
    headings: list[_Heading] = []
    for match in _HEADING_RE.finditer(content_md):
        headings.append(
            _Heading(
                char_start=match.start(),
                level=len(match.group(1)),
                title=match.group(2).strip(),
            )
        )
    return headings


def _titles_match(node: OutlineNode, heading: _Heading) -> bool:
    return node.level == heading.level and _normalize_title(node.title) == _normalize_title(heading.title)


def _fallback_char_start(content_md: str, title: str, *, level: int | None = None) -> int | None:
    for heading in _parse_headings(content_md):
        if level is not None and heading.level != level:
            continue
        if _normalize_title(heading.title) == _normalize_title(title):
            return heading.char_start
    return None


def _build_node_heading_starts(outline_tree: OutlineTree, content_md: str) -> dict[str, int]:
    headings = _parse_headings(content_md)
    nodes = sorted(outline_tree.nodes, key=lambda n: (n.sort_order, n.node_id))
    mapping: dict[str, int] = {}
    heading_idx = 0

    for node in nodes:
        matched = False
        while heading_idx < len(headings):
            heading = headings[heading_idx]
            if _titles_match(node, heading):
                mapping[node.node_id] = heading.char_start
                heading_idx += 1
                matched = True
                break
            heading_idx += 1
        if matched:
            continue

        fallback = _fallback_char_start(content_md, node.title, level=node.level)
        if fallback is None and node.anchor.char_start is not None:
            fallback = node.anchor.char_start
        if fallback is not None:
            mapping[node.node_id] = fallback

    return mapping


def _section_end_by_heading(content_md: str, start: int, level: int) -> int:
    for match in _HEADING_RE.finditer(content_md):
        if match.start() <= start:
            continue
        if len(match.group(1)) <= level:
            return match.start()
    return len(content_md)


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
    headings = _parse_headings(content_md)
    if headings:
        return headings[0].char_start
    if heading_starts:
        return min(heading_starts.values())
    return 0


def slice_section(content_md: str, outline_tree: OutlineTree, node_id: str) -> SectionResponse:
    heading_starts = _build_node_heading_starts(outline_tree, content_md)
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
        start = _fallback_char_start(content_md, node.title, level=node.level) or 0

    end = _section_end_by_heading(content_md, start, node.level)
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
