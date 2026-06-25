from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from doc_chunk.llm.client import LLMClient
from doc_chunk.llm.openai_client import create_llm_client_from_env
from doc_chunk.workspace.layout import OutputWorkspace
from tender_insights.api import accept_gen_catalog, run_gen_catalog_job

from viewer.services.interpret_job_registry import InterpretJobRegistry
from viewer.services.interpret_session_store import InterpretSessionStore

_LOGGER = logging.getLogger("viewer.gen_catalog")


class GenCatalogPipelineService:
    def __init__(
        self,
        *,
        sessions: InterpretSessionStore,
        jobs: InterpretJobRegistry,
        llm_client_factory: Callable[[], LLMClient] | None = None,
    ) -> None:
        self._sessions = sessions
        self._jobs = jobs
        self._llm_client_factory = llm_client_factory or create_llm_client_from_env

    def _report(self, job_id: str, *, payload: dict, dual_file: bool, status: str = "running") -> None:
        current = int(payload.get("current", 0))
        total = int(payload.get("total", 1))
        percent = int(current * 100 / total) if total else 0
        self._jobs.update(
            job_id,
            stage="gen_catalog",
            message=str(payload.get("message", "生成目录")),
            status=status,
            progress_percent=min(percent, 100),
            step_current=current,
            step_total=total,
            detail=str(payload.get("detail", "")),
            dual_file=dual_file,
        )

    async def run_gen_catalog(
        self,
        *,
        job_id: str,
        session_id: str,
        workspace_dir: Path,
        mode: Literal["step", "auto"] = "step",
        continue_from_session: bool = False,
        restart: bool = False,
        dual_file: bool = False,
    ) -> None:
        try:
            ws = OutputWorkspace.open_existing(workspace_dir)
            client = self._llm_client_factory()
            run_limit = 1 if mode == "step" or continue_from_session else None

            def _progress(_stage: str, payload: dict) -> None:
                self._report(job_id, payload=payload, dual_file=dual_file)

            await asyncio.to_thread(
                run_gen_catalog_job,
                ws,
                client=client,
                mode=mode,
                continue_from_session=continue_from_session,
                restart=restart,
                run_limit=run_limit,
                on_progress=_progress,
            )
            self._jobs.update(
                job_id,
                stage="done",
                message="目录生成步骤完成",
                status="done",
                progress_percent=100,
                dual_file=dual_file,
            )
            self._sessions.update(session_id, status="success", error=None)
        except Exception as exc:  # noqa: BLE001
            message = str(exc)
            _LOGGER.exception("gen_catalog job failed")
            self._jobs.update(
                job_id,
                stage="failed",
                message=message,
                status="failed",
                error=message,
                dual_file=dual_file,
            )
            self._sessions.update(session_id, status="failed", error=message)

    async def run_accept(
        self,
        *,
        job_id: str,
        session_id: str,
        workspace_dir: Path,
        dual_file: bool = False,
    ) -> None:
        try:
            ws = OutputWorkspace.open_existing(workspace_dir)
            await asyncio.to_thread(accept_gen_catalog, ws)
            self._jobs.update(
                job_id,
                stage="gen_catalog_accept",
                message="目录已确认落盘",
                status="done",
                progress_percent=100,
                dual_file=dual_file,
            )
            self._sessions.update(session_id, status="success", error=None)
        except Exception as exc:  # noqa: BLE001
            message = str(exc)
            self._jobs.update(
                job_id,
                stage="failed",
                message=message,
                status="failed",
                error=message,
                dual_file=dual_file,
            )
            self._sessions.update(session_id, status="failed", error=message)
