from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from doc_chunk.llm.client import LLMClient
from doc_chunk.models.content_block import ContentBlocksFile
from doc_chunk.models.outline import OutlineTree
from doc_chunk.workspace.layout import OutputWorkspace

from tender_insights.common.anchor_backfill import backfill_char_range
from tender_insights.common.llm_extractor import extract_json_model
from tender_insights.common.output_writer import write_json_artifact
from tender_insights.common.section_router import SectionRouter, load_routing_rules
from tender_insights.common.section_slice import load_content_blocks, node_char_range, slice_for_llm
from tender_insights.config import InsightsConfig
from tender_insights.interpret.merger import dedupe_by_title
from tender_insights.interpret.models import InterpretationFile, InterpretationLLMResponse
from tender_insights.interpret.prompts import SYSTEM_PROMPT, build_user_prompt

_ROUTING_PATH = Path(__file__).with_name("routing.yaml")


def _section_path(node_id: str, outline: OutlineTree) -> list[str]:
    node_map = {n.node_id: n for n in outline.nodes}
    chain: list[str] = []
    cur = node_map.get(node_id)
    while cur:
        chain.append(cur.title)
        cur = node_map.get(cur.parent_id) if cur.parent_id else None
    return list(reversed(chain))


def _slice_node_markdown(
    workspace: OutputWorkspace,
    content_md: str,
    outline: OutlineTree,
    node_id: str,
    *,
    blocks: ContentBlocksFile | None = None,
) -> str:
    start, end = node_char_range(content_md, outline, node_id)
    return slice_for_llm(workspace, content_md, start, end, blocks=blocks)


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
    on_progress: Callable[[str, dict], None] | None = None,
) -> InterpretationFile:
    config = config or InsightsConfig.from_env()
    outline = OutlineTree.model_validate_json(workspace.outline_path.read_text(encoding="utf-8"))
    content_md = workspace.content_path.read_text(encoding="utf-8")
    blocks = load_content_blocks(workspace)
    router = SectionRouter(load_routing_rules(_ROUTING_PATH))

    route_keys = ["disqualification", "scoring", "bid_risk", "directory"]
    target_node_ids: set[str] = set()
    for key in route_keys:
        for node in router.match_nodes(outline, key):
            target_node_ids.add(node.node_id)

    aggregated = InterpretationLLMResponse()
    sorted_ids = sorted(target_node_ids)
    total_nodes = len(sorted_ids)
    if on_progress:
        on_progress(
            "interpret",
            {
                "message": f"开始解读，共 {total_nodes} 个章节待分析",
                "current": 0,
                "total": max(total_nodes, 1),
            },
        )
    for index, node_id in enumerate(sorted_ids, start=1):
        node = next(n for n in outline.nodes if n.node_id == node_id)
        if on_progress:
            on_progress(
                "interpret",
                {
                    "message": f"解读章节 ({index}/{total_nodes})",
                    "detail": node.title,
                    "current": index,
                    "total": max(total_nodes, 1),
                    "node_id": node_id,
                },
            )
        md = _slice_node_markdown(workspace, content_md, outline, node_id, blocks=blocks)
        path = _section_path(node_id, outline)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(node.title, path, md)},
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
    _apply_anchors(dq, content_md)
    _apply_anchors(sc, content_md)
    _apply_anchors(br, content_md)
    _apply_anchors(dr, content_md)

    result = InterpretationFile(
        source_workspace=str(workspace.root),
        disqualification_items=dq,
        scoring_items=sc,
        bid_risk_items=br,
        directory_requirements=dr,
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
                "current": total_nodes,
                "total": max(total_nodes, 1),
            },
        )
    return result
