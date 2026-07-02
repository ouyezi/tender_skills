from __future__ import annotations

from doc_chunk.locate.heading_starts import parse_body_headings
from doc_chunk.models.content_block import ContentBlockRecord, ContentBlocksFile
from doc_chunk.outline.anchor_enricher import enrich_outline_anchors
from tests.unit.test_heading_starts_shared import TOC_BID_CONTENT_MD, _toc_bid_tree
from viewer.services.section_slice import slice_section


def _toc_bid_blocks(content_md: str) -> ContentBlocksFile:
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


def test_enrich_skips_toc_for_section_2_1() -> None:
    tree = _toc_bid_tree()
    blocks = _toc_bid_blocks(TOC_BID_CONTENT_MD)
    enriched = enrich_outline_anchors(tree, blocks, content_md=TOC_BID_CONTENT_MD)
    node = next(n for n in enriched.nodes if n.node_id == "n2")
    first_body = min(h.char_start for h in parse_body_headings(TOC_BID_CONTENT_MD))
    assert node.anchor.char_start is not None
    assert node.anchor.char_start >= first_body
    assert "2.1合同条款偏离表" in TOC_BID_CONTENT_MD[node.anchor.char_start : node.anchor.char_start + 40]


def test_enrich_char_start_matches_viewer() -> None:
    tree = _toc_bid_tree()
    blocks = _toc_bid_blocks(TOC_BID_CONTENT_MD)
    enriched = enrich_outline_anchors(tree, blocks, content_md=TOC_BID_CONTENT_MD)
    for node in enriched.nodes:
        section = slice_section(TOC_BID_CONTENT_MD, enriched, node.node_id)
        assert node.anchor.char_start == section.char_start, node.node_id


def test_enrich_does_not_use_fuzzy_first_match_in_toc() -> None:
    tree = _toc_bid_tree()
    blocks = _toc_bid_blocks(TOC_BID_CONTENT_MD)
    enriched = enrich_outline_anchors(tree, blocks, content_md=TOC_BID_CONTENT_MD)
    toc_end = TOC_BID_CONTENT_MD.index("# 服务偏离表\n\n")
    for node in enriched.nodes:
        if node.anchor.char_start is None:
            continue
        assert node.anchor.char_start >= toc_end or node.node_id == "n1"
