from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException

from viewer.deps import get_interpret_session_store, get_session_store, get_settings
from viewer.models import OpenWorkspaceRequest, SessionRecord
from viewer.services.session_sync import mirror_viewer_session
from viewer.services.workspace import validate_workspace

router = APIRouter(tags=["workspaces"])


@router.post("/workspaces/open")
def open_workspace(body: OpenWorkspaceRequest) -> dict:
    try:
        workspace = validate_workspace(Path(body.path))
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    now = datetime.now(UTC).isoformat()
    session_id = str(uuid.uuid4())
    record = SessionRecord(
        id=session_id,
        title=workspace.name,
        workspace_path=str(workspace),
        source_type="open",
        status="success",
        created_at=now,
        opened_at=now,
        error=None,
    )
    get_session_store().add(record)
    mirror_viewer_session(record, get_interpret_session_store(), get_settings())
    return {"session_id": session_id, "status": "success"}
