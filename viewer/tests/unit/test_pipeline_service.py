from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from doc_chunk.api import run_pipeline

from viewer.models import SessionRecord
from viewer.services.job_registry import JobRegistry
from viewer.services.pipeline import PipelineService
from viewer.services.session_store import SessionStore


@pytest.mark.asyncio
async def test_pipeline_service_marks_session_success(sample_docx: Path, tmp_path: Path) -> None:
    sessions = SessionStore(tmp_path / "sessions.json")
    jobs = JobRegistry()
    now = datetime.now(UTC).isoformat()
    session = SessionRecord(
        id="sess1",
        title="sample.docx",
        workspace_path=str(tmp_path / "ws"),
        source_type="upload",
        status="running",
        created_at=now,
        opened_at=now,
    )
    sessions.add(session)
    jobs.create("job1", "sess1")

    service = PipelineService(sessions=sessions, jobs=jobs, run_pipeline_fn=run_pipeline)
    await service.run_upload_job(
        job_id="job1",
        session_id="sess1",
        input_path=sample_docx,
        workspace_dir=tmp_path / "ws",
    )

    updated = sessions.get("sess1")
    assert updated is not None
    assert updated.status == "success"
    job = jobs.get("job1")
    assert job is not None
    assert job.status == "done"
    assert (tmp_path / "ws" / "outline.json").exists()
