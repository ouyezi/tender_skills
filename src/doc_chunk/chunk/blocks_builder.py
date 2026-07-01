from __future__ import annotations

import re

from doc_chunk.models.chunk import ChunkBlock
from doc_chunk.table.placeholders import parse_table_ref_from_line

MAX_BLOCK_TEXT_CHARS = 32_000
_TABLE_LINE_RE = re.compile(r"^\|.+\|$")
_IMAGE_RE = re.compile(r"!\[[^\]]*]\(([^)]+)\)")


def _truncate(text: str) -> str:
    if len(text) <= MAX_BLOCK_TEXT_CHARS:
        return text
    return text[:MAX_BLOCK_TEXT_CHARS]


def build_chunk_blocks(*, markdown: str, char_start: int = 0, char_end: int | None = None) -> list[ChunkBlock]:
    del char_start, char_end
    blocks: list[ChunkBlock] = []
    table_lines: list[str] = []
    paragraph_lines: list[str] = []
    pending_table_ref: str | None = None

    def flush_paragraph() -> None:
        nonlocal paragraph_lines
        if not paragraph_lines:
            return
        text = _truncate("\n".join(paragraph_lines).strip())
        if text:
            blocks.append(ChunkBlock(type="paragraph", text=text))
        paragraph_lines = []

    def flush_table() -> None:
        nonlocal table_lines, pending_table_ref
        if not table_lines:
            return
        text = _truncate("\n".join(table_lines))
        blocks.append(ChunkBlock(type="table", text=text, table_ref=pending_table_ref))
        table_lines = []
        pending_table_ref = None

    for line in markdown.splitlines():
        table_ref_on_line = parse_table_ref_from_line(line)
        if table_ref_on_line:
            flush_paragraph()
            flush_table()
            pending_table_ref = table_ref_on_line
            continue
        image_match = _IMAGE_RE.match(line.strip())
        if image_match:
            flush_paragraph()
            flush_table()
            blocks.append(ChunkBlock(type="image", image_ref=image_match.group(1)))
            continue
        if _TABLE_LINE_RE.match(line.strip()):
            flush_paragraph()
            table_lines.append(line)
            continue
        if table_lines:
            flush_table()
        if line.strip():
            paragraph_lines.append(line)
        elif paragraph_lines:
            flush_paragraph()

    flush_paragraph()
    flush_table()
    return blocks
