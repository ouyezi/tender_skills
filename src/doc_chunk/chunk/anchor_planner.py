from __future__ import annotations

import re

from doc_chunk.chunk.blocks_builder import build_chunk_blocks
from doc_chunk.chunk.planner import _split_oversized
from doc_chunk.chunk.tokenizer import estimate_tokens
from doc_chunk.models.chunk import ContentChunk
from doc_chunk.models.outline import OutlineNode, OutlineTree

_IMAGE_RE = re.compile(r"!\[[^\]]*]\(([^)]+)\)")


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
    end = content_len

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
    return end


def _build_section_path(node: OutlineNode, node_map: dict[str, OutlineNode]) -> list[str]:
    chain: list[str] = []
    cursor: OutlineNode | None = node
    seen: set[str] = set()
    while cursor and cursor.node_id not in seen:
        seen.add(cursor.node_id)
        chain.append(cursor.title)
        cursor = node_map.get(cursor.parent_id) if cursor.parent_id else None
    return list(reversed(chain))


def plan_chunks_from_anchors(
    content_md: str,
    outline_tree: OutlineTree,
    *,
    max_tokens: int = 20_000,
) -> list[ContentChunk]:
    if max_tokens <= 0:
        raise ValueError("max_tokens must be positive")

    node_map = {n.node_id: n for n in outline_tree.nodes}
    ordered = _sorted_sliceable_nodes(outline_tree.nodes)
    if not ordered:
        return []

    chunks: list[ContentChunk] = []
    chunk_index = 1
    content_len = len(content_md)

    first_start = ordered[0].anchor.char_start or 0
    if first_start > 0 and content_md[:first_start].strip():
        preface_md = content_md[:first_start]
        chunks.append(
            ContentChunk(
                chunk_id=f"chunk-{chunk_index:04d}",
                title="Preface",
                heading_level=None,
                markdown=preface_md if preface_md.endswith("\n") else f"{preface_md}\n",
                source_file="content.md",
                token_estimate=estimate_tokens(preface_md),
                image_refs=[m.group(1) for m in _IMAGE_RE.finditer(preface_md)],
            )
        )
        chunk_index += 1

    for node in ordered:
        start = node.anchor.char_start
        if start is None:
            continue
        end = _section_end_char(node, ordered, node_map, content_len)
        raw = content_md[start:end]
        if not raw.strip():
            continue
        parts = _split_oversized(raw, max_tokens)
        section_path = _build_section_path(node, node_map)
        for part_idx, part in enumerate(parts):
            markdown = part if part.endswith("\n") else f"{part}\n"
            chunk_blocks = build_chunk_blocks(markdown=part, char_start=start, char_end=end)
            chunks.append(
                ContentChunk(
                    chunk_id=f"chunk-{chunk_index:04d}",
                    title=node.title,
                    section_path=section_path,
                    heading_level=node.level if part_idx == 0 else None,
                    markdown=markdown,
                    blocks=chunk_blocks,
                    source_file="content.md",
                    source_ranges=[{"char_start": start, "char_end": end}],
                    token_estimate=estimate_tokens(part),
                    image_refs=[m.group(1) for m in _IMAGE_RE.finditer(part)],
                    original_node_ids=[node.node_id],
                )
            )
            chunk_index += 1

    for idx, chunk in enumerate(chunks):
        chunk.previous_chunk_id = chunks[idx - 1].chunk_id if idx > 0 else None
        chunk.next_chunk_id = chunks[idx + 1].chunk_id if idx + 1 < len(chunks) else None
    return chunks
