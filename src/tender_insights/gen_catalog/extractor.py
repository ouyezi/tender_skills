from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal

from doc_chunk.llm.client import LLMClient
from doc_chunk.workspace.layout import OutputWorkspace

from tender_insights.common.llm_extractor import extract_json_model
from tender_insights.config import InsightsConfig
from tender_insights.gen_catalog.context import (
    build_initial_user_prompt,
    build_node_apply_user_prompt,
    build_node_plan_user_prompt,
)
from tender_insights.gen_catalog.excerpt import pick_node_excerpt
from tender_insights.gen_catalog.models import (
    BidOutlineFile,
    BidOutlineLLMResponse,
    BidOutlineNode,
    BidOutlinePlanLLMResponse,
    GenCatalogSession,
)
from tender_insights.gen_catalog.prerequisites import PrerequisiteReport, validate_prerequisites
from tender_insights.gen_catalog.prompts import GEN_CATALOG_INITIAL_SYSTEM, GEN_CATALOG_NODE_SYSTEM
from tender_insights.gen_catalog.normalize import normalize_outline_ids
from tender_insights.gen_catalog.queue import (
    build_refine_queue,
    compute_step_total,
    find_node,
    next_pending_node_id,
)
from tender_insights.gen_catalog.session import (
    DRAFT_NAME,
    clear_gen_catalog_artifacts,
    load_session,
    save_session,
)
from tender_insights.interpret.llm_logging import LLM_CALLS_FILENAME, log_llm_prompt


def ensure_gen_catalog_llm_logging(workspace: OutputWorkspace) -> None:
    os.environ["INTERPRET_LOG_JSONL"] = str(workspace.root / LLM_CALLS_FILENAME)


def _draft_path(workspace: OutputWorkspace):
    return workspace.root / DRAFT_NAME


def load_draft(workspace: OutputWorkspace) -> BidOutlineFile | None:
    path = _draft_path(workspace)
    if not path.is_file():
        return None
    return BidOutlineFile.model_validate_json(path.read_text(encoding="utf-8"))


def save_draft(workspace: OutputWorkspace, draft: BidOutlineFile) -> None:
    _draft_path(workspace).write_text(draft.model_dump_json(), encoding="utf-8")


def _source_markdown(workspace: OutputWorkspace) -> str:
    for rel in ("interpret/source_content.md", "content.md"):
        path = workspace.root / rel
        if path.is_file():
            return path.read_text(encoding="utf-8")
    return ""


def _build_draft_shell(
    report: PrerequisiteReport,
    root: BidOutlineNode,
    *,
    mode: Literal["step", "auto"],
    status: Literal["running", "paused", "awaiting_accept", "accepted", "failed"],
    step_index: int,
    step_total: int,
) -> BidOutlineFile:
    brief_snapshot = None
    if report.brief is not None:
        brief_snapshot = {
            "summary_text": report.brief.summary_text,
            "fields": report.brief.fields.model_dump(),
        }
    return BidOutlineFile(
        source_workspace=str(report.interpretation.source_workspace),
        interpretation_schema=report.interpretation.schema_version,
        mode=mode,
        status=status,
        step_index=step_index,
        step_total=step_total,
        overview_snapshot=report.interpretation.overview.model_dump(),
        brief_snapshot=brief_snapshot,
        root=root,
    )


