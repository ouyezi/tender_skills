from __future__ import annotations

from pathlib import Path

import fitz

from doc_chunk.models.outline import Anchor, OutlineNode, OutlineTree


def extract_pdf_bookmark_outline(source_path: Path) -> OutlineTree | None:
    try:
        document = fitz.open(source_path)
    except Exception:
        return None

    try:
        toc = document.get_toc(simple=True)
    finally:
        document.close()

    if not toc:
        return None

    nodes: list[OutlineNode] = []
    last_seen_by_level: dict[int, str] = {}
    for idx, row in enumerate(toc):
        if len(row) < 3:
            continue
        level, title, page = row[0], str(row[1]).strip(), int(row[2] or 0)
        if not title:
            continue
        safe_level = max(1, min(8, level))
        parent_id = None
        if safe_level > 1:
            for parent_level in range(safe_level - 1, 0, -1):
                parent_id = last_seen_by_level.get(parent_level)
                if parent_id:
                    break
        node_id = f"n{len(nodes) + 1}"
        nodes.append(
            OutlineNode(
                node_id=node_id,
                title=title,
                level=safe_level,
                parent_id=parent_id,
                sort_order=idx,
                anchor=Anchor(page=page if page > 0 else None),
            )
        )
        last_seen_by_level[safe_level] = node_id
        for stale_level in list(last_seen_by_level):
            if stale_level > safe_level:
                last_seen_by_level.pop(stale_level, None)

    if not nodes:
        return None
    return OutlineTree(strategy="toc", nodes=nodes)
