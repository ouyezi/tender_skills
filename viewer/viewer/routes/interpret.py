from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from typing import Literal

from doc_chunk.errors import UnsupportedFormatError
from doc_chunk.extract.detect import detect_file_type
from doc_chunk.models.outline import OutlineTree
from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Query, UploadFile

from viewer.deps import (
    get_interpret_job_registry,
    get_interpret_pipeline_service,
    get_interpret_session_store,
    get_job_registry,
    get_session_store,
    get_settings,
)
from viewer.models import (
    InterpretResultResponse,
    InterpretSessionRecord,
    InterpretUploadResponse,
)
from viewer.services.outline_tree import build_outline_response
from viewer.services.interpret_inputs import resolve_interpret_input_paths
from viewer.services.section_slice import slice_section
from viewer.services.session_cleanup import delete_session_fully
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


def _workspace_is_ready(workspace_dir: Path) -> bool:
    try:
        validate_workspace(workspace_dir)
    except (ValueError, OSError):
        return False
    else:
        return True


def _mark_session_running(session_id: str) -> None:
    get_interpret_session_store().update(
        session_id,
        status="running",
        error=None,
        opened_at=datetime.now(UTC).isoformat(),
    )


def _start_session_brief_job(session_id: str, background_tasks: BackgroundTasks) -> InterpretUploadResponse:
    settings = get_settings()
    session = _get_session_or_404(session_id)
    _ensure_session_idle(session)
    workspace_dir = Path(session.workspace_path)
    dual_file = len(session.source_files) > 1
    job_id = str(uuid.uuid4())
    _mark_session_running(session_id)
    get_interpret_job_registry().create(job_id, session_id, dual_file=dual_file, job_kind="brief")
    service = get_interpret_pipeline_service()
    if _workspace_is_ready(workspace_dir):
        background_tasks.add_task(
            service.run_brief_on_workspace,
            job_id=job_id,
            session_id=session_id,
            workspace_dir=workspace_dir,
            dual_file=dual_file,
        )
    else:
        try:
            input_paths = resolve_interpret_input_paths(session, settings)
        except FileNotFoundError as exc:
            get_interpret_session_store().update(session_id, status="failed", error=str(exc))
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        background_tasks.add_task(
            service.run_brief_job,
            job_id=job_id,
            session_id=session_id,
            input_paths=input_paths,
            workspace_dir=workspace_dir,
        )
    return InterpretUploadResponse(session_id=session_id, job_id=job_id)


def _start_session_interpret_job(session_id: str, background_tasks: BackgroundTasks) -> InterpretUploadResponse:
    settings = get_settings()
    session = _get_session_or_404(session_id)
    _ensure_session_idle(session)
    workspace_dir = Path(session.workspace_path)
    dual_file = len(session.source_files) > 1
    job_id = str(uuid.uuid4())
    _mark_session_running(session_id)
    get_interpret_job_registry().create(job_id, session_id, dual_file=dual_file, job_kind="interpret")
    service = get_interpret_pipeline_service()
    if _workspace_is_ready(workspace_dir):
        background_tasks.add_task(
            service.run_interpret_on_workspace,
            job_id=job_id,
            session_id=session_id,
            workspace_dir=workspace_dir,
            dual_file=dual_file,
        )
    else:
        try:
            input_paths = resolve_interpret_input_paths(session, settings)
        except FileNotFoundError as exc:
            get_interpret_session_store().update(session_id, status="failed", error=str(exc))
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        background_tasks.add_task(
            service.run_job,
            job_id=job_id,
            session_id=session_id,
            input_paths=input_paths,
            workspace_dir=workspace_dir,
        )
    return InterpretUploadResponse(session_id=session_id, job_id=job_id)


