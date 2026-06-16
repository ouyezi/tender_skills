from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from doc_chunk.models.outline import OutlineTree

from viewer.deps import get_session_store
from viewer.services.outline_tree import build_outline_response
from viewer.services.section_slice import slice_section
from viewer.services.workspace import validate_workspace

router = APIRouter(tags=["content"])


def _load_workspace(session_id: str) -> Path:
    session = get_session_store().get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return validate_workspace(Path(session.workspace_path))


@router.get("/sessions/{session_id}/outline")
def get_outline(session_id: str) -> dict:
    workspace = _load_workspace(session_id)
    outline = OutlineTree.model_validate_json((workspace / "outline.json").read_text(encoding="utf-8"))
    content_md = (workspace / "content.md").read_text(encoding="utf-8")
    return build_outline_response(outline, content_md).model_dump()


@router.get("/sessions/{session_id}/sections/{node_id}")
def get_section(session_id: str, node_id: str) -> dict:
    workspace = _load_workspace(session_id)
    outline = OutlineTree.model_validate_json((workspace / "outline.json").read_text(encoding="utf-8"))
    content_md = (workspace / "content.md").read_text(encoding="utf-8")
    try:
        return slice_section(content_md, outline, node_id).model_dump()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="outline node not found") from exc


@router.get("/sessions/{session_id}/assets/{asset_path:path}")
def get_asset(session_id: str, asset_path: str) -> FileResponse:
    workspace = _load_workspace(session_id)
    target = (workspace / asset_path).resolve()
    if not str(target).startswith(str(workspace.resolve())):
        raise HTTPException(status_code=400, detail="invalid asset path")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="asset not found")
    return FileResponse(target)
