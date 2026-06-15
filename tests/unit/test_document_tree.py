from doc_chunk.models.content_block import ContentBlockRecord, ContentBlocksFile
from doc_chunk.models.outline import Anchor, OutlineNode, OutlineTree
from doc_chunk.tree.builder import build_document_tree


def test_build_document_tree_heading_parent_links() -> None:
    blocks = ContentBlocksFile(
        blocks=[
            ContentBlockRecord(
                block_index=0, block_type="heading", char_start=0, char_end=12, text_preview="1. 技术方案"
            ),
            ContentBlockRecord(
                block_index=1, block_type="paragraph", char_start=12, char_end=30, text_preview="正文"
            ),
            ContentBlockRecord(
                block_index=2, block_type="table", char_start=30, char_end=60, text_preview="|a|b|"
            ),
            ContentBlockRecord(
                block_index=3,
                block_type="image",
                char_start=60,
                char_end=90,
                image_ref="images/x.png",
            ),
        ]
    )
    outline = OutlineTree(
        strategy="content_heuristic",
        nodes=[
            OutlineNode(
                node_id="n1",
                title="技术方案",
                level=1,
                parent_id=None,
                sort_order=0,
                anchor=Anchor(char_start=0, block_start=0),
            )
        ],
    )
    tree = build_document_tree(blocks, outline, content_md="1. 技术方案\n\n正文\n\n|a|b|\n\n![](images/x.png)\n")
    types = {n.node_type for n in tree.nodes}
    assert types >= {"heading", "paragraph", "table", "image"}
    heading = next(n for n in tree.nodes if n.node_type == "heading")
    assert heading.outline_node_id == "n1"
    para = next(n for n in tree.nodes if n.node_type == "paragraph")
    assert para.parent_id == heading.node_id
