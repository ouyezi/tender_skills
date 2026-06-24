from __future__ import annotations

import re

from doc_chunk.chunk.tokenizer import estimate_tokens
from doc_chunk.models.content_block import ContentBlockRecord, ContentBlocksFile
from doc_chunk.table.access import load_table_model
from doc_chunk.workspace.layout import OutputWorkspace

from tender_insights.common.segment_planner import Segment

_SCORING_PATH_KEYWORDS = ("评分", "评审办法", "评标", "评审", "分值", "得分")
_SCORING_TABLE_HEADER_KEYWORDS = ("评分说明", "分值", "得分")
_SCORE_PATTERN = re.compile(r"\d+\s*[-~–—]\s*\d+\s*分")
_INJECT_LOOKAHEAD_CHARS = 8000


def is_scoring_section_path(section_path: list[str]) -> bool:
    haystack = " ".join(section_path)
    return any(kw in haystack for kw in _SCORING_PATH_KEYWORDS)


def is_scoring_table_llm_text(llm_text: str) -> bool:
    if any(kw in llm_text for kw in _SCORING_TABLE_HEADER_KEYWORDS):
        return True
    return bool(_SCORE_PATTERN.search(llm_text))


def _iter_scoring_table_blocks(
    workspace: OutputWorkspace,
    blocks: ContentBlocksFile,
    *,
    char_start: int | None = None,
    char_end: int | None = None,
) -> list[tuple[ContentBlockRecord, str]]:
    found: list[tuple[ContentBlockRecord, str]] = []
    for block in blocks.blocks:
        if block.block_type != "table" or not block.table_ref:
            continue
        if char_start is not None and char_end is not None:
            window_end = char_end + _INJECT_LOOKAHEAD_CHARS
            if block.char_end <= char_start or block.char_start >= window_end:
                continue
        sidecar = load_table_model(workspace, block.table_ref)
        llm_text = sidecar.llm_text.strip()
        if is_scoring_table_llm_text(llm_text):
            found.append((block, llm_text))
    return found


def inject_scoring_tables_into_markdown(
    workspace: OutputWorkspace,
    *,
    markdown: str,
    char_start: int,
    char_end: int,
    blocks: ContentBlocksFile,
) -> str:
    tables = _iter_scoring_table_blocks(
        workspace, blocks, char_start=char_start, char_end=char_end
    )
    if not tables:
        return markdown
    parts = [markdown.rstrip(), ""]
    for _block, llm_text in tables:
        parts.append(llm_text)
    return "\n\n".join(p for p in parts if p)


def build_scoring_table_segments(
    workspace: OutputWorkspace,
    *,
    blocks: ContentBlocksFile,
    host_section_path: list[str] | None = None,
    max_segments: int = 5,
) -> list[Segment]:
    segments: list[Segment] = []
    seen_refs: set[str] = set()
    for block, llm_text in _iter_scoring_table_blocks(workspace, blocks):
        if not block.table_ref or block.table_ref in seen_refs:
            continue
        seen_refs.add(block.table_ref)
        seg_id = f"seg-scoring-{len(segments) + 1:03d}"
        md = f"# 评分表\n\n{llm_text}"
        segments.append(
            Segment(
                segment_id=seg_id,
                section_path=host_section_path or [],
                markdown=md,
                char_start=block.char_start,
                char_end=block.char_end,
                token_estimate=estimate_tokens(md),
            )
        )
        if len(segments) >= max_segments:
            break
    return segments
