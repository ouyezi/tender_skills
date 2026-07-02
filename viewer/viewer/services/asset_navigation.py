from __future__ import annotations

from doc_chunk.models.outline import OutlineTree

from viewer.services.outline_tree import PREFACE_NODE_ID
from viewer.services.section_slice import SectionCharRange, build_section_char_ranges


def resolve_outline_node_for_char(
    char_pos: int,
    content_md: str,
    outline_tree: OutlineTree,
    *,
    section_ranges: list[SectionCharRange] | None = None,
) -> str | None:
    if char_pos < 0:
        return None

    ranges = section_ranges or build_section_char_ranges(content_md, outline_tree)
    preface = ranges[0]
    if char_pos < preface.char_end:
        return PREFACE_NODE_ID

    for section in ranges[1:]:
        if section.char_start <= char_pos < section.char_end:
            return section.node_id
    return None
