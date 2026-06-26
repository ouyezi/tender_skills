from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from viewer.deps import (
    get_gen_catalog_pipeline_service,
    get_interpret_job_registry,
    get_interpret_session_store,
)
from viewer.models import InterpretSessionRecord, InterpretUploadResponse
from viewer.routes.interpret import _read_llm_calls

router = APIRouter(prefix="/gen-catalog", tags=["gen-catalog"])


def _get_session_or_404(session_id: str) -> InterpretSessionRecord:
    session = get_interpret_session_store().get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return session


def _ensure_session_idle(session: InterpretSessionRecord) -> None:
    if session.status == "running":
        raise HTTPException(status_code=409, detail="session is running")
    latest = get_interpret_job_registry().get_latest_for_session(session.id)
    if latest is not None and latest.status == "running":
        raise HTTPException(status_code=409, detail="session has a running job")


def _require_interpretation(workspace: Path) -> None:
    if not (workspace / "interpretation.json").is_file():
        raise HTTPException(status_code=400, detail="interpretation.json not found; run interpret first")


@router.post("/sessions/{session_id}/start", response_model=InterpretUploadResponse)
def start_gen_catalog(
    session_id: str,
    background_tasks: BackgroundTasks,
    mode: Literal["auto", "step"] = Query("step"),
    restart: bool = Query(False),
) -> InterpretUploadResponse:
    session = _get_session_or_404(session_id)
    _ensure_session_idle(session)
    workspace = Path(session.workspace_path)
    _require_interpretation(workspace)
    job_id = str(uuid.uuid4())
    get_interpret_session_store().update(session_id, status="running", error=None)
    get_interpret_job_registry().create(
        job_id,
        session_id,
        dual_file=len(session.source_files) > 1,
        job_kind="gen_catalog",
    )
    service = get_gen_catalog_pipeline_service()
    background_tasks.add_task(
        service.run_gen_catalog,
        job_id=job_id,
        session_id=session_id,
        workspace_dir=workspace,
        mode=mode,
        restart=restart,
        dual_file=len(session.source_files) > 1,
    )
    return InterpretUploadResponse(session_id=session_id, job_id=job_id)


@router.post("/sessions/{session_id}/continue", response_model=InterpretUploadResponse)
def continue_gen_catalog_session(session_id: str, background_tasks: BackgroundTasks) -> InterpretUploadResponse:
    session = _get_session_or_404(session_id)
    _ensure_session_idle(session)
    workspace = Path(session.workspace_path)
    _require_interpretation(workspace)
    job_id = str(uuid.uuid4())
    get_interpret_session_store().update(session_id, status="running", error=None)
    get_interpret_job_registry().create(
        job_id,
        session_id,
        dual_file=len(session.source_files) > 1,
        job_kind="gen_catalog",
    )
    service = get_gen_catalog_pipeline_service()
    background_tasks.add_task(
        service.run_gen_catalog,
        job_id=job_id,
        session_id=session_id,
        workspace_dir=workspace,
        mode="step",
        continue_from_session=True,
        dual_file=len(session.source_files) > 1,
    )
    return InterpretUploadResponse(session_id=session_id, job_id=job_id)


@router.post("/sessions/{session_id}/accept", response_model=InterpretUploadResponse)
def accept_gen_catalog_session(session_id: str, background_tasks: BackgroundTasks) -> InterpretUploadResponse:
    session = _get_session_or_404(session_id)
    _ensure_session_idle(session)
    workspace = Path(session.workspace_path)
    job_id = str(uuid.uuid4())
    get_interpret_session_store().update(session_id, status="running", error=None)
    get_interpret_job_registry().create(
        job_id,
        session_id,
        dual_file=len(session.source_files) > 1,
        job_kind="gen_catalog",
    )
    service = get_gen_catalog_pipeline_service()
    background_tasks.add_task(
        service.run_accept,
        job_id=job_id,
        session_id=session_id,
        workspace_dir=workspace,
        dual_file=len(session.source_files) > 1,
    )
    return InterpretUploadResponse(session_id=session_id, job_id=job_id)


@router.get("/jobs/{job_id}")
def get_gen_catalog_job(job_id: str) -> dict:
    job = get_interpret_job_registry().get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job.model_dump()


@router.get("/sessions/{session_id}/draft")
def get_gen_catalog_draft(session_id: str) -> dict:
    session = _get_session_or_404(session_id)
    draft_path = Path(session.workspace_path) / "bid_outline.draft.json"
    if not draft_path.is_file():
        raise HTTPException(status_code=404, detail="bid_outline.draft.json not found")
    return json.loads(draft_path.read_text(encoding="utf-8"))


@router.get("/sessions/{session_id}/prerequisites")
def get_gen_catalog_prerequisites(session_id: str) -> dict:
    session = _get_session_or_404(session_id)
    workspace = Path(session.workspace_path)
    warnings: list[str] = []
    if not (workspace / "interpretation.json").is_file():
        raise HTTPException(status_code=400, detail="interpretation.json not found")
    if not (workspace / "tender_brief.json").is_file():
        warnings.append("tender_brief.json missing")
    if not (workspace / "templates" / "index.json").is_file():
        warnings.append("templates/index.json missing")
    return {"warnings": warnings}


@router.get("/sessions/{session_id}/llm-calls")
def get_gen_catalog_llm_calls(session_id: str) -> list[dict]:
    session = _get_session_or_404(session_id)
    workspace = Path(session.workspace_path)
    if not workspace.is_dir():
        return []
    calls = _read_llm_calls(workspace)
    return [c for c in calls if str(c.get("call_type", "")).startswith("gen_catalog")]


@router.get("/sessions/{session_id}/status")
def get_gen_catalog_status(session_id: str) -> dict:
    from tender_insights.gen_catalog.models import BidOutlineNode
    from tender_insights.gen_catalog.queue import find_node, next_pending_node_id

    session = _get_session_or_404(session_id)
    workspace = Path(session.workspace_path)
    session_path = workspace / "gen_catalog" / "session.json"
    draft_path = workspace / "bid_outline.draft.json"
    if not session_path.is_file():
        return {"has_session": False, "has_draft": draft_path.is_file()}
    data = json.loads(session_path.read_text(encoding="utf-8"))
    pending_id = next_pending_node_id(data.get("node_queue", []), data.get("completed_steps", []))
    next_title: str | None = None
    if pending_id and draft_path.is_file():
        draft = json.loads(draft_path.read_text(encoding="utf-8"))
        root = BidOutlineNode.model_validate(draft["root"])
        node = find_node(root, pending_id)
        if node is not None:
            next_title = node.title
    return {
        "has_session": True,
        "has_draft": draft_path.is_file(),
        "mode": data.get("mode"),
        "status": data.get("status"),
        "step_index": data.get("step_index", 0),
        "step_total": data.get("step_total", 0),
        "refine_chapters": len(data.get("node_queue", [])),
        "completed_steps": data.get("completed_steps", []),
        "next_node_id": pending_id,
        "next_node_title": next_title,
        "current_node_title": data.get("current_node_title"),
    }
