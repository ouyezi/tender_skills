from __future__ import annotations

from pathlib import Path

from doc_chunk.models.content_block import ContentBlocksFile
from doc_chunk.models.table_model import TableSidecar
from doc_chunk.workspace.layout import OutputWorkspace


def load_table_model(workspace: OutputWorkspace | Path, table_ref: str) -> TableSidecar:
    root = workspace.root if isinstance(workspace, OutputWorkspace) else Path(workspace)
    path = root / table_ref
    return TableSidecar.model_validate_json(path.read_text(encoding="utf-8"))


def substitute_tables_for_llm(
    content_md: str,
    blocks: ContentBlocksFile,
    *,
    workspace: OutputWorkspace,
    char_start: int = 0,
    char_end: int | None = None,
) -> str:
    end = char_end if char_end is not None else len(content_md)
    replacements: list[tuple[int, int, str]] = []
    for block in blocks.blocks:
        if block.block_type != "table" or not block.table_ref:
            continue
        if block.char_end <= char_start or block.char_start >= end:
            continue
        sidecar = load_table_model(workspace, block.table_ref)
        replacements.append((block.char_start, block.char_end, sidecar.llm_text.strip() + "\n\n"))
    if not replacements:
        return content_md[char_start:end]
    replacements.sort(key=lambda x: x[0])
    parts: list[str] = []
    cursor = char_start
    for s, e, text in replacements:
        parts.append(content_md[cursor:s])
        parts.append(text)
        cursor = e
    parts.append(content_md[cursor:end])
    return "".join(parts)
