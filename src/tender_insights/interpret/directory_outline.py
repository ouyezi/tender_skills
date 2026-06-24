from __future__ import annotations

from tender_insights.interpret.models import DirectoryOutline, DirectoryOutlineNode, DirectoryRequirement


def build_directory_outline(
    directory_requirements: list[DirectoryRequirement],
) -> DirectoryOutline:
    nodes: list[DirectoryOutlineNode] = []
    order = 1
    has_structure = False
    for req in directory_requirements:
        if req.structure:
            has_structure = True
            for item in req.structure:
                nodes.append(
                    DirectoryOutlineNode(
                        id=f"dir-{order:03d}",
                        title=item.title,
                        level=1,
                        order=order,
                        mandatory=item.mandatory,
                        number=item.number,
                    )
                )
                order += 1
        else:
            for title in req.required_sections:
                nodes.append(
                    DirectoryOutlineNode(
                        id=f"dir-{order:03d}",
                        title=title,
                        level=1,
                        order=order,
                        mandatory=req.mandatory,
                    )
                )
                order += 1
    confidence = 0.85 if has_structure else (0.6 if nodes else 0.0)
    return DirectoryOutline(confidence=confidence, nodes=nodes)
