from __future__ import annotations

from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from doc_chunk.convert.table_export import export_table_ref_to_docx_bytes
from doc_chunk.media.assets import collect_document_assets
from doc_chunk.media.models import DocumentAssetEntry
from doc_chunk.models.outline import OutlineTree

from viewer.deps import get_interpret_session_store, get_session_store
from viewer.models import DocumentAssetItemResponse, DocumentAssetsResponse
from viewer.services.asset_navigation import resolve_outline_node_for_char
from viewer.services.outline_tree import build_outline_response
from viewer.services.section_slice import slice_section
from viewer.services.session_sync import resolve_viewer_session
from viewer.services.workspace import validate_workspace

router = APIRouter(tags=["content"])


def _load_workspace(session_id: str) -> Path:
    session = resolve_viewer_session(
        session_id,
        viewer_store=get_session_store(),
        interpret_store=get_interpret_session_store(),
    )
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return validate_workspace(Path(session.workspace_path))


def _enrich_assets(workspace: Path) -> DocumentAssetsResponse:
    content_md = (workspace / "content.md").read_text(encoding="utf-8")
    outline = OutlineTree.model_validate_json((workspace / "outline.json").read_text(encoding="utf-8"))
    doc_assets = collect_document_assets(workspace)

    def enrich(entry: DocumentAssetEntry) -> DocumentAssetItemResponse:
        outline_node_id = None
        if entry.char_start is not None:
            outline_node_id = resolve_outline_node_for_char(entry.char_start, content_md, outline)
        return DocumentAssetItemResponse(
            asset_type=entry.asset_type,
            ref=entry.ref,
            source_block_index=entry.source_block_index,
            char_start=entry.char_start,
            char_end=entry.char_end,
            preview=entry.preview,
            outline_node_id=outline_node_id,
            meta=entry.meta,
        )

    return DocumentAssetsResponse(
        images=[enrich(entry) for entry in doc_assets.images],
        tables=[enrich(entry) for entry in doc_assets.tables],
    )


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


@router.get("/sessions/{session_id}/document-assets")
def get_document_assets(session_id: str) -> dict:
    workspace = _load_workspace(session_id)
    return _enrich_assets(workspace).model_dump()


@router.get("/sessions/{session_id}/tables/{table_ref:path}/export.docx")
def export_table_docx(session_id: str, table_ref: str) -> StreamingResponse:
    workspace = _load_workspace(session_id)
    if not table_ref.startswith("tables/"):
        raise HTTPException(status_code=400, detail="invalid table_ref")
    try:
        data = export_table_ref_to_docx_bytes(workspace, table_ref)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="table sidecar not found") from exc
    filename = Path(table_ref).stem + ".docx"
    return StreamingResponse(
        BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/sessions/{session_id}/assets/{asset_path:path}")
def get_asset(session_id: str, asset_path: str) -> FileResponse:
    workspace = _load_workspace(session_id)
    target = (workspace / asset_path).resolve()
    if not str(target).startswith(str(workspace.resolve())):
        raise HTTPException(status_code=400, detail="invalid asset path")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="asset not found")
    return FileResponse(target)
