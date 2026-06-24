from __future__ import annotations

import json
from pathlib import Path

import pytest
from doc_chunk.llm.client import FakeLLMClient

from viewer.models import InterpretSessionRecord
from viewer.services.interpret_job_registry import InterpretJobRegistry
from viewer.services.interpret_pipeline import InterpretPipelineService
from viewer.services.interpret_session_store import InterpretSessionStore


@pytest.mark.asyncio
async def test_single_file_interpret_pipeline(sample_docx: Path, tmp_path: Path) -> None:
    sessions = InterpretSessionStore(tmp_path / "interpret_sessions.json")
    jobs = InterpretJobRegistry()
    session_id = "sess-1"
    job_id = "job-1"
    workspace_dir = tmp_path / "workspaces" / session_id
    workspace_dir.mkdir(parents=True)
    sessions.add(
        InterpretSessionRecord(
            id=session_id,
            title=sample_docx.name,
            workspace_path=str(workspace_dir),
            source_files=[sample_docx.name],
            status="running",
            created_at="2026-06-24T00:00:00+00:00",
            opened_at="2026-06-24T00:00:00+00:00",
        )
    )
    jobs.create(job_id, session_id)

    fake_llm = FakeLLMClient(
        default_response=json.dumps(
            {
                "disqualification_items": [],
                "scoring_items": [],
                "bid_risk_items": [],
                "directory_requirements": [],
            }
        )
    )
    service = InterpretPipelineService(
        sessions=sessions,
        jobs=jobs,
        llm_client_factory=lambda: fake_llm,
    )
    await service.run_job(
        job_id=job_id,
        session_id=session_id,
        input_paths=[sample_docx],
        workspace_dir=workspace_dir,
    )
    job = jobs.get(job_id)
    assert job is not None
    assert job.status == "done"
    assert (workspace_dir / "interpretation.json").exists()
    assert (workspace_dir / "templates" / "index.json").exists()
