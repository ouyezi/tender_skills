from __future__ import annotations

from dataclasses import dataclass

from doc_chunk.models.outline import OutlineTree

_KEYWORDS = ["附件", "承诺书", "授权", "声明", "委托"]


@dataclass(frozen=True, slots=True)
class TemplateHit:
    node_id: str
    title: str


def detect_template_nodes(outline: OutlineTree) -> list[TemplateHit]:
    hits: list[TemplateHit] = []
    for node in outline.nodes:
        if any(kw in node.title for kw in _KEYWORDS):
            hits.append(TemplateHit(node_id=node.node_id, title=node.title))
    return hits
