from __future__ import annotations

from viewer.models import InterpretJobState


class InterpretJobRegistry:
    def __init__(self) -> None:
        self._jobs: dict[str, InterpretJobState] = {}

    def create(self, job_id: str, session_id: str) -> InterpretJobState:
        job = InterpretJobState(
            job_id=job_id,
            session_id=session_id,
            stage="pipeline_1",
            message="starting interpret pipeline",
            status="running",
            error=None,
        )
        self._jobs[job_id] = job
        return job

    def get(self, job_id: str) -> InterpretJobState | None:
        return self._jobs.get(job_id)

    def update(self, job_id: str, **fields: object) -> InterpretJobState:
        job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(job_id)
        updated = job.model_copy(update=fields)
        self._jobs[job_id] = updated
        return updated
