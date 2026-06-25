from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from typing import Literal

from doc_chunk.llm.client import LLMClient
from doc_chunk.llm.openai_client import create_llm_client_from_env
from doc_chunk.workspace.layout import OutputWorkspace

from tender_insights.brief.extractor import extract_brief_workspace
from tender_insights.common.pipeline_runner import prepare_workspaces
from tender_insights.common.workspace_resolver import resolve_workspace
from tender_insights.interpret.extractor import interpret_workspace
from tender_insights.interpret.llm_logging import LLM_CALLS_FILENAME
from tender_insights.interpret.models import InterpretationFile
from tender_insights.interpret.render import render_interpretation_markdown
from tender_insights.legal.extractor import review_legal_workspace
from tender_insights.template.extractor import extract_templates_workspace
from tender_insights.gen_catalog.accept import accept_gen_catalog_draft
from tender_insights.gen_catalog.extractor import gen_catalog_workspace


def resolve_workspace_path(path: Path, *, output_dir: Path | None = None, overwrite: bool = False) -> OutputWorkspace:
    return resolve_workspace(path, output_dir=output_dir, overwrite=overwrite)


def setup_interpret_llm_logging(workspace: OutputWorkspace) -> Path:
    log_path = workspace.root / LLM_CALLS_FILENAME
    log_path.unlink(missing_ok=True)
    os.environ["INTERPRET_LOG_JSONL"] = str(log_path)
    return log_path


def interpret_document(
    workspace: OutputWorkspace,
    *,
    client: LLMClient | None = None,
    on_progress: Callable[[str, dict], None] | None = None,
):
    client = client or create_llm_client_from_env()
    return interpret_workspace(workspace, client, on_progress=on_progress)


def run_interpret_job(
    workspace: OutputWorkspace,
    *,
    client: LLMClient | None = None,
    on_progress: Callable[[str, dict], None] | None = None,
    include_template: bool = True,
    setup_logging: bool = True,
):
    client = client or create_llm_client_from_env()
    if setup_logging:
        setup_interpret_llm_logging(workspace)
    result = interpret_workspace(workspace, client, on_progress=on_progress)
    if include_template:
        extract_templates_workspace(workspace, client)
    return result


def extract_templates(workspace: OutputWorkspace, *, client: LLMClient | None = None):
    client = client or create_llm_client_from_env()
    return extract_templates_workspace(workspace, client)


def review_legal(workspace: OutputWorkspace, *, client: LLMClient | None = None):
    client = client or create_llm_client_from_env()
    return review_legal_workspace(workspace, client)


def extract_tender_brief(
    workspace: OutputWorkspace,
    *,
    client: LLMClient | None = None,
    on_progress: Callable[[str, dict], None] | None = None,
):
    client = client or create_llm_client_from_env()
    return extract_brief_workspace(workspace, client, on_progress=on_progress)


def render_interpretation_report(
    workspace: OutputWorkspace,
    *,
    output_path: Path | None = None,
) -> Path:
    interpretation_path = workspace.root / "interpretation.json"
    if not interpretation_path.is_file():
        raise FileNotFoundError(f"interpretation.json not found in {workspace.root}")
    data = InterpretationFile.model_validate_json(interpretation_path.read_text(encoding="utf-8"))
    markdown = render_interpretation_markdown(data)
    dest = output_path or (workspace.root / "interpret" / "interpret_report.md")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(markdown, encoding="utf-8")
    return dest


def run_gen_catalog_job(
    workspace: OutputWorkspace,
    *,
    client: LLMClient | None = None,
    mode: Literal["step", "auto"] = "auto",
    continue_from_session: bool = False,
    restart: bool = False,
    overwrite: bool = False,
    run_limit: int | None = None,
    on_progress: Callable[[str, dict], None] | None = None,
):
    client = client or create_llm_client_from_env()
    return gen_catalog_workspace(
        workspace,
        client,
        mode=mode,
        continue_from_session=continue_from_session,
        restart=restart,
        overwrite=overwrite,
        run_limit=run_limit,
        on_progress=on_progress,
    )


def continue_gen_catalog(workspace: OutputWorkspace, **kwargs):
    return run_gen_catalog_job(
        workspace,
        mode="step",
        continue_from_session=True,
        run_limit=1,
        **kwargs,
    )


def accept_gen_catalog(workspace: OutputWorkspace):
    return accept_gen_catalog_draft(workspace)
