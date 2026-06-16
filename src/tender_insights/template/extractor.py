from __future__ import annotations

from doc_chunk.llm.client import LLMClient
from doc_chunk.models.outline import OutlineTree
from doc_chunk.workspace.layout import OutputWorkspace

from tender_insights.common.output_writer import write_json_artifact
from tender_insights.template.boundary import slice_by_heading_level
from tender_insights.template.classifier import classify_template
from tender_insights.template.detector import detect_template_nodes
from tender_insights.template.models import TemplateEntry, TemplatesIndexFile


def _section_path(node_id: str, outline: OutlineTree) -> list[str]:
    node_map = {n.node_id: n for n in outline.nodes}
    chain: list[str] = []
    cur = node_map.get(node_id)
    while cur:
        chain.append(cur.title)
        cur = node_map.get(cur.parent_id) if cur.parent_id else None
    return list(reversed(chain))


def _slice_node_markdown(content_md: str, outline: OutlineTree, node_id: str) -> tuple[str, int, int]:
    node = next(n for n in outline.nodes if n.node_id == node_id)
    start = node.anchor.char_start if node.anchor and node.anchor.char_start is not None else 0
    siblings = sorted(
        [n for n in outline.nodes if n.level == node.level and (n.anchor.char_start or 0) > start],
        key=lambda n: n.anchor.char_start or 10**9,
    )
    end = siblings[0].anchor.char_start if siblings and siblings[0].anchor else len(content_md)
    md, end = slice_by_heading_level(content_md, start, node.level)
    if not md:
        md = content_md[start:end].strip()
    return md, start, end


def extract_templates_workspace(
    workspace: OutputWorkspace,
    client: LLMClient,
) -> TemplatesIndexFile:
    del client  # rule-based classifier; client reserved for future LLM fallback
    outline = OutlineTree.model_validate_json(workspace.outline_path.read_text(encoding="utf-8"))
    content_md = workspace.content_path.read_text(encoding="utf-8")

    templates_dir = workspace.root / "templates"
    templates_dir.mkdir(parents=True, exist_ok=True)

    type_counters: dict[str, int] = {}
    entries: list[TemplateEntry] = []

    for idx, hit in enumerate(detect_template_nodes(outline), start=1):
        md, char_start, char_end = _slice_node_markdown(content_md, outline, hit.node_id)
        tpl_type, type_label, confidence = classify_template(hit.title, md)

        type_counters[tpl_type] = type_counters.get(tpl_type, 0) + 1
        filename = f"{tpl_type}-{type_counters[tpl_type]:03d}.md"
        rel_path = f"templates/{filename}"
        (templates_dir / filename).write_text(md, encoding="utf-8")

        entries.append(
            TemplateEntry(
                id=f"tpl-{idx:03d}",
                type=tpl_type,
                type_label=type_label,
                title=hit.title,
                section_path=_section_path(hit.node_id, outline),
                file=rel_path,
                char_start=char_start,
                char_end=char_end,
                confidence=confidence,
            )
        )

    result = TemplatesIndexFile(templates=entries)
    write_json_artifact(
        workspace,
        "templates/index.json",
        result.model_dump(mode="json"),
        stage_name="template",
        output_key="templates",
    )
    return result
