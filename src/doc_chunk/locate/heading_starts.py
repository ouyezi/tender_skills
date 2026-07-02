from __future__ import annotations

import re
from dataclasses import dataclass

from doc_chunk.extract.promote_headings import is_toc_entry_line
from doc_chunk.models.outline import OutlineNode, OutlineTree

_HEADING_RE = re.compile(r"^(#{1,8})[ \t]+(.+?)[ \t#]*$", re.MULTILINE)
_NUM_PREFIX_RE = re.compile(r"^(\d+(?:\.\d+)*[\s、.．]+)")
_CN_ENUM_PREFIX_RE = re.compile(r"^[一二三四五六七八九十百零]+、[ \t]*")
_TOC_PAGE_SUFFIX_RE = re.compile(r"[\t]\d+\s*$")
_GLUED_PAGE_RE = re.compile(r"^(?P<title>.+?\D)(?P<page>\d{1,3})$")
_LEADING_GLUED_NUM_RE = re.compile(r"^\d+(?=[\u4e00-\u9fff])")


@dataclass(frozen=True, slots=True)
class Heading:
    char_start: int
    level: int
    title: str


def normalize_outline_title(text: str) -> str:
    stripped = _TOC_PAGE_SUFFIX_RE.sub("", text.strip())
    glued = _GLUED_PAGE_RE.match(stripped)
    if glued is not None:
        stripped = glued.group("title")
    stripped = _LEADING_GLUED_NUM_RE.sub("", stripped)
    stripped = _CN_ENUM_PREFIX_RE.sub("", stripped)
    stripped = _NUM_PREFIX_RE.sub("", stripped)
    return stripped.strip().lower()


def parse_body_headings(content_md: str) -> list[Heading]:
    headings: list[Heading] = []
    for match in _HEADING_RE.finditer(content_md):
        title = match.group(2).strip()
        if is_toc_entry_line(title):
            continue
        headings.append(
            Heading(
                char_start=match.start(),
                level=len(match.group(1)),
                title=title,
            )
        )
    return headings


def _titles_match(node: OutlineNode, heading: Heading) -> bool:
    return node.level == heading.level and normalize_outline_title(node.title) == normalize_outline_title(
        heading.title
    )


def fallback_char_start(content_md: str, title: str, *, level: int | None = None) -> int | None:
    for heading in parse_body_headings(content_md):
        if level is not None and heading.level != level:
            continue
        if normalize_outline_title(heading.title) == normalize_outline_title(title):
            return heading.char_start
    return None


def build_node_heading_starts(
    outline_tree: OutlineTree,
    content_md: str,
    *,
    use_existing_anchor_fallback: bool = True,
) -> dict[str, int]:
    headings = parse_body_headings(content_md)
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

        fb = fallback_char_start(content_md, node.title, level=node.level)
        if fb is None and use_existing_anchor_fallback and node.anchor.char_start is not None:
            fb = node.anchor.char_start
        if fb is not None:
            mapping[node.node_id] = fb

    return mapping


def section_end_by_heading(content_md: str, start: int, level: int) -> int:
    for match in _HEADING_RE.finditer(content_md):
        if match.start() <= start:
            continue
        if len(match.group(1)) <= level:
            return match.start()
    return len(content_md)


def section_char_range(tree: OutlineTree, content_md: str, node_id: str) -> tuple[int, int]:
    node_map = {n.node_id: n for n in tree.nodes}
    node = node_map.get(node_id)
    if node is None:
        raise KeyError(node_id)

    heading_starts = build_node_heading_starts(tree, content_md)
    start = heading_starts.get(node_id)
    if start is None:
        start = fallback_char_start(content_md, node.title, level=node.level) or 0
    end = section_end_by_heading(content_md, start, node.level)
    return start, end
