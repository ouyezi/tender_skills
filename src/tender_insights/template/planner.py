from __future__ import annotations

from doc_chunk.llm.client import LLMClient
from doc_chunk.models.outline import OutlineTree
from doc_chunk.workspace.layout import OutputWorkspace
from doc_chunk.workspace.manifest_io import load_manifest

from tender_insights.common.llm_extractor import extract_json_model
from tender_insights.common.output_writer import write_json_artifact
from tender_insights.config import InsightsConfig
from tender_insights.interpret.llm_logging import log_llm_prompt
from tender_insights.template.models import TemplatePlanFile, TemplatePlanLLMResponse
from tender_insights.template.prompts import TEMPLATE_PLAN_SYSTEM, build_plan_user_prompt
from tender_insights.template.sharder import build_template_shards


def _read_manifest_title(workspace: OutputWorkspace) -> str:
    if not workspace.manifest_path.exists():
        return ""
    manifest = load_manifest(workspace.manifest_path)
    return manifest.source.title or manifest.source.file_name or ""


def build_deterministic_plan(
    content_md: str,
    outline: OutlineTree,
    config: InsightsConfig,
) -> TemplatePlanFile:
    shards = build_template_shards(content_md, outline, config=config)
    return TemplatePlanFile(
        whole_doc_chars=len(content_md),
        shard_count=len(shards),
        shards=shards,
    )


def write_plan_json(workspace: OutputWorkspace, plan: TemplatePlanFile) -> None:
    write_json_artifact(
        workspace,
        "templates/plan.json",
        plan.model_dump(mode="json"),
        stage_name="template",
        output_key="templates",
    )


def run_template_plan_llm(
    workspace: OutputWorkspace,
    client: LLMClient,
    plan: TemplatePlanFile,
    doc_title: str,
    config: InsightsConfig,
) -> TemplatePlanFile:
    if not config.template_plan_enabled:
        return plan

    shard_summaries = [
        {
            "shard_id": shard.shard_id,
            "section_path": shard.section_path,
            "char_count": shard.char_count,
            "strategy": shard.strategy,
        }
        for shard in plan.shards
    ]
    messages = [
        {"role": "system", "content": TEMPLATE_PLAN_SYSTEM},
        {
            "role": "user",
            "content": build_plan_user_prompt(
                doc_title=doc_title,
                shard_summaries=shard_summaries,
            ),
        },
    ]
    log_llm_prompt(
        call_type="template_plan",
        messages=messages,
        workspace=str(workspace.root),
        segment_id="plan",
    )
    response = extract_json_model(
        client,
        messages,
        TemplatePlanLLMResponse,
        max_retries=config.max_retries,
        log_context={"call_type": "template_plan", "segment_id": "plan"},
    )
    return plan.model_copy(
        update={
            "llm_notes": response.notes or None,
            "priority_sections": response.priority_sections,
        }
    )
