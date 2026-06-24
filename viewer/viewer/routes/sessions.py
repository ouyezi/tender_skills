from __future__ import annotations

from datetime import UTC, datetime
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException

from viewer.deps import (
    get_interpret_job_registry,
    get_interpret_session_store,
    get_job_registry,
    get_pipeline_service,
    get_session_store,
    get_settings,
)
from viewer.models import UploadResponse
from viewer.services.reextract import resolve_reextract_input
from viewer.services.session_cleanup import delete_session_fully

router = APIRouter(tags=["sessions"])


@router.get("/sessions")
def list_sessions() -> list[dict]:
    return [s.model_dump() for s in get_session_store().list_sessions()]


@router.get("/sessions/{session_id}")
def get_session(session_id: str) -> dict:
    session = get_session_store().get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return session.model_dump()


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str) -> dict:
    settings = get_settings()
    deleted = delete_session_fully(
        session_id,
        settings=settings,
        session_store=get_session_store(),
        interpret_store=get_interpret_session_store(),
        job_registry=get_job_registry(),
        interpret_job_registry=get_interpret_job_registry(),
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="session not found")
    return {"deleted": True}


@router.post("/sessions/{session_id}/reextract", response_model=UploadResponse)
def reextract_session(session_id: str, background_tasks: BackgroundTasks) -> UploadResponse:
    store = get_session_store()
    session = store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")

    settings = get_settings()
    try:
        input_path = resolve_reextract_input(session, settings)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job_id = str(uuid.uuid4())
    workspace_dir = Path(session.workspace_path)
    store.update(session_id, status="running", error=None, opened_at=datetime.now(UTC).isoformat())
    get_job_registry().create(job_id, session_id)

    background_tasks.add_task(
        get_pipeline_service().run_upload_job,
        job_id=job_id,
        session_id=session_id,
        input_path=input_path,
        workspace_dir=workspace_dir,
    )
    return UploadResponse(session_id=session_id, job_id=job_id)
