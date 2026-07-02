from __future__ import annotations

import json
from pathlib import Path

from doc_chunk.models.content_block import ContentBlockRecord, ContentBlocksFile
from doc_chunk.models.outline import OutlineTree
from doc_chunk.outline.builder import build_outline_from_workspace
from doc_chunk.outline.content_heading_enricher import (
    enrich_content_md_headings,
    resync_blocks_char_offsets,
)
from doc_chunk.workspace.layout import OutputWorkspace
from tests.unit.test_heading_starts_shared import TOC_BID_CONTENT_MD, _toc_bid_tree
from viewer.services.section_slice import slice_section


def _toc_bid_tree_clean() -> OutlineTree:
    nodes = []
    for node in _toc_bid_tree().nodes:
        title = node.title
        if node.node_id == "n1":
            title = "服务偏离表"
        elif node.node_id == "n2":
            title = "2.1 合同条款偏离表"
        elif node.node_id == "n3":
            title = "2.2 技术条款偏离表"
        nodes.append(node.model_copy(update={"title": title}))
    return _toc_bid_tree().model_copy(update={"nodes": nodes})


def _blocks_from_lines(content_md: str) -> ContentBlocksFile:
    blocks: list[ContentBlockRecord] = []
    offset = 0
    for block_index, line in enumerate(content_md.splitlines(keepends=True)):
        start = offset
        end = start + len(line)
        offset = end
        block_type = "heading" if line.lstrip().startswith("#") else "paragraph"
        blocks.append(
            ContentBlockRecord(
                block_index=block_index,
                block_type=block_type,
                char_start=start,
                char_end=end,
                text_preview=line.strip() or None,
            )
        )
    return ContentBlocksFile(blocks=blocks)


CONTENT_WITHOUT_SECTION_PREFIX = (
    "2025年生日福利预算\n\n投标/响应文件\n\n"
    "# 投标函\t1\n"
    "# 合同条款偏离表\t12\n"
    "## 服务偏离表\t3\n"
    "# 服务偏离表\n\n"
    "服务偏离概述\n\n"
    "### 合同条款偏离表\n\n"
    "| 序号 | 条款 |\n|---|---|\n| 1 | foo |\n\n"
    "### 技术条款偏离表\n\n"
    "技术偏离正文\n"
)


def test_enrich_content_md_headings_adds_toc_prefixes() -> None:
    tree = _toc_bid_tree_clean()
    enriched, edits = enrich_content_md_headings(CONTENT_WITHOUT_SECTION_PREFIX, tree)

    assert edits
    assert "### 2.1 合同条款偏离表" in enriched
    assert "### 2.2 技术条款偏离表" in enriched
    assert "### 合同条款偏离表" not in enriched


def test_enrich_content_md_headings_noop_when_titles_already_match() -> None:
    tree = _toc_bid_tree_clean()
    content_md = TOC_BID_CONTENT_MD.replace("2.1合同条款偏离表", "2.1 合同条款偏离表").replace(
        "2.2技术条款偏离表", "2.2 技术条款偏离表"
    )
    enriched, edits = enrich_content_md_headings(content_md, tree)
    assert enriched == content_md
    assert edits == []


def test_enrich_content_md_headings_skips_non_toc_strategy() -> None:
    tree = _toc_bid_tree().model_copy(update={"strategy": "heading_heuristic"})
    enriched, edits = enrich_content_md_headings(CONTENT_WITHOUT_SECTION_PREFIX, tree)
    assert enriched == CONTENT_WITHOUT_SECTION_PREFIX
    assert edits == []


def test_resync_blocks_char_offsets_updates_heading_preview() -> None:
    tree = _toc_bid_tree_clean()
    blocks = _blocks_from_lines(CONTENT_WITHOUT_SECTION_PREFIX)
    enriched, edits = enrich_content_md_headings(CONTENT_WITHOUT_SECTION_PREFIX, tree)
    resynced = resync_blocks_char_offsets(blocks, edits, content_md=enriched)

    heading_blocks = [b for b in resynced.blocks if b.block_type == "heading"]
    previews = [b.text_preview for b in heading_blocks if b.text_preview and "合同条款偏离表" in b.text_preview]
    assert any(p.startswith("### 2.1 合同条款偏离表") for p in previews)


def test_builder_pipeline_enriches_content_and_keeps_anchor_alignment(
    monkeypatch, tmp_path: Path
) -> None:
    ws = OutputWorkspace.create(tmp_path / "ws", overwrite=False)
    ws.content_path.write_text(CONTENT_WITHOUT_SECTION_PREFIX, encoding="utf-8")
    blocks = _blocks_from_lines(CONTENT_WITHOUT_SECTION_PREFIX)
    ws.content_blocks_path.write_text(blocks.model_dump_json(indent=2), encoding="utf-8")

    source_path = tmp_path / "a.docx"
    source_path.write_bytes(b"docx")
    monkeypatch.setattr(
        "doc_chunk.outline.builder.extract_docx_toc_outline",
        lambda _p: _toc_bid_tree_clean(),
    )
    monkeypatch.setattr("doc_chunk.outline.builder.extract_pdf_bookmark_outline", lambda _p: None)

    tree = build_outline_from_workspace(ws, source_path)
    content_md = ws.content_path.read_text(encoding="utf-8")

    assert "### 2.1 合同条款偏离表" in content_md
    for node in tree.nodes:
        section = slice_section(content_md, tree, node.node_id)
        assert node.anchor.char_start == section.char_start, node.node_id
        if node.node_id == "n2":
            assert section.markdown.splitlines()[0].startswith("### 2.1 合同条款偏离表")

    outline_data = json.loads((ws.root / "outline.json").read_text(encoding="utf-8"))
    assert outline_data["strategy"] == "toc"
