from __future__ import annotations

from viewer.models import JobState


class JobRegistry:
    def __init__(self) -> None:
        self._jobs: dict[str, JobState] = {}

    def create(self, job_id: str, session_id: str) -> JobState:
        job = JobState(
            job_id=job_id,
            session_id=session_id,
            stage="extract",
            message="starting pipeline",
            status="running",
            error=None,
        )
        self._jobs[job_id] = job
        return job

    def get(self, job_id: str) -> JobState | None:
        return self._jobs.get(job_id)

    def update(self, job_id: str, **fields: object) -> JobState:
        job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(job_id)
        updated = job.model_copy(update=fields)
        self._jobs[job_id] = updated
        return updated

    def remove_for_session(self, session_id: str) -> None:
        self._jobs = {job_id: job for job_id, job in self._jobs.items() if job.session_id != session_id}
