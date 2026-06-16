from __future__ import annotations

from fastapi import APIRouter, HTTPException

from viewer.deps import get_job_registry

router = APIRouter(tags=["jobs"])


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = get_job_registry().get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job.model_dump()
