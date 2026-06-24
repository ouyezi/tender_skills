from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from doc_chunk.errors import UnsupportedFormatError
from doc_chunk.extract.detect import detect_file_type
from doc_chunk.models.outline import OutlineTree
from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile

from viewer.deps import (
    get_interpret_job_registry,
    get_interpret_pipeline_service,
    get_interpret_session_store,
    get_settings,
)
from viewer.models import (
    InterpretResultResponse,
    InterpretSessionRecord,
    InterpretUploadResponse,
)
from viewer.services.outline_tree import build_outline_response
from viewer.services.section_slice import slice_section
from viewer.services.workspace import validate_workspace

router = APIRouter(prefix="/interpret", tags=["interpret"])

_ALLOWED = {"docx", "pdf"}


async def _save_upload(upload: UploadFile, dest: Path) -> None:
    if not upload.filename:
        raise HTTPException(status_code=400, detail="filename is required")
    content = await upload.read()
    dest.write_bytes(content)
    try:
        file_type = detect_file_type(dest)
    except UnsupportedFormatError as exc:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if file_type not in _ALLOWED:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"unsupported file type: {file_type}")


def _load_interpret_workspace(session_id: str) -> Path:
    session = get_interpret_session_store().get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return validate_workspace(Path(session.workspace_path))


@router.post("/upload", response_model=InterpretUploadResponse)
async def upload_interpret(
    background_tasks: BackgroundTasks,
    file1: UploadFile = File(...),
    file2: UploadFile | None = File(None),
) -> InterpretUploadResponse:
    settings = get_settings()
    session_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    upload_dir = settings.interpret_uploads_dir / session_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    workspace_dir = settings.workspaces_dir / session_id

    dest1 = upload_dir / (file1.filename or "file1")
    await _save_upload(file1, dest1)

    source_files = [dest1.name]
    input_paths = [dest1]
    if file2 and file2.filename:
        dest2 = upload_dir / file2.filename
        await _save_upload(file2, dest2)
        source_files.append(dest2.name)
        input_paths.append(dest2)

    now = datetime.now(UTC).isoformat()
    record = InterpretSessionRecord(
        id=session_id,
        title=dest1.name,
        workspace_path=str(workspace_dir),
        source_files=source_files,
        status="running",
        created_at=now,
        opened_at=now,
        error=None,
    )
    get_interpret_session_store().add(record)
    get_interpret_job_registry().create(job_id, session_id)

    service = get_interpret_pipeline_service()
    background_tasks.add_task(
        service.run_job,
        job_id=job_id,
        session_id=session_id,
        input_paths=input_paths,
        workspace_dir=workspace_dir,
    )
    return InterpretUploadResponse(session_id=session_id, job_id=job_id)


@router.get("/jobs/{job_id}")
def get_interpret_job(job_id: str) -> dict:
    job = get_interpret_job_registry().get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job.model_dump()


@router.get("/sessions")
def list_interpret_sessions() -> list[dict]:
    return [s.model_dump() for s in get_interpret_session_store().list_sessions()]


@router.get("/sessions/{session_id}")
def get_interpret_session(session_id: str) -> dict:
    session = get_interpret_session_store().get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return session.model_dump()


@router.get("/sessions/{session_id}/result", response_model=InterpretResultResponse)
def get_interpret_result(session_id: str) -> InterpretResultResponse:
    session = get_interpret_session_store().get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    workspace = Path(session.workspace_path)
    interpretation_path = workspace / "interpretation.json"
    templates_path = workspace / "templates" / "index.json"
    if not interpretation_path.exists():
        raise HTTPException(status_code=404, detail="interpretation not found")
    interpretation = json.loads(interpretation_path.read_text(encoding="utf-8"))
    templates: dict = {}
    if templates_path.exists():
        templates = json.loads(templates_path.read_text(encoding="utf-8"))
    return InterpretResultResponse(
        interpretation=interpretation,
        templates=templates,
        source_files=session.source_files,
    )


@router.get("/sessions/{session_id}/outline")
def get_interpret_outline(session_id: str) -> dict:
    workspace = _load_interpret_workspace(session_id)
    outline = OutlineTree.model_validate_json((workspace / "outline.json").read_text(encoding="utf-8"))
    content_md = (workspace / "content.md").read_text(encoding="utf-8")
    return build_outline_response(outline, content_md).model_dump()


@router.get("/sessions/{session_id}/sections/{node_id}")
def get_interpret_section(session_id: str, node_id: str) -> dict:
    workspace = _load_interpret_workspace(session_id)
    outline = OutlineTree.model_validate_json((workspace / "outline.json").read_text(encoding="utf-8"))
    content_md = (workspace / "content.md").read_text(encoding="utf-8")
    try:
        return slice_section(content_md, outline, node_id).model_dump()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="outline node not found") from exc
