from __future__ import annotations

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
from tender_insights.legal.models import LegalReviewFile, LegalReviewLLMResponse
from tender_insights.legal.prompts import SYSTEM_PROMPT, build_user_prompt

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


def _apply_risk_anchors(items: list, content_md: str) -> None:
    for item in items:
        start, end = backfill_char_range(content_md, item.clause_excerpt)
        item.char_start = start
        item.char_end = end


def _apply_pending_anchors(items: list, content_md: str) -> None:
    for item in items:
        start, end = backfill_char_range(content_md, item.description)
        item.char_start = start
        item.char_end = end


def review_legal_workspace(
    workspace: OutputWorkspace,
    client: LLMClient,
    *,
    config: InsightsConfig | None = None,
) -> LegalReviewFile:
    config = config or InsightsConfig.from_env()
    outline = OutlineTree.model_validate_json(workspace.outline_path.read_text(encoding="utf-8"))
    content_md = workspace.content_path.read_text(encoding="utf-8")
    blocks = load_content_blocks(workspace)
    router = SectionRouter(load_routing_rules(_ROUTING_PATH))

    route_keys = ["legal_risk", "pending"]
    target_node_ids: set[str] = set()
    for key in route_keys:
        for node in router.match_nodes(outline, key):
            target_node_ids.add(node.node_id)

    aggregated = LegalReviewLLMResponse()
    for node_id in sorted(target_node_ids):
        node = next(n for n in outline.nodes if n.node_id == node_id)
        md = _slice_node_markdown(workspace, content_md, outline, node_id, blocks=blocks)
        path = _section_path(node_id, outline)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(node.title, path, md)},
        ]
        batch = extract_json_model(client, messages, LegalReviewLLMResponse, max_retries=config.max_retries)
        aggregated.risk_items.extend(batch.risk_items)
        aggregated.pending_confirmations.extend(batch.pending_confirmations)

    risks = dedupe_by_title(aggregated.risk_items, title_getter=lambda x: x.description)
    pending = dedupe_by_title(aggregated.pending_confirmations, title_getter=lambda x: x.description)
    _apply_risk_anchors(risks, content_md)
    _apply_pending_anchors(pending, content_md)

    result = LegalReviewFile(
        source_workspace=str(workspace.root),
        risk_items=risks,
        pending_confirmations=pending,
    )
    write_json_artifact(
        workspace,
        "legal_review.json",
        result.model_dump(mode="json"),
        stage_name="legal",
        output_key="legal_review",
    )
    return result
