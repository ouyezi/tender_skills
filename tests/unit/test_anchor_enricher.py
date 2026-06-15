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
