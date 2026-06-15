from doc_chunk.models.content_block import ContentBlockRecord, ContentBlocksFile
from doc_chunk.models.outline import Anchor, OutlineNode, OutlineTree
from doc_chunk.tree.builder import build_document_tree, build_document_tree_with_warnings


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


def test_document_tree_node_ids_unique_with_image_before_heading() -> None:
    blocks = ContentBlocksFile(
        blocks=[
            ContentBlockRecord(
                block_index=0, block_type="image", char_start=0, char_end=10, image_ref="images/cover.png"
            ),
            ContentBlockRecord(
                block_index=1, block_type="paragraph", char_start=10, char_end=30, text_preview="1. 封面"
            ),
        ]
    )
    outline = OutlineTree(
        strategy="toc",
        nodes=[
            OutlineNode(
                node_id="n1",
                title="封面",
                level=1,
                parent_id=None,
                sort_order=0,
                anchor=Anchor(char_start=0, block_start=0),
            ),
            OutlineNode(
                node_id="n2",
                title="正文",
                level=1,
                parent_id=None,
                sort_order=1,
                anchor=Anchor(char_start=10, block_start=1),
            ),
        ],
    )
    tree = build_document_tree(blocks, outline, content_md="![](images/cover.png)\n\n1. 封面\n\n")
    ids = [n.node_id for n in tree.nodes]
    assert len(ids) == len(set(ids)), f"duplicate node_id: {ids}"
    heading_outline_ids = {n.outline_node_id for n in tree.nodes if n.node_type == "heading" and n.outline_node_id}
    assert heading_outline_ids == {"n1", "n2"}


def test_synthesize_heading_when_anchor_on_image() -> None:
    blocks = ContentBlocksFile(
        blocks=[
            ContentBlockRecord(
                block_index=0, block_type="image", char_start=0, char_end=10, image_ref="images/cover.png"
            ),
            ContentBlockRecord(
                block_index=1, block_type="paragraph", char_start=10, char_end=30, text_preview="正文"
            ),
        ]
    )
    outline = OutlineTree(
        strategy="toc",
        nodes=[
            OutlineNode(
                node_id="n1", title="封面", level=1, parent_id=None, sort_order=0,
                anchor=Anchor(char_start=0, block_start=0),
            ),
        ],
    )
    tree = build_document_tree(blocks, outline, content_md="![](images/cover.png)\n\n正文\n\n")
    headings = [n for n in tree.nodes if n.node_type == "heading" and n.outline_node_id == "n1"]
    assert len(headings) == 1
    image_node = next(n for n in tree.nodes if n.node_type == "image")
    heading = headings[0]
    assert tree.nodes.index(heading) < tree.nodes.index(image_node)


def test_synthesized_headings_on_same_block_preserve_outline_order() -> None:
    blocks = ContentBlocksFile(
        blocks=[
            ContentBlockRecord(
                block_index=0, block_type="image", char_start=0, char_end=10, image_ref="images/shared.png"
            ),
        ]
    )
    outline = OutlineTree(
        strategy="toc",
        nodes=[
            OutlineNode(
                node_id="n1", title="封面A", level=1, parent_id=None, sort_order=0,
                anchor=Anchor(char_start=0, block_start=0),
            ),
            OutlineNode(
                node_id="n2", title="封面B", level=1, parent_id=None, sort_order=1,
                anchor=Anchor(char_start=0, block_start=0),
            ),
        ],
    )
    tree = build_document_tree(blocks, outline, content_md="![](images/shared.png)\n\n")
    synth = [n for n in tree.nodes if n.node_type == "heading" and n.outline_node_id in {"n1", "n2"}]
    assert [n.outline_node_id for n in synth] == ["n1", "n2"]
    assert tree.nodes.index(synth[0]) < tree.nodes.index(synth[1])


def test_duplicate_anchor_emits_warning() -> None:
    blocks = ContentBlocksFile(
        blocks=[
            ContentBlockRecord(
                block_index=0, block_type="image", char_start=0, char_end=10, image_ref="images/shared.png"
            ),
        ]
    )
    outline = OutlineTree(
        strategy="toc",
        nodes=[
            OutlineNode(
                node_id="n1", title="A", level=1, parent_id=None, sort_order=0,
                anchor=Anchor(char_start=0, block_start=0),
            ),
            OutlineNode(
                node_id="n2", title="B", level=1, parent_id=None, sort_order=1,
                anchor=Anchor(char_start=0, block_start=0),
            ),
        ],
    )
    _tree, warnings = build_document_tree_with_warnings(blocks, outline, content_md="![](x)\n\n")
    assert "outline_duplicate_anchor:0" in warnings
