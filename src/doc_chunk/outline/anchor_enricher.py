from __future__ import annotations

import re

from doc_chunk.models.content_block import ContentBlocksFile
from doc_chunk.models.outline import Anchor, OutlineNode, OutlineTree

_NUM_PREFIX_RE = re.compile(r"^(\d+(?:\.\d+)*[\s、.．]+)")


def _normalize_title(text: str) -> str:
    return _NUM_PREFIX_RE.sub("", text).strip().lower()


def _find_block_for_title(title: str, blocks: ContentBlocksFile, content_md: str) -> int | None:
    target = _normalize_title(title)
    for block in blocks.blocks:
        if block.block_type not in {"paragraph", "heading"}:
            continue
        preview = (block.text_preview or content_md[block.char_start : block.char_end]).strip()
        normalized = _normalize_title(preview)
        if normalized == target or target in normalized or normalized in target:
            return block.block_index
    return None


def enrich_outline_anchors(
    tree: OutlineTree,
    blocks: ContentBlocksFile,
    *,
    content_md: str,
) -> OutlineTree:
    block_by_index = {b.block_index: b for b in blocks.blocks}
    new_nodes: list[OutlineNode] = []
    for node in tree.nodes:
        anchor = node.anchor.model_copy()
        idx = anchor.block_index
        if idx is None or idx not in block_by_index:
            idx = _find_block_for_title(node.title, blocks, content_md)
        if idx is not None and idx in block_by_index:
            block = block_by_index[idx]
            anchor.block_index = idx
            anchor.block_start = idx
            anchor.char_start = block.char_start
            anchor.char_end = block.char_end
        new_nodes.append(node.model_copy(update={"anchor": anchor}))
    return tree.model_copy(update={"nodes": new_nodes})
