from __future__ import annotations

from doc_chunk.models.outline import OutlineTree

from viewer.models import OutlineTreeNode, OutlineTreeResponse

PREFACE_NODE_ID = "__preface__"


def _sorted_nodes(tree: OutlineTree) -> list:
    return sorted(tree.nodes, key=lambda n: (n.sort_order, n.node_id))


def _build_section_path(node, node_map: dict) -> list[str]:
    chain: list[str] = []
    cursor = node
    seen: set[str] = set()
    while cursor and cursor.node_id not in seen:
        seen.add(cursor.node_id)
        chain.append(cursor.title)
        cursor = node_map.get(cursor.parent_id) if cursor.parent_id else None
    return list(reversed(chain))


def _first_anchor_start(tree: OutlineTree) -> int | None:
    starts = [n.anchor.char_start for n in tree.nodes if n.anchor.char_start is not None]
    return min(starts) if starts else None


def build_outline_response(tree: OutlineTree, content_md: str) -> OutlineTreeResponse:
    node_map = {n.node_id: n for n in tree.nodes}
    children_by_parent: dict[str | None, list] = {}
    for node in _sorted_nodes(tree):
        children_by_parent.setdefault(node.parent_id, []).append(node)

    def to_node(raw) -> OutlineTreeNode:
        return OutlineTreeNode(
            node_id=raw.node_id,
            title=raw.title,
            level=raw.level,
            needs_review=raw.needs_review,
            children=[to_node(child) for child in children_by_parent.get(raw.node_id, [])],
        )

    roots = [to_node(node) for node in children_by_parent.get(None, [])]
    nodes: list[OutlineTreeNode] = []

    first_start = _first_anchor_start(tree)
    if first_start and first_start > 0 and content_md[:first_start].strip():
        nodes.append(
            OutlineTreeNode(
                node_id=PREFACE_NODE_ID,
                title="前言",
                level=0,
                needs_review=False,
                children=[],
            )
        )
    nodes.extend(roots)
    return OutlineTreeResponse(strategy=tree.strategy, nodes=nodes)
