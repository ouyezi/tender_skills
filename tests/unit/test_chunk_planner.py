from __future__ import annotations

from doc_chunk.chunk.planner import plan_chunks_from_outline
from doc_chunk.models.outline import Anchor, OutlineNode, OutlineTree


def _outline_tree() -> OutlineTree:
    return OutlineTree(
        strategy="heading_heuristic",
        nodes=[
            OutlineNode(
                node_id="n1",
                title="第一章",
                level=1,
                parent_id=None,
                sort_order=0,
                anchor=Anchor(block_index=0),
            ),
            OutlineNode(
                node_id="n2",
                title="第一节",
                level=2,
                parent_id="n1",
                sort_order=1,
                anchor=Anchor(block_index=1),
            ),
        ],
    )


def test_chunk_planner_keeps_preface_and_section_path() -> None:
    content_md = (
        "封面信息\n\n"
        "# 第一章\n\n"
        "第一章正文\n\n"
        "## 第一节\n\n"
        "第一节正文。"
    )

    chunks = plan_chunks_from_outline(content_md, _outline_tree(), max_tokens=20000)

    assert chunks[0].heading_level is None
    assert chunks[0].section_path == []
    sec_chunk = next(chunk for chunk in chunks if chunk.title == "第一节")
    assert sec_chunk.heading_level == 2
    assert sec_chunk.section_path == ["第一章", "第一节"]


def test_chunk_planner_splits_oversized_section_into_continuations() -> None:
    long_body = "很长内容" * 300
    content_md = "# 第一章\n\n" + long_body

    chunks = plan_chunks_from_outline(content_md, _outline_tree(), max_tokens=120)

    chapter_chunks = [chunk for chunk in chunks if chunk.title == "第一章"]
    assert len(chapter_chunks) > 1
    assert chapter_chunks[0].heading_level == 1
    assert all(chunk.section_path == ["第一章"] for chunk in chapter_chunks)
    assert all(chunk.heading_level is None for chunk in chapter_chunks[1:])