def run_gen_catalog_initial(
    workspace: OutputWorkspace,
    client: LLMClient,
    *,
    report: PrerequisiteReport,
    mode: Literal["step", "auto"] = "step",
    config: InsightsConfig | None = None,
) -> BidOutlineFile:
    config = config or InsightsConfig.from_env()
    user_content = build_initial_user_prompt(report)
    messages = [
        {"role": "system", "content": GEN_CATALOG_INITIAL_SYSTEM},
        {"role": "user", "content": user_content},
    ]
    log_llm_prompt(
        call_type="gen_catalog_initial",
        messages=messages,
        workspace=str(workspace.root),
        segment_id="initial",
    )
    response = extract_json_model(
        client,
        messages,
        BidOutlineLLMResponse,
        max_retries=config.max_retries,
        log_context={"call_type": "gen_catalog_initial", "segment_id": "initial"},
    )
    normalize_outline_ids(response.outline)
    step_total = compute_step_total(response.outline)
    draft = _build_draft_shell(
        report,
        response.outline,
        mode=mode,
        status="paused" if mode == "step" else "running",
        step_index=1,
        step_total=step_total,
    )
    save_draft(workspace, draft)
    session = GenCatalogSession(
        mode=mode,
        status="paused" if mode == "step" else "running",
        step_index=1,
        step_total=step_total,
        node_queue=build_refine_queue(response.outline),
        completed_steps=["initial"],
    )
    save_session(workspace, session)
    return draft


    save_session(workspace, session)
    return draft


def run_gen_catalog_node_plan(
    workspace: OutputWorkspace,
    client: LLMClient,
    *,
    report: PrerequisiteReport,
    draft: BidOutlineFile,
    node_id: str,
    excerpt: str,
    title: str,
    config: InsightsConfig | None = None,
) -> BidOutlinePlanLLMResponse:
    config = config or InsightsConfig.from_env()
    user_content = build_node_plan_user_prompt(report.brief, draft.root, excerpt)
    messages = [
        {"role": "system", "content": GEN_CATALOG_NODE_SYSTEM},
        {"role": "user", "content": user_content},
    ]
    log_llm_prompt(
        call_type="gen_catalog_node_plan",
        messages=messages,
        workspace=str(workspace.root),
        segment_id=node_id,
        section_path=[title],
    )
    return extract_json_model(
        client,
        messages,
        BidOutlinePlanLLMResponse,
        max_retries=config.max_retries,
        log_context={"call_type": "gen_catalog_node_plan", "segment_id": node_id},
    )


def run_gen_catalog_node_apply(
    workspace: OutputWorkspace,
    client: LLMClient,
    *,
    report: PrerequisiteReport,
    draft: BidOutlineFile,
    node_id: str,
    excerpt: str,
    title: str,
    refinement_plan: str,
    config: InsightsConfig | None = None,
) -> BidOutlineLLMResponse:
    config = config or InsightsConfig.from_env()
    user_content = build_node_apply_user_prompt(
        report.brief, draft.root, excerpt, refinement_plan
    )
    messages = [
        {"role": "system", "content": GEN_CATALOG_NODE_SYSTEM},
        {"role": "user", "content": user_content},
    ]
    log_llm_prompt(
        call_type="gen_catalog_node_apply",
        messages=messages,
        workspace=str(workspace.root),
        segment_id=node_id,
        section_path=[title],
    )
    response = extract_json_model(
        client,
        messages,
        BidOutlineLLMResponse,
        max_retries=config.max_retries,
        log_context={"call_type": "gen_catalog_node_apply", "segment_id": node_id},
    )
    normalize_outline_ids(response.outline)
    return response


def run_gen_catalog_node(
    workspace: OutputWorkspace,
    client: LLMClient,
    *,
    report: PrerequisiteReport,
    draft: BidOutlineFile,
    session: GenCatalogSession,
    node_id: str,
    config: InsightsConfig | None = None,
) -> BidOutlineFile:
    config = config or InsightsConfig.from_env()
    node = find_node(draft.root, node_id)
    title = node.title if node is not None else node_id
    excerpt = pick_node_excerpt(
        _source_markdown(workspace),
        node_title=title,
        max_chars=config.gen_catalog_excerpt_max_chars,
        min_chars=config.gen_catalog_excerpt_min_chars,
    )

    plan = run_gen_catalog_node_plan(
        workspace,
        client,
        report=report,
        draft=draft,
        node_id=node_id,
        excerpt=excerpt,
        title=title,
        config=config,
    )
    session.last_plan = {
        "node_id": node_id,
        "needs_optimization": plan.needs_optimization,
        "refinement_plan": plan.refinement_plan,
    }
    session.current_node_id = node_id
    session.current_node_title = title

    if plan.needs_optimization:
        response = run_gen_catalog_node_apply(
            workspace,
            client,
            report=report,
            draft=draft,
            node_id=node_id,
            excerpt=excerpt,
            title=title,
            refinement_plan=plan.refinement_plan,
            config=config,
        )
        draft = _build_draft_shell(
            report,
            response.outline,
            mode=session.mode,
            status=draft.status,
            step_index=session.step_index + 1,
            step_total=session.step_total,
        )
        save_draft(workspace, draft)

    session.step_index += 1
    session.completed_steps.append(node_id)
    save_session(workspace, session)
    return draft


