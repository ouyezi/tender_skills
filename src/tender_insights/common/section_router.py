from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from doc_chunk.models.outline import OutlineNode, OutlineTree


def load_routing_rules(path: Path) -> dict[str, dict[str, list[str]]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data


class SectionRouter:
    def __init__(self, rules: dict[str, dict[str, list[str]]]) -> None:
        self._rules = rules

    def match_nodes(self, outline: OutlineTree, route_key: str) -> list[OutlineNode]:
        keywords = self._rules.get(route_key, {}).get("keywords", [])
        if not keywords:
            return []
        matched: list[OutlineNode] = []
        for node in outline.nodes:
            title = node.title
            if any(kw in title for kw in keywords):
                matched.append(node)
        return sorted(matched, key=lambda n: n.sort_order)
