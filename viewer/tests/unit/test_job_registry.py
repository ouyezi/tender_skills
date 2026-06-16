from __future__ import annotations

from viewer.models import JobState
from viewer.services.job_registry import JobRegistry


def test_job_registry_tracks_progress() -> None:
    registry = JobRegistry()
    registry.create("job1", "sess1")
    registry.update("job1", stage="outline", message="building outline", status="running")

    job = registry.get("job1")
    assert isinstance(job, JobState)
    assert job.stage == "outline"
    assert job.status == "running"
