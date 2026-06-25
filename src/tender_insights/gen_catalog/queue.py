from __future__ import annotations

from tender_insights.gen_catalog.models import BidOutlineNode


def build_node_queue(root: BidOutlineNode) -> list[str]:
    queue: list[str] = []

    def walk(node: BidOutlineNode) -> None:
        if node.id != "bid-root":
            queue.append(node.id)
        for child in node.children:
            walk(child)

    for child in root.children:
        walk(child)
    return queue


def find_node(root: BidOutlineNode, node_id: str) -> BidOutlineNode | None:
    if root.id == node_id:
        return root

    for child in root.children:
        found = find_node(child, node_id)
        if found is not None:
            return found
    return None


def next_pending_node_id(queue: list[str], completed_steps: list[str]) -> str | None:
    done = set(completed_steps)
    for node_id in queue:
        if node_id not in done:
            return node_id
    return None


def compute_step_total(root: BidOutlineNode) -> int:
    return 1 + len(build_node_queue(root))
