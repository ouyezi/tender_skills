from doc_chunk.models.outline import Anchor, OutlineNode, OutlineTree

from viewer.services.asset_navigation import resolve_outline_node_for_char
from viewer.services.outline_tree import PREFACE_NODE_ID
from viewer.services.section_slice import build_section_char_ranges, slice_section


def test_resolve_preface_char() -> None:
    content_md = "Preface text\n\n# Chapter 1\n\nBody"
    tree = OutlineTree(
        nodes=[
            OutlineNode(
                node_id="n1",
                title="Chapter 1",
                level=1,
                parent_id=None,
                sort_order=0,
                anchor=Anchor(char_start=content_md.index("Body")),
            )
        ]
    )
    assert resolve_outline_node_for_char(5, content_md, tree) == PREFACE_NODE_ID


def test_resolve_chapter_char() -> None:
    content_md = "Preface\n\n# Chapter 1\n\nAlpha\n\n# Chapter 2\n\nBeta"
    tree = OutlineTree(
        nodes=[
            OutlineNode(
                node_id="n1",
                title="Chapter 1",
                level=1,
                parent_id=None,
                sort_order=0,
                anchor=Anchor(char_start=0),
            ),
            OutlineNode(
                node_id="n2",
                title="Chapter 2",
                level=1,
                parent_id=None,
                sort_order=1,
                anchor=Anchor(char_start=0),
            ),
        ]
    )
    pos = content_md.index("Alpha")
    assert resolve_outline_node_for_char(pos, content_md, tree) == "n1"


def test_build_section_char_ranges_matches_slice_section() -> None:
    content_md = "Preface\n\n# Chapter 1\n\nAlpha\n\n# Chapter 2\n\nBeta"
    tree = OutlineTree(
        nodes=[
            OutlineNode(
                node_id="n1",
                title="Chapter 1",
                level=1,
                parent_id=None,
                sort_order=0,
                anchor=Anchor(char_start=0),
            ),
            OutlineNode(
                node_id="n2",
                title="Chapter 2",
                level=1,
                parent_id=None,
                sort_order=1,
                anchor=Anchor(char_start=0),
            ),
        ]
    )
    ranges = build_section_char_ranges(content_md, tree)
    preface = slice_section(content_md, tree, PREFACE_NODE_ID)
    assert ranges[0].node_id == PREFACE_NODE_ID
    assert ranges[0].char_start == preface.char_start
    assert ranges[0].char_end == preface.char_end
    for section in ranges[1:]:
        sliced = slice_section(content_md, tree, section.node_id)
        assert section.char_start == sliced.char_start
        assert section.char_end == sliced.char_end
