from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from doc_chunk.models.content_block import ContentBlocksFile
from doc_chunk.workspace.layout import OutputWorkspace

from tender_insights.common.ocr.enricher import enrich_content_with_ocr
from tender_insights.common.section_slice import load_content_blocks
from tender_insights.config import InsightsConfig


@dataclass(frozen=True, slots=True)
class InterpretSource:
    markdown: str
    source_path: Path
    blocks: ContentBlocksFile | None
    ocr_image_count: int


def prepare_interpret_source(
    workspace: OutputWorkspace,
    *,
    config: InsightsConfig,
    ocr_enabled: bool | None = None,
) -> InterpretSource:
    content_md = workspace.content_path.read_text(encoding="utf-8")
    blocks = load_content_blocks(workspace)
    interpret_dir = workspace.root / "interpret"
    interpret_dir.mkdir(parents=True, exist_ok=True)
    source_path = interpret_dir / "source_content.md"

    use_ocr = config.ocr_enabled if ocr_enabled is None else ocr_enabled
    if use_ocr:
        enriched, _, ocr_count = enrich_content_with_ocr(workspace, content_md, config=config)
    else:
        enriched = content_md
        ocr_count = 0

    source_path.write_text(enriched, encoding="utf-8")
    return InterpretSource(
        markdown=enriched,
        source_path=source_path,
        blocks=blocks,
        ocr_image_count=ocr_count,
    )
