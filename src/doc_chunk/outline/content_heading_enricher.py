from __future__ import annotations

import re
from dataclasses import dataclass

from doc_chunk.locate.heading_starts import (
    build_node_heading_starts,
    ensure_section_prefix_spacing,
    normalize_outline_title,
)
from doc_chunk.models.content_block import ContentBlocksFile
from doc_chunk.models.outline import OutlineTree

_HEADING_RE = re.compile(r"^(#{1,8})[ \t]+(.+?)[ \t#]*$", re.MULTILINE)


@dataclass(frozen=True, slots=True)
class TitleEdit:
    start: int
    old_end: int
    new_text: str


def _heading_match_at(content_md: str, char_start: int) -> re.Match[str] | None:
    for match in _HEADING_RE.finditer(content_md):
        if match.start() == char_start:
            return match
    return None


def enrich_content_md_headings(content_md: str, tree: OutlineTree) -> tuple[str, list[TitleEdit]]:
    if tree.strategy != "toc" or not content_md:
        return content_md, []

    node_map = {node.node_id: node for node in tree.nodes}
    heading_starts = build_node_heading_starts(
        tree, content_md, use_existing_anchor_fallback=False
    )

    edits: list[TitleEdit] = []
    for node_id, char_start in heading_starts.items():
        node = node_map[node_id]
        match = _heading_match_at(content_md, char_start)
        if match is None:
            continue

        current_title = match.group(2).strip()
        display_title = ensure_section_prefix_spacing(node.title)
        if current_title == display_title:
            continue
        if normalize_outline_title(current_title) != normalize_outline_title(node.title):
            continue

        edits.append(
            TitleEdit(
                start=match.start(2),
                old_end=match.end(2),
                new_text=display_title,
            )
        )

    if not edits:
        return content_md, []

    enriched = content_md
    for edit in sorted(edits, key=lambda item: item.start, reverse=True):
        enriched = enriched[: edit.start] + edit.new_text + enriched[edit.old_end :]
    return enriched, edits


def _map_char_position(pos: int, edits: list[TitleEdit]) -> int:
    offset = 0
    for edit in sorted(edits, key=lambda item: item.start):
        edit_delta = len(edit.new_text) - (edit.old_end - edit.start)
        if pos <= edit.start:
            break
        if pos >= edit.old_end:
            offset += edit_delta
        else:
            offset += len(edit.new_text) - (pos - edit.start)
            break
    return pos + offset


def resync_blocks_char_offsets(
    blocks: ContentBlocksFile,
    edits: list[TitleEdit],
    *,
    content_md: str,
) -> ContentBlocksFile:
    if not edits:
        return blocks

    updated_blocks = []
    for block in blocks.blocks:
        new_start = _map_char_position(block.char_start, edits)
        new_end = _map_char_position(block.char_end, edits)
        preview = block.text_preview
        if block.block_type == "heading":
            preview = content_md[new_start:new_end].strip() or None
        updated_blocks.append(
            block.model_copy(
                update={
                    "char_start": new_start,
                    "char_end": new_end,
                    "text_preview": preview,
                }
            )
        )
    return blocks.model_copy(update={"blocks": updated_blocks})
