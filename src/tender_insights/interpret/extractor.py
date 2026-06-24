from __future__ import annotations

from doc_chunk.llm.client import LLMClient
from doc_chunk.models.outline import OutlineTree
from doc_chunk.workspace.layout import OutputWorkspace

from tender_insights.common.anchor_backfill import backfill_char_range
from tender_insights.common.content_source import prepare_interpret_source
from tender_insights.common.llm_extractor import extract_json_model
from tender_insights.common.output_writer import write_json_artifact
from tender_insights.common.segment_planner import plan_segments
from tender_insights.config import InsightsConfig
from tender_insights.interpret.directory_outline import build_directory_outline
from tender_insights.interpret.merger import dedupe_by_title
from tender_insights.interpret.models import InterpretationFile, InterpretationLLMResponse
from tender_insights.interpret.overview import build_overview
from tender_insights.interpret.prompts import SYSTEM_PROMPT, build_segment_prompt


def _apply_anchors(items: list, content_md: str) -> None:
    for item in items:
        start, end = backfill_char_range(content_md, item.source_excerpt)
        item.char_start = start
        item.char_end = end


def interpret_workspace(
    workspace: OutputWorkspace,
    client: LLMClient,
    *,
    config: InsightsConfig | None = None,
) -> InterpretationFile:
    config = config or InsightsConfig.from_env()
    outline = OutlineTree.model_validate_json(workspace.outline_path.read_text(encoding="utf-8"))

    source = prepare_interpret_source(workspace, config=config)
    segments = plan_segments(workspace, source, outline, config=config)

    aggregated = InterpretationLLMResponse()
    for seg in segments:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_segment_prompt(seg.segment_id, seg.section_path, seg.markdown)},
        ]
        batch = extract_json_model(client, messages, InterpretationLLMResponse, max_retries=config.max_retries)
        aggregated.disqualification_items.extend(batch.disqualification_items)
        aggregated.scoring_items.extend(batch.scoring_items)
        aggregated.bid_risk_items.extend(batch.bid_risk_items)
        aggregated.directory_requirements.extend(batch.directory_requirements)

    dq = dedupe_by_title(aggregated.disqualification_items)
    sc = dedupe_by_title(aggregated.scoring_items)
    br = dedupe_by_title(aggregated.bid_risk_items)
    dr = dedupe_by_title(aggregated.directory_requirements)

    anchor_md = source.markdown
    _apply_anchors(dq, anchor_md)
    _apply_anchors(sc, anchor_md)
    _apply_anchors(br, anchor_md)
    _apply_anchors(dr, anchor_md)

    overview = build_overview(client, dq=dq, sc=sc, br=br, dr=dr, max_retries=config.max_retries)
    directory_outline = build_directory_outline(dr)

    result = InterpretationFile(
        source_workspace=str(workspace.root),
        overview=overview,
        disqualification_items=dq,
        scoring_items=sc,
        bid_risk_items=br,
        directory_requirements=dr,
        directory_outline=directory_outline,
        segment_count=len(segments),
        ocr_image_count=source.ocr_image_count,
    )
    write_json_artifact(
        workspace,
        "interpretation.json",
        result.model_dump(mode="json"),
        stage_name="interpret",
        output_key="interpretation",
    )
    return result
