from __future__ import annotations

from doc_chunk.models.content_block import ContentBlockRecord, ContentBlocksFile
from doc_chunk.models.outline import Anchor, OutlineNode, OutlineTree
from doc_chunk.outline.anchor_enricher import enrich_outline_anchors


def test_enrich_preserves_bookmark_block_index() -> None:
    content_md = "一、服务方案1\n\n# 一、服务方案\n\nbody\n"
    blocks = ContentBlocksFile(
        blocks=[
            ContentBlockRecord(
                block_index=0,
                block_type="paragraph",
                char_start=0,
                char_end=8,
                text_preview="一、服务方案1",
            ),
            ContentBlockRecord(
                block_index=1,
                block_type="heading",
                char_start=9,
                char_end=18,
                text_preview="# 一、服务方案",
            ),
        ]
    )
    tree = OutlineTree(
        strategy="toc",
        nodes=[
            OutlineNode(
                node_id="n1",
                title="一、服务方案",
                level=1,
                parent_id=None,
                sort_order=0,
                anchor=Anchor(
                    block_index=1,
                    block_start=1,
                    char_start=9,
                    char_end=18,
                ),
                source_refs=["toc_bookmark:_Toc1"],
            )
        ],
    )
    enriched = enrich_outline_anchors(tree, blocks, content_md=content_md)
    assert enriched.nodes[0].anchor.block_index == 1


def test_enrich_falls_back_when_bookmark_unresolved() -> None:
    content_md = "一、服务方案3\n# 一、服务方案\n"
    blocks = ContentBlocksFile(
        blocks=[
            ContentBlockRecord(
                block_index=0,
                block_type="paragraph",
                char_start=0,
                char_end=8,
                text_preview="一、服务方案3",
            ),
            ContentBlockRecord(
                block_index=1,
                block_type="heading",
                char_start=8,
                char_end=17,
                text_preview="# 一、服务方案",
            ),
        ]
    )
    tree = OutlineTree(
        strategy="toc",
        nodes=[
            OutlineNode(
                node_id="n1",
                title="一、服务方案",
                level=1,
                parent_id=None,
                sort_order=0,
                anchor=Anchor(block_index=0),
                source_refs=["toc_bookmark:_TocMissing"],
            )
        ],
    )
    enriched = enrich_outline_anchors(tree, blocks, content_md=content_md)
    assert enriched.nodes[0].anchor.block_index == 1