def _start_session_template_job(session_id: str, background_tasks: BackgroundTasks) -> InterpretUploadResponse:
    settings = get_settings()
    session = _get_session_or_404(session_id)
    _ensure_session_idle(session)
    workspace_dir = Path(session.workspace_path)
    dual_file = len(session.source_files) > 1
    job_id = str(uuid.uuid4())
    _mark_session_running(session_id)
    get_interpret_job_registry().create(job_id, session_id, dual_file=dual_file, job_kind="template")
    service = get_interpret_pipeline_service()
    if _workspace_is_ready(workspace_dir):
        background_tasks.add_task(
            service.run_template_on_workspace,
            job_id=job_id,
            session_id=session_id,
            workspace_dir=workspace_dir,
            dual_file=dual_file,
        )
    else:
        try:
            input_paths = resolve_interpret_input_paths(session, settings)
        except FileNotFoundError as exc:
            get_interpret_session_store().update(session_id, status="failed", error=str(exc))
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        background_tasks.add_task(
            service.run_template_job,
            job_id=job_id,
            session_id=session_id,
            input_paths=input_paths,
            workspace_dir=workspace_dir,
        )
    return InterpretUploadResponse(session_id=session_id, job_id=job_id)


async def _enqueue_upload_job(
    background_tasks: BackgroundTasks,
    *,
    file1: UploadFile,
    file2: UploadFile | None,
    job_kind: Literal["interpret", "brief", "template"],
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
    get_interpret_job_registry().create(
        job_id,
        session_id,
        dual_file=len(input_paths) > 1,
        job_kind=job_kind,
    )

    service = get_interpret_pipeline_service()
    if job_kind == "brief":
        background_tasks.add_task(
            service.run_brief_job,
            job_id=job_id,
            session_id=session_id,
            input_paths=input_paths,
            workspace_dir=workspace_dir,
        )
    elif job_kind == "template":
        background_tasks.add_task(
            service.run_template_job,
            job_id=job_id,
            session_id=session_id,
            input_paths=input_paths,
            workspace_dir=workspace_dir,
        )
    else:
        background_tasks.add_task(
            service.run_job,
            job_id=job_id,
            session_id=session_id,
            input_paths=input_paths,
            workspace_dir=workspace_dir,
        )
    return InterpretUploadResponse(session_id=session_id, job_id=job_id)


@router.post("/upload", response_model=InterpretUploadResponse)
async def upload_interpret(
    background_tasks: BackgroundTasks,
    file1: UploadFile = File(...),
    file2: UploadFile | None = File(None),
    job_kind: Literal["interpret", "brief", "template"] = Query(default="interpret"),
) -> InterpretUploadResponse:
    return await _enqueue_upload_job(background_tasks, file1=file1, file2=file2, job_kind=job_kind)


@router.post("/brief-upload", response_model=InterpretUploadResponse)
async def upload_brief(
    background_tasks: BackgroundTasks,
    file1: UploadFile = File(...),
    file2: UploadFile | None = File(None),
) -> InterpretUploadResponse:
    """兼容旧路径；与 ``POST /upload?job_kind=brief`` 等价。"""
    return await _enqueue_upload_job(background_tasks, file1=file1, file2=file2, job_kind="brief")


@router.post("/sessions/{session_id}/brief", response_model=InterpretUploadResponse)
def run_brief_on_session(session_id: str, background_tasks: BackgroundTasks) -> InterpretUploadResponse:
    """对已选会话重跑概要：工作区就绪则跳过 pipeline，否则从已上传原文件重建。"""
    return _start_session_brief_job(session_id, background_tasks)


@router.post("/sessions/{session_id}/template", response_model=InterpretUploadResponse)
def run_template_on_session(session_id: str, background_tasks: BackgroundTasks) -> InterpretUploadResponse:
    """对已选会话重跑模版提取：工作区就绪则跳过 pipeline，否则从已上传原文件重建。"""
    return _start_session_template_job(session_id, background_tasks)


@router.post("/sessions/{session_id}/run", response_model=InterpretUploadResponse)
def run_interpret_on_session(session_id: str, background_tasks: BackgroundTasks) -> InterpretUploadResponse:
    """对已选会话重跑解读：工作区就绪则跳过 pipeline，否则从已上传原文件重建。"""
    return _start_session_interpret_job(session_id, background_tasks)


@router.get("/jobs/{job_id}")
def get_interpret_job(job_id: str) -> dict:
    job = get_interpret_job_registry().get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job.model_dump()


@router.get("/sessions/{session_id}/job")
def get_interpret_session_job(session_id: str) -> dict:
    session = get_interpret_session_store().get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    job = get_interpret_job_registry().get_latest_for_session(session_id)
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


@router.delete("/sessions/{session_id}")
def delete_interpret_session(session_id: str) -> dict:
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


def _read_llm_calls(workspace: Path) -> list[dict]:
    path = workspace / "llm_calls.jsonl"
    if not path.exists():
        return []
    merged: dict[str, dict] = {}
    attempts: dict[str, list[dict]] = {}
    order: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        record = json.loads(stripped)
        key = record.get("segment_id") or record.get("call_type") or f"call-{len(order)}"
        event = record.get("event")
        if event == "response":
            if key in merged:
                merged[key]["response"] = record.get("response")
            continue
        if event == "attempt":
            attempts.setdefault(key, []).append(record)
            continue
        if key not in merged:
            order.append(key)
        merged[key] = record
    for key in order:
        if key in attempts:
            merged[key]["attempts"] = attempts[key]
    return [merged[key] for key in order]


@router.get("/sessions/{session_id}/llm-calls")
def get_interpret_llm_calls(session_id: str) -> list[dict]:
    session = get_interpret_session_store().get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    workspace = Path(session.workspace_path)
    if not workspace.is_dir():
        return []
    return _read_llm_calls(workspace)


@router.get("/sessions/{session_id}/brief")
def get_interpret_brief(session_id: str) -> dict:
    session = get_interpret_session_store().get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    brief_path = Path(session.workspace_path) / "tender_brief.json"
    if not brief_path.exists():
        raise HTTPException(status_code=404, detail="tender brief not found")
    return json.loads(brief_path.read_text(encoding="utf-8"))


@router.get("/sessions/{session_id}/result", response_model=InterpretResultResponse)
def get_interpret_result(session_id: str) -> InterpretResultResponse:
    session = get_interpret_session_store().get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    workspace = Path(session.workspace_path)
    interpretation_path = workspace / "interpretation.json"
    templates_path = workspace / "templates" / "index.json"
    has_interpretation = interpretation_path.is_file()
    has_templates = templates_path.is_file()
    if not has_interpretation and not has_templates:
        raise HTTPException(status_code=404, detail="interpretation not found")
    interpretation: dict = {}
    if has_interpretation:
        interpretation = json.loads(interpretation_path.read_text(encoding="utf-8"))
    templates: dict = {}
    if has_templates:
        templates = json.loads(templates_path.read_text(encoding="utf-8"))
    return InterpretResultResponse(
        interpretation=interpretation,
        templates=templates,
        source_files=session.source_files,
    )


@router.get("/sessions/{session_id}/templates/{template_id}")
def get_interpret_template(session_id: str, template_id: str) -> dict:
    session = get_interpret_session_store().get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    workspace = Path(session.workspace_path).resolve()
    index_path = workspace / "templates" / "index.json"
    if not index_path.is_file():
        raise HTTPException(status_code=404, detail="templates not found")
    index = json.loads(index_path.read_text(encoding="utf-8"))
    entry = next((t for t in index.get("templates", []) if t.get("id") == template_id), None)
    if entry is None:
        raise HTTPException(status_code=404, detail="template not found")
    rel_file = entry.get("file")
    if not rel_file or not isinstance(rel_file, str):
        raise HTTPException(status_code=404, detail="template file missing")
    file_path = (workspace / rel_file).resolve()
    if not str(file_path).startswith(str(workspace)):
        raise HTTPException(status_code=400, detail="invalid template path")
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="template file not found")
    return {
        "id": template_id,
        "title": entry.get("title", ""),
        "type_label": entry.get("type_label", ""),
        "file": rel_file,
        "markdown": file_path.read_text(encoding="utf-8"),
    }


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
