from __future__ import annotations

from doc_chunk.models.content_block import ContentBlocksFile
from doc_chunk.models.outline import OutlineTree
from doc_chunk.table.access import substitute_tables_for_llm
from doc_chunk.workspace.layout import OutputWorkspace


def load_content_blocks(workspace: OutputWorkspace) -> ContentBlocksFile | None:
    path = workspace.content_blocks_path
    if not path.exists():
        return None
    return ContentBlocksFile.model_validate_json(path.read_text(encoding="utf-8"))


def node_char_range(content_md: str, outline: OutlineTree, node_id: str) -> tuple[int, int]:
    node = next(n for n in outline.nodes if n.node_id == node_id)
    start = node.anchor.char_start if node.anchor and node.anchor.char_start is not None else 0
    siblings = sorted(
        [n for n in outline.nodes if n.level == node.level and (n.anchor.char_start or 0) > start],
        key=lambda n: n.anchor.char_start or 10**9,
    )
    end = siblings[0].anchor.char_start if siblings and siblings[0].anchor else len(content_md)
    return start, end


def slice_for_llm(
    workspace: OutputWorkspace,
    content_md: str,
    char_start: int,
    char_end: int,
    *,
    blocks: ContentBlocksFile | None = None,
) -> str:
    """Slice content.md and replace table blocks with llm_text when sidecars exist."""
    if blocks is None:
        blocks = load_content_blocks(workspace)
    if blocks is None:
        return content_md[char_start:char_end]
    return substitute_tables_for_llm(
        content_md,
        blocks,
        workspace=workspace,
        char_start=char_start,
        char_end=char_end,
    )
