from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from doc_chunk.errors import UnsupportedFormatError
from doc_chunk.extract.detect import detect_file_type
from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile

from viewer.deps import get_job_registry, get_pipeline_service, get_session_store, get_settings
from viewer.models import SessionRecord, UploadResponse

router = APIRouter(tags=["upload"])

_ALLOWED = {"docx", "pdf"}


@router.post("/upload", response_model=UploadResponse)
async def upload_file(background_tasks: BackgroundTasks, file: UploadFile) -> UploadResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="filename is required")

    settings = get_settings()
    session_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    upload_dir = settings.data_dir / "uploads" / session_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    workspace_dir = settings.workspaces_dir / session_id

    dest = upload_dir / file.filename
    content = await file.read()
    dest.write_bytes(content)

    try:
        file_type = detect_file_type(dest)
    except UnsupportedFormatError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if file_type not in _ALLOWED:
        raise HTTPException(status_code=400, detail=f"unsupported file type: {file_type}")

    now = datetime.now(UTC).isoformat()
    record = SessionRecord(
        id=session_id,
        title=file.filename,
        workspace_path=str(workspace_dir),
        source_type="upload",
        status="running",
        created_at=now,
        opened_at=now,
        error=None,
    )
    get_session_store().add(record)
    get_job_registry().create(job_id, session_id)

    service = get_pipeline_service()
    background_tasks.add_task(
        service.run_upload_job,
        job_id=job_id,
        session_id=session_id,
        input_path=dest,
        workspace_dir=workspace_dir,
    )
    return UploadResponse(session_id=session_id, job_id=job_id)
