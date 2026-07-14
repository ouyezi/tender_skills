from __future__ import annotations

from doc_chunk.locate.heading_starts import (
    build_node_heading_starts,
    infer_body_start,
    parse_body_headings,
)
from doc_chunk.models.outline import Anchor, OutlineNode, OutlineTree

GLUED_TOC_MD = (
    "封面\n\n"
    "# 目录\n\n"
    "一、服务方案1\n"
    "（一）服务大纲1\n"
    "1.全场景福利平台1\n\n"
    "# 一、服务方案\n\n"
    "正文A\n\n"
    "## （一）服务大纲\n\n"
    "正文B\n"
)


def test_infer_body_start_skips_glued_toc_cluster() -> None:
    start = infer_body_start(GLUED_TOC_MD)
    assert start == GLUED_TOC_MD.index("# 一、服务方案\n")


def test_build_node_heading_starts_uses_body_not_toc() -> None:
    tree = OutlineTree(
        strategy="toc",
        nodes=[
            OutlineNode(
                node_id="n1",
                title="一、服务方案",
                level=1,
                parent_id=None,
                sort_order=0,
                anchor=Anchor(),
            ),
            OutlineNode(
                node_id="n2",
                title="（一）服务大纲",
                level=2,
                parent_id="n1",
                sort_order=1,
                anchor=Anchor(),
            ),
        ],
    )
    starts = build_node_heading_starts(tree, GLUED_TOC_MD, use_existing_anchor_fallback=False)
    assert starts["n1"] == GLUED_TOC_MD.index("# 一、服务方案\n")
    assert starts["n2"] == GLUED_TOC_MD.index("## （一）服务大纲\n")
    assert starts["n1"] >= infer_body_start(GLUED_TOC_MD)
