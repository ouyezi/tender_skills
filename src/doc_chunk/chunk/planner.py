from __future__ import annotations

import re
from dataclasses import dataclass

from doc_chunk.chunk.tokenizer import estimate_tokens
from doc_chunk.models.chunk import ContentChunk
from doc_chunk.models.outline import OutlineNode, OutlineTree

_HEADING_RE = re.compile(r"^(#{1,8})[ \t]+(.+?)[ \t#]*$", re.MULTILINE)
_IMAGE_RE = re.compile(r"!\[[^\]]*]\(([^)]+)\)")


@dataclass(slots=True)
class _Section:
    title: str
    heading_level: int | None
    section_path: list[str]
    markdown: str


def _build_outline_title_paths(nodes: list[OutlineNode]) -> dict[str, list[str]]:
    node_map = {node.node_id: node for node in nodes}
    result: dict[str, list[str]] = {}
    for node in nodes:
        if node.title in result:
            continue
        path: list[str] = []
        cursor: OutlineNode | None = node
        visited: set[str] = set()
        while cursor is not None and cursor.node_id not in visited:
            visited.add(cursor.node_id)
            path.append(cursor.title)
            cursor = node_map.get(cursor.parent_id) if cursor.parent_id else None
        result[node.title] = list(reversed(path))
    return result


def _split_markdown_sections(content_md: str, outline_tree: OutlineTree) -> list[_Section]:
    matches = list(_HEADING_RE.finditer(content_md))
    outline_paths = _build_outline_title_paths(outline_tree.nodes)

    if not matches:
        title = outline_tree.nodes[0].title if outline_tree.nodes else "Document"
        return [_Section(title=title, heading_level=None, section_path=[], markdown=content_md)]

    sections: list[_Section] = []
    if matches[0].start() > 0 and content_md[: matches[0].start()].strip():
        sections.append(
            _Section(
                title="Preface",
                heading_level=None,
                section_path=[],
                markdown=content_md[: matches[0].start()],
            )
        )

    stack: list[tuple[int, str]] = []
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(content_md)
        level = len(match.group(1))
        title = match.group(2).strip()

        while stack and stack[-1][0] >= level:
            stack.pop()
        computed_path = [item_title for _, item_title in stack] + [title]
        stack.append((level, title))
        section_path = outline_paths.get(title, computed_path)

        sections.append(
            _Section(
                title=title,
                heading_level=level,
                section_path=section_path,
                markdown=content_md[start:end],
            )
        )
    return sections


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


def plan_chunks_from_outline(
    content_md: str,
    outline_tree: OutlineTree,
    max_tokens: int = 20_000,
) -> list[ContentChunk]:
    if max_tokens <= 0:
        raise ValueError("max_tokens must be positive")

    sections = _split_markdown_sections(content_md, outline_tree)
    chunks: list[ContentChunk] = []
    chunk_index = 1

    for section in sections:
        parts = _split_oversized(section.markdown, max_tokens)
        for part_idx, part in enumerate(parts):
            chunk = ContentChunk(
                chunk_id=f"chunk-{chunk_index:04d}",
                title=section.title,
                section_path=list(section.section_path),
                heading_level=section.heading_level if part_idx == 0 else None,
                markdown=part if part.endswith("\n") else f"{part}\n",
                source_file="content.md",
                token_estimate=estimate_tokens(part),
                image_refs=[m.group(1) for m in _IMAGE_RE.finditer(part)],
            )
            chunks.append(chunk)
            chunk_index += 1

    for idx, chunk in enumerate(chunks):
        chunk.previous_chunk_id = chunks[idx - 1].chunk_id if idx > 0 else None
        chunk.next_chunk_id = chunks[idx + 1].chunk_id if idx + 1 < len(chunks) else None
    return chunks


def plan_chunks(
    content_md: str,
    outline_tree: OutlineTree,
    *,
    max_tokens: int = 20_000,
    markdown_headings_only: bool = False,
) -> list[ContentChunk]:
    if markdown_headings_only:
        return plan_chunks_from_outline(content_md, outline_tree, max_tokens=max_tokens)
    has_char_anchors = any(n.anchor.char_start is not None for n in outline_tree.nodes)
    if has_char_anchors:
        from doc_chunk.chunk.anchor_planner import plan_chunks_from_anchors

        return plan_chunks_from_anchors(content_md, outline_tree, max_tokens=max_tokens)
    return plan_chunks_from_outline(content_md, outline_tree, max_tokens=max_tokens)
