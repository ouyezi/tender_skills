from __future__ import annotations

from doc_chunk.workspace.layout import OutputWorkspace

from tender_insights.common.section_slice import slice_for_llm
from tender_insights.template.models import TemplateHitLLM


def slice_template_hit(
    workspace: OutputWorkspace,
    content_md: str,
    hit: TemplateHitLLM,
) -> tuple[str, int, int] | None:
    start, end = hit.char_start, hit.char_end
    doc_len = len(content_md)
    if start < 0 or end < 0 or start >= end or end > doc_len:
        return None
    md = slice_for_llm(workspace, content_md, start, end).strip()
    return md, start, end
