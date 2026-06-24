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

    segment_json = json.dumps(
        {
            "disqualification_items": [],
            "scoring_items": [],
            "bid_risk_items": [],
            "directory_requirements": [],
        }
    )
    overview_json = json.dumps(
        {
            "summary": "概要",
            "disqualification_summary": "废标",
            "scoring_summary": "得分",
            "bid_risk_summary": "风险",
            "directory_summary": "目录",
        }
    )

    class _InterpretFakeLLM(FakeLLMClient):
        def __init__(self) -> None:
            super().__init__()
            self._segment_json = segment_json
            self._overview_json = overview_json

        def complete(self, messages, *, response_format="text", timeout=60.0):
            user_text = " ".join(
                str(m.get("content", "")) for m in messages if m.get("role") == "user"
            )
            if "已提取明细" in user_text:
                return self._overview_json
            return self._segment_json

    fake_llm = _InterpretFakeLLM()
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
