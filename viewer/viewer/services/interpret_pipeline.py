from __future__ import annotations

import asyncio
import shutil
from collections.abc import Callable
from pathlib import Path

from doc_chunk.api import run_pipeline
from doc_chunk.llm.client import LLMClient
from doc_chunk.llm.openai_client import create_llm_client_from_env
from doc_chunk.models.document import PipelineResult
from doc_chunk.workspace.layout import OutputWorkspace
from tender_insights.api import extract_templates, interpret_document

from viewer.services.interpret_job_registry import InterpretJobRegistry
from viewer.services.interpret_session_store import InterpretSessionStore
from viewer.services.workspace_merge import merge_workspaces, validate_merged_workspace


class InterpretPipelineService:
    def __init__(
        self,
        *,
        sessions: InterpretSessionStore,
        jobs: InterpretJobRegistry,
        run_pipeline_fn: Callable[..., PipelineResult] = run_pipeline,
        llm_client_factory: Callable[[], LLMClient] | None = None,
    ) -> None:
        self._sessions = sessions
        self._jobs = jobs
        self._run_pipeline = run_pipeline_fn
        self._llm_client_factory = llm_client_factory or create_llm_client_from_env

    async def run_job(
        self,
        *,
        job_id: str,
        session_id: str,
        input_paths: list[Path],
        workspace_dir: Path,
    ) -> None:
        temp_dirs: list[Path] = []
        try:
            for idx, input_path in enumerate(input_paths, start=1):
                stage = "pipeline_1" if idx == 1 else "pipeline_2"
                self._jobs.update(job_id, stage=stage, message=f"extracting file {idx}")
                temp = workspace_dir.parent / f"{session_id}_tmp{idx}"
                temp_dirs.append(temp)
                result = await asyncio.to_thread(
                    self._run_pipeline,
                    input_path,
                    temp,
                    overwrite=True,
                    skip_refine=True,
                    skip_enrich=True,
                )
                if result.status == "failed":
                    error = result.errors[0]["error"] if result.errors else "pipeline failed"
                    raise RuntimeError(error)

            if len(input_paths) == 1:
                if workspace_dir.exists():
                    shutil.rmtree(workspace_dir)
                shutil.copytree(temp_dirs[0], workspace_dir)
            else:
                self._jobs.update(job_id, stage="merge", message="merging workspaces")
                if workspace_dir.exists():
                    shutil.rmtree(workspace_dir)
                merge_workspaces(
                    workspace_dir,
                    sources=[
                        (temp_dirs[0], input_paths[0].name),
                        (temp_dirs[1], input_paths[1].name),
                    ],
                )
                validate_merged_workspace(workspace_dir)

            ws = OutputWorkspace.open_existing(workspace_dir)
            client = self._llm_client_factory()
            self._jobs.update(job_id, stage="interpret", message="running interpret")
            await asyncio.to_thread(interpret_document, ws, client=client)
            self._jobs.update(job_id, stage="template", message="extracting templates")
            await asyncio.to_thread(extract_templates, ws, client=client)
            self._jobs.update(job_id, stage="done", message="complete", status="done")
            self._sessions.update(session_id, status="success", error=None)
        except Exception as exc:  # noqa: BLE001
            message = str(exc)
            self._jobs.update(
                job_id,
                stage="failed",
                message=message,
                status="failed",
                error=message,
            )
            self._sessions.update(session_id, status="failed", error=message)
        finally:
            for temp in temp_dirs:
                shutil.rmtree(temp, ignore_errors=True)
