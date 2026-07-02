from __future__ import annotations

import pytest

from doc_chunk.locate.heading_starts import (
    build_node_heading_starts,
    ensure_section_prefix_spacing,
    fallback_char_start,
    normalize_outline_title,
    parse_body_headings,
    section_char_range,
)
from doc_chunk.models.outline import Anchor, OutlineNode, OutlineTree

TOC_BID_CONTENT_MD = (
    "2025年生日福利预算\n\n投标/响应文件\n\n"
    "# 投标函\t1\n"
    "# 合同条款偏离表\t12\n"
    "## 服务偏离表\t3\n"
    "# 服务偏离表\n\n"
    "服务偏离概述\n\n"
    "### 2.1合同条款偏离表\n\n"
    "| 序号 | 条款 |\n|---|---|\n| 1 | foo |\n\n"
    "### 2.2技术条款偏离表\n\n"
    "技术偏离正文\n"
)


def _toc_bid_tree() -> OutlineTree:
    return OutlineTree(
        strategy="toc",
        nodes=[
            OutlineNode(
                node_id="n1",
                title="服务偏离表3",
                level=1,
                parent_id=None,
                sort_order=0,
                anchor=Anchor(block_index=0),
            ),
            OutlineNode(
                node_id="n2",
                title="2.1合同条款偏离表12",
                level=3,
                parent_id="n1",
                sort_order=1,
                anchor=Anchor(block_index=1),
            ),
            OutlineNode(
                node_id="n3",
                title="2.2技术条款偏离表",
                level=3,
                parent_id="n1",
                sort_order=2,
                anchor=Anchor(block_index=2),
            ),
        ],
    )


def test_parse_body_headings_skips_toc_entries() -> None:
    headings = parse_body_headings(TOC_BID_CONTENT_MD)
    titles = [h.title for h in headings]
    assert "投标函\t1" not in titles
    assert "合同条款偏离表\t12" not in titles
    assert "2.1合同条款偏离表" in titles


def test_normalize_outline_title_strips_glue_page_and_prefix() -> None:
    assert normalize_outline_title("2.1合同条款偏离表12") == normalize_outline_title("2.1 合同条款偏离表")
    assert normalize_outline_title("1投标函11") == normalize_outline_title("投标函")
    assert normalize_outline_title("2.1合同条款偏离表（模板）") == normalize_outline_title(
        "合同条款偏离表（模板）"
    )


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("2.1合同条款偏离表", "2.1 合同条款偏离表"),
        ("2.1 合同条款偏离表", "2.1 合同条款偏离表"),
        ("1投标函", "1 投标函"),
        ("一、投标函", "一、 投标函"),
        ("一、 投标函", "一、 投标函"),
        ("评分索引表", "评分索引表"),
    ],
)
def test_ensure_section_prefix_spacing(title: str, expected: str) -> None:
    assert ensure_section_prefix_spacing(title) == expected


def test_build_node_heading_starts_skips_toc_for_section_2_1() -> None:
    tree = _toc_bid_tree()
    starts = build_node_heading_starts(tree, TOC_BID_CONTENT_MD, use_existing_anchor_fallback=False)
    body_headings = parse_body_headings(TOC_BID_CONTENT_MD)
    first_body = min(h.char_start for h in body_headings)
    assert starts["n2"] >= first_body
    assert "2.1合同条款偏离表" in TOC_BID_CONTENT_MD[starts["n2"] : starts["n2"] + 40]


def test_section_char_range_parent_includes_child_body() -> None:
    tree = _toc_bid_tree()
    start, end = section_char_range(tree, TOC_BID_CONTENT_MD, "n1")
    section_md = TOC_BID_CONTENT_MD[start:end]
    assert "2.1合同条款偏离表" in section_md


def test_fallback_char_start_finds_first_body_match() -> None:
    pos = fallback_char_start(TOC_BID_CONTENT_MD, "2.1合同条款偏离表12", level=3)
    assert pos is not None
    assert TOC_BID_CONTENT_MD[pos : pos + 20].startswith("### 2.1")


def test_build_node_heading_starts_matches_slice_section() -> None:
    from viewer.services.section_slice import slice_section

    tree = _toc_bid_tree()
    starts = build_node_heading_starts(tree, TOC_BID_CONTENT_MD)
    for node in tree.nodes:
        section = slice_section(TOC_BID_CONTENT_MD, tree, node.node_id)
        assert starts.get(node.node_id) == section.char_start, node.node_id
