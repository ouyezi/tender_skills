from __future__ import annotations

from datetime import UTC, datetime

from typing import Literal

from viewer.models import InterpretJobState


class InterpretJobRegistry:
    def __init__(self) -> None:
        self._jobs: dict[str, InterpretJobState] = {}

    def create(
        self,
        job_id: str,
        session_id: str,
        *,
        dual_file: bool = False,
        job_kind: Literal["interpret", "brief", "gen_catalog"] = "interpret",
    ) -> InterpretJobState:
        if job_kind == "brief":
            message = "准备提取招标概要"
        elif job_kind == "gen_catalog":
            message = "准备生成投标目录"
        else:
            message = "准备开始解读流水线"
        stage = "gen_catalog" if job_kind == "gen_catalog" else "pipeline_1"
        job = InterpretJobState(
            job_id=job_id,
            session_id=session_id,
            job_kind=job_kind,
            stage=stage,
            message=message,
            status="running",
            error=None,
            progress_percent=0,
            step_current=0,
            step_total=0,
            detail="",
            dual_file=dual_file,
        )
        self._jobs[job_id] = job
        return job

    def get(self, job_id: str) -> InterpretJobState | None:
        return self._jobs.get(job_id)

    def get_latest_for_session(self, session_id: str) -> InterpretJobState | None:
        matches = [job for job in self._jobs.values() if job.session_id == session_id]
        if not matches:
            return None
        return max(matches, key=lambda job: job.updated_at)

    def update(self, job_id: str, **fields: object) -> InterpretJobState:
        job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(job_id)
        fields.setdefault("updated_at", datetime.now(UTC).isoformat())
        updated = job.model_copy(update=fields)
        self._jobs[job_id] = updated
        return updated

    def remove_for_session(self, session_id: str) -> None:
        self._jobs = {
            job_id: job for job_id, job in self._jobs.items() if job.session_id != session_id
        }
