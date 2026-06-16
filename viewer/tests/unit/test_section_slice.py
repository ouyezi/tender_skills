from __future__ import annotations

from doc_chunk.models.outline import Anchor, OutlineNode, OutlineTree

from viewer.services.outline_tree import PREFACE_NODE_ID
from viewer.services.section_slice import slice_section


def test_slice_section_uses_char_anchors() -> None:
    content_md = "Preface\n\n# Chapter 1\n\nAlpha\n\n## Section 1.1\n\nBeta\n\n# Chapter 2\n\nGamma"
    tree = OutlineTree(
        nodes=[
            OutlineNode(
                node_id="n1",
                title="Chapter 1",
                level=1,
                parent_id=None,
                sort_order=0,
                anchor=Anchor(char_start=content_md.index("# Chapter 1")),
            ),
            OutlineNode(
                node_id="n2",
                title="Section 1.1",
                level=2,
                parent_id="n1",
                sort_order=1,
                anchor=Anchor(char_start=content_md.index("## Section 1.1")),
            ),
        ]
    )

    preface = slice_section(content_md, tree, PREFACE_NODE_ID)
    assert preface.title == "前言"
    assert "Preface" in preface.markdown

    section = slice_section(content_md, tree, "n2")
    assert section.title == "Section 1.1"
    assert "Beta" in section.markdown
    assert "Gamma" not in section.markdown
    assert section.section_path == ["Chapter 1", "Section 1.1"]
