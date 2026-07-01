from __future__ import annotations

from doc_chunk.models.outline import Anchor, OutlineNode, OutlineTree
from doc_chunk.outline.continuity import normalize_outline_cn_continuity


def test_normalize_outline_cn_continuity_nests_local_enum_under_numeric_section() -> None:
    content_md = "\n".join(
        [
            "#### 2.2.5.2 员工保险",
            "",
            "一、员工投诉反馈机制：",
            "",
            "二、医疗险索赔流程：",
            "",
            "# 三、索赔及服务问答",
        ]
    )
    tree = OutlineTree(
        strategy="heading_heuristic",
        nodes=[
            OutlineNode(
                node_id="n1",
                title="2.2.5.2员工保险",
                level=4,
                parent_id="n0",
                sort_order=0,
                anchor=Anchor(block_index=0),
            ),
            OutlineNode(
                node_id="n3",
                title="三、索赔及服务问答",
                level=1,
                parent_id=None,
                sort_order=1,
                anchor=Anchor(block_index=6),
            ),
        ],
    )
    normalized = normalize_outline_cn_continuity(tree, content_md=content_md)
    by_title = {node.title: node for node in normalized.nodes}
    assert by_title["三、索赔及服务问答"].level == 5
    assert by_title["三、索赔及服务问答"].parent_id == "n1"


def test_normalize_outline_cn_continuity_keeps_major_chapters() -> None:
    content_md = "\n".join(
        [
            "# 一、企业简介及资质",
            "",
            "#### 1.6 企业荣誉",
            "",
            "# 二、百福得服务方案介绍",
        ]
    )
    tree = OutlineTree(
        strategy="heading_heuristic",
        nodes=[
            OutlineNode(
                node_id="n1",
                title="一、企业简介及资质",
                level=1,
                parent_id=None,
                sort_order=0,
                anchor=Anchor(block_index=0),
            ),
            OutlineNode(
                node_id="n2",
                title="1.6企业荣誉",
                level=4,
                parent_id="n1",
                sort_order=1,
                anchor=Anchor(block_index=2),
            ),
            OutlineNode(
                node_id="n3",
                title="二、百福得服务方案介绍",
                level=1,
                parent_id=None,
                sort_order=2,
                anchor=Anchor(block_index=4),
            ),
        ],
    )
    normalized = normalize_outline_cn_continuity(tree, content_md=content_md)
    by_title = {node.title: node for node in normalized.nodes}
    assert by_title["二、百福得服务方案介绍"].level == 1
    assert by_title["二、百福得服务方案介绍"].parent_id is None
