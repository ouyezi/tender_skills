from doc_chunk.chunk.anchor_planner import plan_chunks_from_anchors
from doc_chunk.models.outline import Anchor, OutlineNode, OutlineTree


def _no_heading_outline(content_md: str) -> OutlineTree:
    positions = []
    for title in ("总则", "技术方案", "报价"):
        idx = content_md.index(title)
        positions.append(idx)
    return OutlineTree(
        strategy="content_heuristic",
        nodes=[
            OutlineNode(
                node_id="n1",
                title="总则",
                level=1,
                parent_id=None,
                sort_order=0,
                anchor=Anchor(char_start=positions[0], char_end=positions[0] + 2, block_start=0),
            ),
            OutlineNode(
                node_id="n2",
                title="技术方案",
                level=1,
                parent_id=None,
                sort_order=1,
                anchor=Anchor(char_start=positions[1], char_end=positions[1] + 4, block_start=2),
            ),
            OutlineNode(
                node_id="n3",
                title="报价",
                level=1,
                parent_id=None,
                sort_order=2,
                anchor=Anchor(char_start=positions[2], char_end=positions[2] + 2, block_start=4),
            ),
        ],
    )


def test_anchor_planner_one_chunk_per_outline_node_without_md_headings() -> None:
    content_md = (
        "1. 总则\n\n总则正文。\n\n"
        "2. 技术方案\n\n方案详情。\n\n"
        "3. 报价\n\n报价表。"
    )
    chunks = plan_chunks_from_anchors(content_md, _no_heading_outline(content_md), max_tokens=20_000)
    main_chunks = [c for c in chunks if c.title != "Preface"]
    assert len(main_chunks) == 3
    assert all(c.original_node_ids for c in main_chunks)
    assert main_chunks[0].original_node_ids == ["n1"]
    assert "方案详情" in main_chunks[1].markdown
    assert "报价表" in main_chunks[2].markdown


def test_anchor_planner_excludes_child_body_from_parent_blocks_range() -> None:
    content_md = "# 第一章\n\n父级独有。\n\n## 第一节\n\n子级内容。"
    child_start = content_md.index("## 第一节")
    tree = OutlineTree(
        strategy="content_heuristic",
        nodes=[
            OutlineNode(
                node_id="n1",
                title="第一章",
                level=1,
                parent_id=None,
                sort_order=0,
                anchor=Anchor(char_start=0, char_end=child_start),
            ),
            OutlineNode(
                node_id="n2",
                title="第一节",
                level=2,
                parent_id="n1",
                sort_order=1,
                anchor=Anchor(char_start=child_start, char_end=len(content_md)),
            ),
        ],
    )
    chunks = plan_chunks_from_anchors(content_md, tree, max_tokens=20_000)
    parent = next(c for c in chunks if c.original_node_ids == ["n1"])
    assert "父级独有" in parent.markdown
    assert "子级内容" not in parent.markdown
