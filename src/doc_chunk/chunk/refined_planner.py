from __future__ import annotations

import re

from doc_chunk.chunk.tokenizer import estimate_tokens
from doc_chunk.models.chunk import ContentChunk
from doc_chunk.models.outline import OutlineMappingFile, OutlineTree

_IMAGE_RE = re.compile(r"!\[[^\]]*]\(([^)]+)\)")


def _split_oversized(markdown: str, max_tokens: int) -> list[str]:
    if estimate_tokens(markdown) <= max_tokens:
        return [markdown]

    parts: list[str] = []
    current: list[str] = []
    for line in markdown.splitlines(keepends=True):
        candidate = "".join(current + [line])
        if current and estimate_tokens(candidate) > max_tokens:
            parts.append("".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        parts.append("".join(current))
    return parts or [markdown]


def _build_paths(refined_outline: OutlineTree) -> dict[str, list[str]]:
    by_id = {node.node_id: node for node in refined_outline.nodes}
    paths: dict[str, list[str]] = {}
    for node in refined_outline.nodes:
        chain: list[str] = []
        cursor = node
        seen: set[str] = set()
        while cursor and cursor.node_id not in seen:
            seen.add(cursor.node_id)
            chain.append(cursor.title)
            cursor = by_id.get(cursor.parent_id) if cursor.parent_id else None
        paths[node.node_id] = list(reversed(chain))
    return paths


def plan_chunks_from_refined(
    content_md: str,
    refined_outline: OutlineTree,
    mapping_file: OutlineMappingFile,
    *,
    max_tokens: int = 20_000,
) -> list[ContentChunk]:
    if max_tokens <= 0:
        raise ValueError("max_tokens must be positive")

    node_by_id = {node.node_id: node for node in refined_outline.nodes}
    paths = _build_paths(refined_outline)
    chunks: list[ContentChunk] = []
    chunk_idx = 1

    for mapping in mapping_file.mappings:
        node = node_by_id.get(mapping.refined_node_id)
        if node is None:
            continue
        start = int(mapping.markdown_range.get("char_start", 0))
        end = int(mapping.markdown_range.get("char_end", start))
        start = max(0, min(len(content_md), start))
        end = max(start, min(len(content_md), end))
        raw_markdown = content_md[start:end]
        if not raw_markdown.strip():
            continue

        for part_idx, part in enumerate(_split_oversized(raw_markdown, max_tokens)):
            markdown = part if part.endswith("\n") else f"{part}\n"
            chunks.append(
                ContentChunk(
                    chunk_id=f"chunk-{chunk_idx:04d}",
                    title=node.title,
                    section_path=paths.get(node.node_id, [node.title]),
                    heading_level=node.level if part_idx == 0 else None,
                    markdown=markdown,
                    source_file="content.md",
                    token_estimate=estimate_tokens(markdown),
                    image_refs=[m.group(1) for m in _IMAGE_RE.finditer(markdown)],
                    outline_source="refined",
                    refined_node_id=node.node_id,
                    original_node_ids=list(mapping.source_node_ids),
                )
            )
            chunk_idx += 1

    for idx, chunk in enumerate(chunks):
        chunk.previous_chunk_id = chunks[idx - 1].chunk_id if idx > 0 else None
        chunk.next_chunk_id = chunks[idx + 1].chunk_id if idx + 1 < len(chunks) else None
    return chunks
