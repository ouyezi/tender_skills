from __future__ import annotations

from doc_chunk.models.outline import OutlineTree

from viewer.services.outline_tree import PREFACE_NODE_ID
from viewer.services.section_slice import slice_section


def resolve_outline_node_for_char(
    char_pos: int,
    content_md: str,
    outline_tree: OutlineTree,
) -> str | None:
    if char_pos < 0:
        return None

    preface = slice_section(content_md, outline_tree, PREFACE_NODE_ID)
    if char_pos < preface.char_end:
        return PREFACE_NODE_ID

    for node in outline_tree.nodes:
        try:
            section = slice_section(content_md, outline_tree, node.node_id)
        except KeyError:
            continue
        if section.char_start <= char_pos < section.char_end:
            return node.node_id
    return None
