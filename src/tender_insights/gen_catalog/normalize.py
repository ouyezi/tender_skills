from __future__ import annotations

import re

from tender_insights.gen_catalog.models import BidOutlineNode

_BID_ID = re.compile(r"^bid-\d{3}$")


def normalize_outline_ids(root: BidOutlineNode) -> BidOutlineNode:
    """Ensure non-root nodes use unique ``bid-NNN`` ids (never reuse ``dir-*`` from interpret)."""
    used: set[str] = {"bid-root"}
    counter = 0

    def walk(node: BidOutlineNode) -> None:
        nonlocal counter
        if node.id != "bid-root":
            if _BID_ID.fullmatch(node.id) and node.id not in used:
                used.add(node.id)
            else:
                while True:
                    counter += 1
                    candidate = f"bid-{counter:03d}"
                    if candidate not in used:
                        node.id = candidate
                        used.add(candidate)
                        break
        for child in node.children:
            walk(child)

    for child in root.children:
        walk(child)
    return root
