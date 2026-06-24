from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from doc_chunk.llm.client import LLMClient
from doc_chunk.llm.openai_client import create_llm_client_from_env
from doc_chunk.workspace.layout import OutputWorkspace

from tender_insights.common.workspace_resolver import resolve_workspace
from tender_insights.interpret.extractor import interpret_workspace
from tender_insights.legal.extractor import review_legal_workspace
from tender_insights.template.extractor import extract_templates_workspace


def resolve_workspace_path(path: Path, *, output_dir: Path | None = None, overwrite: bool = False) -> OutputWorkspace:
    return resolve_workspace(path, output_dir=output_dir, overwrite=overwrite)


def interpret_document(
    workspace: OutputWorkspace,
    *,
    client: LLMClient | None = None,
    on_progress: Callable[[str, dict], None] | None = None,
):
    client = client or create_llm_client_from_env()
    return interpret_workspace(workspace, client, on_progress=on_progress)


def extract_templates(workspace: OutputWorkspace, *, client: LLMClient | None = None):
    client = client or create_llm_client_from_env()
    return extract_templates_workspace(workspace, client)


def review_legal(workspace: OutputWorkspace, *, client: LLMClient | None = None):
    client = client or create_llm_client_from_env()
    return review_legal_workspace(workspace, client)
