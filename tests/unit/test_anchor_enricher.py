from __future__ import annotations

from doc_chunk.models.content_block import ContentBlockRecord, ContentBlocksFile
from doc_chunk.models.outline import Anchor, OutlineNode, OutlineTree
from doc_chunk.outline.anchor_enricher import enrich_outline_anchors


def test_enrich_fills_char_anchors_from_block_text() -> None:
    blocks = ContentBlocksFile(
        blocks=[
            ContentBlockRecord(
                block_index=0,
                block_type="paragraph",
                char_start=0,
                char_end=10,
                text_preview="1. 技术方案",
            ),
            ContentBlockRecord(
                block_index=1,
                block_type="paragraph",
                char_start=10,
                char_end=30,
                text_preview="方案正文",
            ),
        ]
    )
    tree = OutlineTree(
        strategy="content_heuristic",
        nodes=[
            OutlineNode(
                node_id="n1",
                title="技术方案",
                level=1,
                parent_id=None,
                sort_order=0,
                anchor=Anchor(block_index=0),
            )
        ],
    )
    enriched = enrich_outline_anchors(tree, blocks, content_md="1. 技术方案\n\n方案正文\n\n")
    assert enriched.nodes[0].anchor.char_start == 0
    assert enriched.nodes[0].anchor.char_end == 10
    assert enriched.nodes[0].anchor.block_start == 0


def test_relocate_anchor_from_image_to_following_paragraph() -> None:
    blocks = ContentBlocksFile(
        blocks=[
            ContentBlockRecord(
                block_index=0, block_type="image", char_start=0, char_end=10, image_ref="images/cover.png"
            ),
            ContentBlockRecord(
                block_index=1, block_type="paragraph", char_start=10, char_end=25, text_preview="封面"
            ),
            ContentBlockRecord(
                block_index=2, block_type="paragraph", char_start=25, char_end=40, text_preview="第二章"
            ),
        ]
    )
    tree = OutlineTree(
        strategy="toc",
        nodes=[
            OutlineNode(
                node_id="n1", title="封面", level=1, parent_id=None, sort_order=0,
                anchor=Anchor(block_index=0, block_start=0),
            ),
            OutlineNode(
                node_id="n2", title="第二章", level=1, parent_id=None, sort_order=1,
                anchor=Anchor(block_index=2, block_start=2),
            ),
        ],
    )
    enriched = enrich_outline_anchors(tree, blocks, content_md="![](x)\n\n封面\n\n第二章\n\n")
    assert enriched.nodes[0].anchor.block_start == 1
    assert enriched.nodes[0].anchor.block_index == 1


def test_relocate_prefers_title_match_over_first_paragraph() -> None:
    blocks = ContentBlocksFile(
        blocks=[
            ContentBlockRecord(
                block_index=0, block_type="image", char_start=0, char_end=10, image_ref="images/cover.png"
            ),
            ContentBlockRecord(
                block_index=1, block_type="paragraph", char_start=10, char_end=25, text_preview="无关前言"
            ),
            ContentBlockRecord(
                block_index=2, block_type="paragraph", char_start=25, char_end=40, text_preview="封面"
            ),
        ]
    )
    tree = OutlineTree(
        strategy="toc",
        nodes=[
            OutlineNode(
                node_id="n1", title="封面", level=1, parent_id=None, sort_order=0,
                anchor=Anchor(block_index=0, block_start=0),
            ),
        ],
    )
    enriched = enrich_outline_anchors(tree, blocks, content_md="![](x)\n\n无关前言\n\n封面\n\n")
    assert enriched.nodes[0].anchor.block_start == 2
