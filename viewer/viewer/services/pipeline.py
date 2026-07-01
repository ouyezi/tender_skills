from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path

from doc_chunk.api import run_pipeline
from doc_chunk.models.document import PipelineResult

from viewer.config import ViewerSettings
from viewer.services.job_registry import JobRegistry
from viewer.services.session_store import SessionStore
from viewer.services.interpret_session_store import InterpretSessionStore
from viewer.services.session_sync import sync_session_status

_STAGE_MAP = {
    "extract": "extract",
    "outline": "outline",
    "tree": "tree",
    "chunk": "chunk",
    "enrich": "chunk",
}


class PipelineService:
    def __init__(
        self,
        *,
        sessions: SessionStore,
        jobs: JobRegistry,
        interpret_sessions: InterpretSessionStore | None = None,
        settings: ViewerSettings | None = None,
        run_pipeline_fn: Callable[..., PipelineResult] = run_pipeline,
    ) -> None:
        self._sessions = sessions
        self._jobs = jobs
        self._interpret_sessions = interpret_sessions
        self._settings = settings or ViewerSettings.load()
        self._run_pipeline = run_pipeline_fn

    def _update_session_status(self, session_id: str, **fields: object) -> None:
        if self._interpret_sessions is not None:
            sync_session_status(
                session_id,
                viewer_store=self._sessions,
                interpret_store=self._interpret_sessions,
                settings=self._settings,
                **fields,
            )
            return
        self._sessions.update(session_id, **fields)

    def _on_progress(self, job_id: str, stage: str, payload: dict) -> None:
        mapped = _STAGE_MAP.get(stage, "chunk")
        message = str(payload.get("message", stage))
        self._jobs.update(job_id, stage=mapped, message=message, status="running")

    async def run_upload_job(
        self,
        *,
        job_id: str,
        session_id: str,
        input_path: Path,
        workspace_dir: Path,
    ) -> None:
        def _progress(stage: str, payload: dict) -> None:
            self._on_progress(job_id, stage, payload)

        def _execute() -> PipelineResult:
            return self._run_pipeline(
                input_path,
                workspace_dir,
                overwrite=True,
                skip_refine=True,
                skip_enrich=True,
                on_progress=_progress,
            )

        try:
            result = await asyncio.to_thread(_execute)
            if result.status == "failed":
                error = result.errors[0]["error"] if result.errors else "pipeline failed"
                self._jobs.update(job_id, stage="failed", message=error, status="failed", error=error)
                self._update_session_status(session_id, status="failed", error=error)
                return
            self._jobs.update(job_id, stage="done", message="pipeline complete", status="done")
            self._update_session_status(session_id, status="success", error=None)
        except Exception as exc:  # noqa: BLE001
            message = str(exc)
            self._jobs.update(job_id, stage="failed", message=message, status="failed", error=message)
            self._update_session_status(session_id, status="failed", error=message)
