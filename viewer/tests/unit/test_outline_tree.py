from __future__ import annotations

from doc_chunk.models.outline import Anchor, OutlineNode, OutlineTree

from viewer.services.outline_tree import build_outline_response


def test_build_outline_response_nests_by_parent_id() -> None:
    tree = OutlineTree(
        strategy="toc",
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
                title="Section 1.1",
                level=2,
                parent_id="n1",
                sort_order=1,
                anchor=Anchor(char_start=50),
            ),
        ],
    )
    response = build_outline_response(tree, content_md="# Chapter 1\n\nbody\n\n## Section 1.1\n\ntext")

    assert response.strategy == "toc"
    assert len(response.nodes) == 1
    assert response.nodes[0].node_id == "n1"
    assert response.nodes[0].children[0].node_id == "n2"


def test_build_outline_response_adds_preface_node() -> None:
    tree = OutlineTree(
        strategy="heading_heuristic",
        nodes=[
            OutlineNode(
                node_id="n1",
                title="Chapter 1",
                level=1,
                parent_id=None,
                sort_order=0,
                anchor=Anchor(char_start=20),
            ),
        ],
    )
    response = build_outline_response(tree, content_md="Preface text\n\n# Chapter 1\n\nbody")

    assert response.nodes[0].node_id == "__preface__"
    assert response.nodes[0].title == "前言"
    assert response.nodes[1].node_id == "n1"
