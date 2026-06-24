from __future__ import annotations

from tender_insights.interpret.models import (
    DirectoryOutline,
    DirectoryOutlineNode,
    DirectoryRequirement,
    DirectoryStructureNode,
)


def _flatten_structure(
    nodes: list[DirectoryStructureNode],
    *,
    level: int,
    order_counter: list[int],
    output: list[DirectoryOutlineNode],
) -> None:
    for node in nodes:
        output.append(
            DirectoryOutlineNode(
                id=f"dir-{order_counter[0]:03d}",
                title=node.title,
                level=level,
                order=order_counter[0],
                mandatory=node.mandatory,
                number=node.number,
            )
        )
        order_counter[0] += 1
        if node.children:
            _flatten_structure(node.children, level=level + 1, order_counter=order_counter, output=output)


def build_directory_outline(
    directory_requirements: list[DirectoryRequirement],
) -> DirectoryOutline:
    explicit = [r for r in directory_requirements if not r.inferred and r.structure]
    inferred = [r for r in directory_requirements if r.inferred and r.structure]
    sources = explicit or inferred or directory_requirements

    nodes: list[DirectoryOutlineNode] = []
    order_counter = [1]
    has_explicit = bool(explicit)
    has_inferred = bool(inferred) and not explicit

    for req in sources:
        if req.structure:
            _flatten_structure(req.structure, level=1, order_counter=order_counter, output=nodes)
        else:
            for title in req.required_sections:
                nodes.append(
                    DirectoryOutlineNode(
                        id=f"dir-{order_counter[0]:03d}",
                        title=title,
                        level=1,
                        order=order_counter[0],
                        mandatory=req.mandatory,
                    )
                )
                order_counter[0] += 1

    if has_explicit:
        confidence = 0.85
    elif has_inferred:
        confidence = 0.55
    elif nodes:
        confidence = 0.6
    else:
        confidence = 0.0
    return DirectoryOutline(confidence=confidence, nodes=nodes)
