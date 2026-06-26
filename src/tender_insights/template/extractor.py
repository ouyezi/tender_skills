from __future__ import annotations

import logging
from collections.abc import Callable

from doc_chunk.llm.client import LLMClient
from doc_chunk.models.outline import OutlineTree
from doc_chunk.workspace.layout import OutputWorkspace
from doc_chunk.workspace.manifest_io import load_manifest, save_manifest

from tender_insights.common.llm_extractor import extract_json_model
from tender_insights.common.output_writer import write_json_artifact
from tender_insights.common.section_slice import slice_for_llm
from tender_insights.config import InsightsConfig
from tender_insights.errors import LLMExtractionError
from tender_insights.interpret.llm_logging import log_llm_prompt
from tender_insights.template.merger import dedupe_template_hits
from tender_insights.template.models import (
    TemplateEntry,
    TemplateExtractResponse,
    TemplateHitLLM,
    TemplatePlanFile,
    TemplateShard,
    TemplatesIndexFile,
)
from tender_insights.template.planner import (
    _read_manifest_title,
    build_deterministic_plan,
    run_template_plan_llm,
    write_plan_json,
)
from tender_insights.template.prompts import TEMPLATE_EXTRACT_SYSTEM, build_extract_user_prompt

logger = logging.getLogger(__name__)


def _progress(
    on_progress: Callable[[str, dict], None] | None,
    stage: str,
    payload: dict,
) -> None:
    if on_progress is None:
        return
    try:
        on_progress(stage, payload)
    except Exception:
        return


def _append_manifest_warning(workspace: OutputWorkspace, warning: str) -> None:
    if not workspace.manifest_path.exists():
        return
    manifest = load_manifest(workspace.manifest_path)
    if warning not in manifest.warnings:
        manifest.warnings.append(warning)
    save_manifest(workspace, manifest)


def _shard_map(plan: TemplatePlanFile) -> dict[str, TemplateShard]:
    return {shard.shard_id: shard for shard in plan.shards}


def _materialize_templates(
    workspace: OutputWorkspace,
    hits: list[TemplateHitLLM],
    plan: TemplatePlanFile,
) -> tuple[list[TemplateEntry], list[str]]:
    templates_dir = workspace.root / "templates"
    templates_dir.mkdir(parents=True, exist_ok=True)
    shards = _shard_map(plan)
    type_counters: dict[str, int] = {}
    entries: list[TemplateEntry] = []
    warnings: list[str] = []

    for idx, hit in enumerate(hits, start=1):
        md = hit.markdown.strip()
        if not md:
            msg = f"empty markdown for template: {hit.title}"
            warnings.append(msg)
            logger.warning(msg)
            continue
        type_counters[hit.type] = type_counters.get(hit.type, 0) + 1
        filename = f"{hit.type}-{type_counters[hit.type]:03d}.md"
        rel_path = f"templates/{filename}"
        (templates_dir / filename).write_text(md, encoding="utf-8")
        shard = shards.get(hit.shard_id) if hit.shard_id else None
        excerpt = hit.source_excerpt.strip() or md[:200]
        entries.append(
            TemplateEntry(
                id=f"tpl-{idx:03d}",
                type=hit.type,
                type_label=hit.type_label,
                title=hit.title,
                section_path=shard.section_path if shard else [],
                file=rel_path,
                char_start=None,
                char_end=None,
                confidence=hit.confidence,
                extraction_method="llm",
                shard_id=hit.shard_id,
            )
        )
        if not hit.source_excerpt:
            hit.source_excerpt = excerpt
    return entries, warnings


def extract_templates_workspace(
    workspace: OutputWorkspace,
    client: LLMClient,
    *,
    config: InsightsConfig | None = None,
    on_progress: Callable[[str, dict], None] | None = None,
) -> TemplatesIndexFile:
    config = config or InsightsConfig.from_env()
    content_md = workspace.content_path.read_text(encoding="utf-8")
    outline = OutlineTree.model_validate_json(workspace.outline_path.read_text(encoding="utf-8"))
    doc_title = _read_manifest_title(workspace)

    templates_dir = workspace.root / "templates"
    templates_dir.mkdir(parents=True, exist_ok=True)

    plan = build_deterministic_plan(content_md, outline, config)
    if config.template_plan_enabled:
        plan = run_template_plan_llm(workspace, client, plan, doc_title, config)
    write_plan_json(workspace, plan)

    total_steps = plan.shard_count + 2
    _progress(
        on_progress,
        "template_plan",
        {"current": 0, "total": total_steps, "shard_count": plan.shard_count},
    )

    all_hits: list[TemplateHitLLM] = []
    for i, shard in enumerate(plan.shards, start=1):
        _progress(
            on_progress,
            "template_extract",
            {
                "current": i,
                "total": total_steps,
                "shard_id": shard.shard_id,
                "detail": " > ".join(shard.section_path),
            },
        )
        shard_md = slice_for_llm(workspace, content_md, shard.char_start, shard.char_end)
        messages = [
            {"role": "system", "content": TEMPLATE_EXTRACT_SYSTEM},
            {
                "role": "user",
                "content": build_extract_user_prompt(shard=shard, shard_markdown=shard_md),
            },
        ]
        log_llm_prompt(
            call_type="template_extract",
            messages=messages,
            workspace=str(workspace.root),
            segment_id=shard.shard_id,
            section_path=shard.section_path,
        )
        try:
            batch = extract_json_model(
                client,
                messages,
                TemplateExtractResponse,
                max_retries=config.max_retries,
                log_context={
                    "call_type": "template_extract",
                    "segment_id": shard.shard_id,
                },
            )
            for hit in batch.templates:
                hit.shard_id = shard.shard_id
                all_hits.append(hit)
        except LLMExtractionError:
            logger.warning("template extract failed for %s", shard.shard_id)

    _progress(
        on_progress,
        "template_merge",
        {"current": total_steps - 1, "total": total_steps},
    )
    merged = dedupe_template_hits(all_hits)
    entries, _warnings = _materialize_templates(workspace, merged, plan)

    result = TemplatesIndexFile(
        schema_version="1.1",
        templates=entries,
        plan_ref="templates/plan.json",
        shard_count=plan.shard_count,
    )
    write_json_artifact(
        workspace,
        "templates/index.json",
        result.model_dump(mode="json"),
        stage_name="template",
        output_key="templates",
    )
    if not entries:
        _append_manifest_warning(workspace, "no templates identified")
    return result
