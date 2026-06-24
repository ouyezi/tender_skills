from __future__ import annotations

import json
import re
from dataclasses import dataclass

from doc_chunk.chunk.tokenizer import estimate_tokens
from doc_chunk.models.chunk import ChunkIndex, ContentChunk
from doc_chunk.models.outline import OutlineNode, OutlineTree
from doc_chunk.workspace.layout import OutputWorkspace

from tender_insights.common.content_source import InterpretSource
from tender_insights.common.section_slice import slice_for_llm
from tender_insights.config import InsightsConfig

_HEADING_RE = re.compile(r"^(#{1,8})[ \t]+(.+?)[ \t#]*$", re.MULTILINE)


@dataclass(frozen=True, slots=True)
class Segment:
    segment_id: str
    section_path: list[str]
    markdown: str
    char_start: int
    char_end: int
    token_estimate: int


@dataclass(slots=True)
class _RawSegment:
    section_path: list[str]
    markdown: str
    char_start: int
    char_end: int
    token_estimate: int



def _find_char_range(source_md: str, markdown: str, hint_start: int = 0) -> tuple[int, int]:
    needle = markdown.strip()
    if not needle:
        return hint_start, hint_start
    pos = source_md.find(needle, hint_start)
    if pos >= 0:
        return pos, pos + len(needle)
    short = needle[: min(120, len(needle))]
    pos = source_md.find(short, hint_start)
    if pos >= 0:
        return pos, pos + len(short)
    return hint_start, min(len(source_md), hint_start + len(needle))


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


def _split_markdown_sections(content_md: str, outline: OutlineTree) -> list[_RawSegment]:
    matches = list(_HEADING_RE.finditer(content_md))
    outline_paths = _build_outline_title_paths(outline.nodes)
    sections: list[tuple[list[str], str, int, int]] = []

    if not matches:
        title = outline.nodes[0].title if outline.nodes else "Document"
        return [
            _RawSegment(
                section_path=[],
                markdown=content_md,
                char_start=0,
                char_end=len(content_md),
                token_estimate=estimate_tokens(content_md),
            )
        ]

    if matches[0].start() > 0 and content_md[: matches[0].start()].strip():
        preface = content_md[: matches[0].start()]
        sections.append(([], preface, 0, matches[0].start()))

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
        body = content_md[start:end]
        sections.append((section_path, body, start, end))

    return [
        _RawSegment(
            section_path=path,
            markdown=body,
            char_start=start,
            char_end=end,
            token_estimate=estimate_tokens(body),
        )
        for path, body, start, end in sections
    ]


def _load_chunks(workspace: OutputWorkspace, source_md: str) -> list[_RawSegment] | None:
    index_path = workspace.chunks_dir / "index.json"
    if not index_path.exists():
        return None
    index = ChunkIndex.model_validate_json(index_path.read_text(encoding="utf-8"))
    if not index.chunks:
        return None

    raw: list[_RawSegment] = []
    cursor = 0
    for entry in index.chunks:
        chunk_path = workspace.chunks_dir / entry.path
        if not chunk_path.exists():
            continue
        chunk = ContentChunk.model_validate(json.loads(chunk_path.read_text(encoding="utf-8")))
        md = chunk.markdown
        char_start, char_end = _find_char_range(source_md, md, hint_start=cursor)
        cursor = char_start
        raw.append(
            _RawSegment(
                section_path=list(entry.section_path or chunk.section_path),
                markdown=md,
                char_start=char_start,
                char_end=char_end,
                token_estimate=chunk.token_estimate or estimate_tokens(md),
            )
        )
    return raw or None


def _merge_small_segments(raw: list[_RawSegment], min_tokens: int) -> list[_RawSegment]:
    """Merge undersized segments with subsequent chunks until min_tokens is reached."""
    if not raw:
        return raw
    merged: list[_RawSegment] = []
    idx = 0
    while idx < len(raw):
        current = raw[idx]
        while current.token_estimate < min_tokens and idx + 1 < len(raw):
            nxt = raw[idx + 1]
            combined_md = current.markdown.rstrip() + "\n\n" + nxt.markdown.lstrip()
            current = _RawSegment(
                section_path=current.section_path or nxt.section_path,
                markdown=combined_md,
                char_start=current.char_start,
                char_end=nxt.char_end,
                token_estimate=estimate_tokens(combined_md),
            )
            idx += 1
        merged.append(current)
        idx += 1
    return merged


def _split_large_segments(raw: list[_RawSegment], max_tokens: int) -> list[_RawSegment]:
    out: list[_RawSegment] = []
    for seg in raw:
        parts = _split_oversized(seg.markdown, max_tokens)
        for part in parts:
            part_tokens = estimate_tokens(part)
            char_start, char_end = _find_char_range(
                seg.markdown if len(parts) == 1 else part,
                part,
                hint_start=0,
            )
            if len(parts) == 1:
                char_start, char_end = seg.char_start, seg.char_end
            else:
                char_start = seg.char_start + char_start
                char_end = seg.char_start + char_end
            out.append(
                _RawSegment(
                    section_path=seg.section_path,
                    markdown=part,
                    char_start=char_start,
                    char_end=char_end,
                    token_estimate=part_tokens,
                )
            )
    return out


def plan_segments(
    workspace: OutputWorkspace,
    source: InterpretSource,
    outline: OutlineTree,
    *,
    config: InsightsConfig,
) -> list[Segment]:
    from tender_insights.common.scoring_segments import (
        build_scoring_table_segments,
        expand_short_segment_markdown,
        inject_scoring_tables_into_markdown,
        is_scoring_host_section_path,
    )

    source_md = source.markdown
    raw = _load_chunks(workspace, source_md)
    if raw is None:
        raw = _split_markdown_sections(source_md, outline)

    raw = [seg for seg in raw if seg.markdown.strip()]
    raw = _merge_small_segments(raw, config.segment_min_tokens)
    raw = _split_large_segments(raw, config.segment_max_tokens)

    segments: list[Segment] = []
    keyword_match = config.segment_keyword_match_enabled
    for idx, seg in enumerate(raw, start=1):
        llm_md = slice_for_llm(
            workspace,
            source_md,
            seg.char_start,
            seg.char_end,
            blocks=source.blocks,
        )
        if keyword_match:
            llm_md = expand_short_segment_markdown(
                workspace,
                source_md,
                seg,
                llm_md,
                blocks=source.blocks,
            )
        if not llm_md.strip():
            continue
        if (
            keyword_match
            and source.blocks is not None
            and is_scoring_host_section_path(seg.section_path)
            and len(llm_md.strip()) < 200
        ):
            llm_md = inject_scoring_tables_into_markdown(
                workspace,
                markdown=llm_md,
                char_start=seg.char_start,
                char_end=seg.char_end,
                blocks=source.blocks,
            )
        segments.append(
            Segment(
                segment_id=f"seg-{idx:03d}",
                section_path=seg.section_path,
                markdown=llm_md,
                char_start=seg.char_start,
                char_end=seg.char_end,
                token_estimate=estimate_tokens(llm_md),
            )
        )

    if keyword_match and source.blocks is not None:
        host_path = segments[-1].section_path if segments else []
        dedicated = build_scoring_table_segments(
            workspace,
            blocks=source.blocks,
            host_section_path=host_path,
            max_segments=5,
        )
        existing_markdown = {s.markdown.strip() for s in segments}
        for seg in dedicated:
            if seg.markdown.strip() in existing_markdown:
                continue
            segments.append(seg)
            existing_markdown.add(seg.markdown.strip())

    return segments
