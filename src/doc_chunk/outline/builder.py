from __future__ import annotations

import json
from pathlib import Path

from doc_chunk.models.content_block import ContentBlocksFile
from doc_chunk.models.outline import Anchor, OutlineNode, OutlineTree
from doc_chunk.outline.anchor_enricher import enrich_outline_anchors
from doc_chunk.outline.continuity import normalize_outline_cn_continuity
from doc_chunk.outline.heading_heuristic import (
    extract_content_heuristic_outline,
    extract_heading_outline,
)
from doc_chunk.outline.toc_docx import extract_docx_toc_outline
from doc_chunk.outline.toc_pdf import extract_pdf_bookmark_outline
from doc_chunk.workspace.layout import OutputWorkspace


def _write_outline(workspace: OutputWorkspace, tree: OutlineTree) -> Path:
    workspace.outline_path.write_text(
        json.dumps(tree.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return workspace.outline_path


def _flat_outline(workspace: OutputWorkspace, source_path: Path) -> OutlineTree:
    title = source_path.stem or workspace.root.name or "Document"
    return OutlineTree(
        strategy="flat_fallback",
        nodes=[
            OutlineNode(
                node_id="n1",
                title=title,
                level=1,
                parent_id=None,
                sort_order=0,
                anchor=Anchor(block_index=0),
                needs_review=True,
            )
        ],
    )


def build_outline_from_workspace(workspace: OutputWorkspace, source_path: Path) -> OutlineTree:
    content_md = workspace.content_path.read_text(encoding="utf-8") if workspace.content_path.exists() else ""
    suffix = source_path.suffix.lower()

    tree: OutlineTree | None = None
    if suffix in {".docx", ".docm", ".doc"}:
        tree = extract_docx_toc_outline(source_path)
    elif suffix == ".pdf":
        tree = extract_pdf_bookmark_outline(source_path)

    if tree is None:
        tree = extract_heading_outline(content_md)
    if tree is None:
        tree = extract_content_heuristic_outline(content_md)
    if tree is None:
        tree = _flat_outline(workspace, source_path)

    if workspace.content_blocks_path.exists():
        blocks = ContentBlocksFile.model_validate_json(
            workspace.content_blocks_path.read_text(encoding="utf-8")
        )
        tree = enrich_outline_anchors(tree, blocks, content_md=content_md)

    if tree.strategy in {"heading_heuristic", "toc", "content_heuristic"}:
        tree = normalize_outline_cn_continuity(tree, content_md=content_md)

    _write_outline(workspace, tree)
    return tree