def _emit_progress(
    on_progress: Callable[[str, dict], None] | None,
    *,
    message: str,
    detail: str,
    current: int,
    total: int,
    step: str,
    node_id: str | None = None,
    node_title: str | None = None,
) -> None:
    if on_progress is None:
        return
    payload: dict = {
        "message": message,
        "detail": detail,
        "current": current,
        "total": total,
        "step": step,
    }
    if node_id is not None:
        payload["node_id"] = node_id
    if node_title is not None:
        payload["node_title"] = node_title
    on_progress("gen_catalog", payload)


def gen_catalog_workspace(
    workspace: OutputWorkspace,
    client: LLMClient,
    *,
    mode: Literal["step", "auto"] = "auto",
    continue_from_session: bool = False,
    restart: bool = False,
    overwrite: bool = False,
    run_limit: int | None = None,
    on_progress: Callable[[str, dict], None] | None = None,
    config: InsightsConfig | None = None,
) -> BidOutlineFile:
    if restart:
        clear_gen_catalog_artifacts(workspace)

    report = validate_prerequisites(workspace, overwrite=overwrite)
    ensure_gen_catalog_llm_logging(workspace)

    draft = load_draft(workspace)
    session: GenCatalogSession | None = None
    if continue_from_session or draft is not None:
        try:
            session = load_session(workspace)
        except FileNotFoundError:
            session = None

    steps_run = 0

    if draft is None:
        _emit_progress(
            on_progress,
            message="正在生成初始目录…",
            detail="步骤 1",
            current=0,
            total=1,
            step="gen_catalog_initial",
        )
        draft = run_gen_catalog_initial(workspace, client, report=report, mode=mode, config=config)
        session = load_session(workspace)
        steps_run += 1
        if mode == "step" and (run_limit is None or steps_run >= run_limit):
            return draft

    assert session is not None
    assert draft is not None

    while True:
        pending = next_pending_node_id(session.node_queue, session.completed_steps)
        if pending is None:
            draft.status = "awaiting_accept"
            session.status = "awaiting_accept"
            save_draft(workspace, draft)
            save_session(workspace, session)
            _emit_progress(
                on_progress,
                message="目录生成完成，待确认落盘",
                detail=f"{session.step_index} / {session.step_total}",
                current=session.step_index,
                total=session.step_total,
                step="awaiting_accept",
            )
            return draft

        node = find_node(draft.root, pending)
        title = node.title if node is not None else pending
        _emit_progress(
            on_progress,
            message=f"正在完善节点：{title}",
            detail=f"节点 {session.step_index} / {session.step_total}",
            current=session.step_index,
            total=session.step_total,
            step="gen_catalog_node",
            node_id=pending,
            node_title=title,
        )
        draft = run_gen_catalog_node(
            workspace,
            client,
            report=report,
            draft=draft,
            session=session,
            node_id=pending,
            config=config,
        )
        session = load_session(workspace)
        steps_run += 1
        if mode == "step" and (run_limit is None or steps_run >= run_limit):
            session.status = "paused"
            draft.status = "paused"
            save_session(workspace, session)
            save_draft(workspace, draft)
            return draft
