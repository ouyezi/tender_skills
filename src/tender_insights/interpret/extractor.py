from __future__ import annotations

from collections.abc import Callable

from agent_platform.client import AgentClient
from agent_platform.factory import create_agent_client_from_env
from doc_chunk.llm.client import LLMClient
from doc_chunk.models.outline import OutlineTree
from doc_chunk.workspace.layout import OutputWorkspace

from tender_insights.common.agent_extractor import extract_json_via_agent
from tender_insights.common.anchor_backfill import backfill_char_range
from tender_insights.common.content_source import prepare_interpret_source
from tender_insights.common.output_writer import write_json_artifact
from tender_insights.common.segment_planner import plan_segments
from tender_insights.config import InsightsConfig
from tender_insights.interpret.directory_outline import build_directory_outline
from tender_insights.interpret.llm_logging import log_llm_prompt
from tender_insights.interpret.merger import (
    dedupe_by_title,
    merge_scoring_items,
    normalize_directory_requirements,
)
from tender_insights.interpret.models import InterpretationFile, InterpretationLLMResponse
from tender_insights.interpret.overview import build_overview
from tender_insights.interpret.prompts import SYSTEM_PROMPT, build_segment_prompt
from tender_insights.interpret.response_normalize import normalize_interpretation_llm_data


def _apply_anchors(items: list, content_md: str) -> None:
    """为提取项回填原文锚点。"""
    for item in items:
        start, end = backfill_char_range(content_md, item.source_excerpt)
        item.char_start = start
        item.char_end = end


def _section_path_string(section_path: list[str]) -> str:
    """将章节路径列表格式化为 agent 合同中的字符串。"""
    return " > ".join(section_path) if section_path else "(root)"


def _segment_call_type(segment_id: str) -> str:
    """按分段 id 选择 interpret call_type。"""
    if segment_id.startswith("seg-scoring-"):
        return "interpret_scoring_table"
    return "interpret_segment"


def interpret_workspace(
    workspace: OutputWorkspace,
    client: LLMClient | AgentClient,
    *,
    config: InsightsConfig | None = None,
    on_progress: Callable[[str, dict], None] | None = None,
    agent_client: AgentClient | None = None,
) -> InterpretationFile:
    """对工作区执行分段解读并写入 interpretation.json。"""
    config = config or InsightsConfig.from_env()
    resolved = agent_client
    if resolved is None:
        if isinstance(client, AgentClient):
            resolved = client
        else:
            resolved = create_agent_client_from_env(llm_client=client)

    outline = OutlineTree.model_validate_json(workspace.outline_path.read_text(encoding="utf-8"))

    source = prepare_interpret_source(workspace, config=config)
    segments = plan_segments(workspace, source, outline, config=config)
    total_segments = len(segments)

    if on_progress:
        on_progress(
            "interpret",
            {
                "message": f"开始解读，共 {total_segments} 个分段待分析",
                "current": 0,
                "total": max(total_segments, 1),
            },
        )

    aggregated = InterpretationLLMResponse()
    for index, seg in enumerate(segments, start=1):
        title = seg.section_path[-1] if seg.section_path else seg.segment_id
        if on_progress:
            on_progress(
                "interpret",
                {
                    "message": f"解读分段 ({index}/{total_segments})",
                    "detail": title,
                    "current": index,
                    "total": max(total_segments, 1),
                    "node_id": seg.segment_id,
                },
            )
        call_type = _segment_call_type(seg.segment_id)
        section_path_str = _section_path_string(seg.section_path)
        agent_input: dict = {
            "segment_id": seg.segment_id,
            "section_path": section_path_str,
            "markdown": seg.markdown,
        }
        if call_type == "interpret_segment" and config.segment_keyword_match_enabled:
            agent_input["keyword_match_enabled"] = True

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": build_segment_prompt(
                    seg.segment_id,
                    seg.section_path,
                    seg.markdown,
                    keyword_match_enabled=(
                        True
                        if call_type == "interpret_scoring_table"
                        else config.segment_keyword_match_enabled
                    ),
                ),
            },
        ]
        log_llm_prompt(
            call_type=call_type,
            messages=messages,
            workspace=str(workspace.root),
            segment_id=seg.segment_id,
            section_path=seg.section_path,
            token_estimate=seg.token_estimate,
        )
        batch = extract_json_via_agent(
            resolved,
            call_type,
            agent_input,
            InterpretationLLMResponse,
            max_retries=config.max_retries,
            normalize=lambda data, path=seg.section_path: normalize_interpretation_llm_data(
                data,
                section_path=path,
            ),
            log_context={"call_type": call_type, "segment_id": seg.segment_id},
        )
        aggregated.disqualification_items.extend(batch.disqualification_items)
        aggregated.scoring_items.extend(batch.scoring_items)
        aggregated.bid_risk_items.extend(batch.bid_risk_items)
        aggregated.directory_requirements.extend(batch.directory_requirements)

    dq = dedupe_by_title(aggregated.disqualification_items)
    sc = merge_scoring_items(aggregated.scoring_items)
    br = dedupe_by_title(aggregated.bid_risk_items)
    dr = normalize_directory_requirements(aggregated.directory_requirements)

    anchor_md = source.markdown
    _apply_anchors(dq, anchor_md)
    _apply_anchors(sc, anchor_md)
    _apply_anchors(br, anchor_md)
    _apply_anchors(dr, anchor_md)

    if on_progress:
        on_progress(
            "interpret",
            {
                "message": "正在生成概要…",
                "detail": "",
                "current": total_segments,
                "total": max(total_segments, 1),
            },
        )
    overview = build_overview(
        resolved,
        dq=dq,
        sc=sc,
        br=br,
        dr=dr,
        max_retries=config.max_retries,
        workspace=str(workspace.root),
        agent_client=resolved,
    )
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
    if on_progress:
        on_progress(
            "interpret",
            {
                "message": "解读完成，正在写入结果",
                "current": total_segments,
                "total": max(total_segments, 1),
            },
        )
    return result
