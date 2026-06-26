from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.helpers.interpret_fake_llm import InterpretFakeLLM
from viewer.models import InterpretSessionRecord
from viewer.services.interpret_job_registry import InterpretJobRegistry
from viewer.services.interpret_pipeline import InterpretPipelineService
from viewer.services.interpret_session_store import InterpretSessionStore


@pytest.mark.asyncio
async def test_single_file_interpret_pipeline(
    sample_docx: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OCR_ENABLED", "false")
    monkeypatch.setenv("TEMPLATE_PLAN_ENABLED", "false")
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
    extract_json = json.dumps(
        {
            "templates": [
                {
                    "title": "授权书",
                    "type": "authorization",
                    "type_label": "授权书",
                    "char_start": 0,
                    "char_end": 20,
                    "confidence": 0.9,
                    "source_excerpt": "授权",
                }
            ]
        }
    )

    fake_llm = InterpretFakeLLM(
        segment_json=segment_json,
        overview_json=overview_json,
        extract_json=extract_json,
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
    index_data = json.loads((workspace_dir / "templates" / "index.json").read_text(encoding="utf-8"))
    assert len(index_data.get("templates", [])) >= 1


@pytest.mark.asyncio
async def test_brief_on_existing_workspace(sample_docx: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.helpers.brief_fake_llm import BriefFakeLLM

    monkeypatch.setenv("OCR_ENABLED", "false")
    from doc_chunk.api import run_pipeline

    workspace_dir = tmp_path / "workspaces" / "sess-brief-ws"
    run_pipeline(sample_docx, workspace_dir, overwrite=True, skip_refine=True, skip_enrich=True)

    sessions = InterpretSessionStore(tmp_path / "interpret_sessions.json")
    jobs = InterpretJobRegistry()
    session_id = "sess-brief-ws"
    sessions.add(
        InterpretSessionRecord(
            id=session_id,
            title=sample_docx.name,
            workspace_path=str(workspace_dir),
            source_files=[sample_docx.name],
            status="running",
            created_at="2026-06-25T00:00:00+00:00",
            opened_at="2026-06-25T00:00:00+00:00",
        )
    )
    job_id = "job-brief-ws"
    jobs.create(job_id, session_id, job_kind="brief")

    service = InterpretPipelineService(
        sessions=sessions,
        jobs=jobs,
        llm_client_factory=lambda: BriefFakeLLM(),
    )
    await service.run_brief_on_workspace(
        job_id=job_id,
        session_id=session_id,
        workspace_dir=workspace_dir,
    )
    job = jobs.get(job_id)
    assert job is not None
    assert job.status == "done"
    assert (workspace_dir / "tender_brief.json").exists()
    from tests.helpers.brief_fake_llm import BriefFakeLLM

    monkeypatch.setenv("OCR_ENABLED", "false")
    sessions = InterpretSessionStore(tmp_path / "interpret_sessions.json")
    jobs = InterpretJobRegistry()
    session_id = "sess-brief"
    job_id = "job-brief"
    workspace_dir = tmp_path / "workspaces" / session_id
    workspace_dir.mkdir(parents=True)
    sessions.add(
        InterpretSessionRecord(
            id=session_id,
            title=sample_docx.name,
            workspace_path=str(workspace_dir),
            source_files=[sample_docx.name],
            status="running",
            created_at="2026-06-25T00:00:00+00:00",
            opened_at="2026-06-25T00:00:00+00:00",
        )
    )
    jobs.create(job_id, session_id, job_kind="brief")

    service = InterpretPipelineService(
        sessions=sessions,
        jobs=jobs,
        llm_client_factory=lambda: BriefFakeLLM(),
    )
    await service.run_brief_job(
        job_id=job_id,
        session_id=session_id,
        input_paths=[sample_docx],
        workspace_dir=workspace_dir,
    )
    job = jobs.get(job_id)
    assert job is not None
    assert job.status == "done"
    assert job.job_kind == "brief"
    assert (workspace_dir / "tender_brief.json").exists()
    assert (workspace_dir / "tender_brief.txt").exists()
