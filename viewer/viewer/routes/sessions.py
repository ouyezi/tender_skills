from __future__ import annotations

from fastapi import APIRouter, HTTPException

from viewer.deps import get_session_store

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
    deleted = get_session_store().delete(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="session not found")
    return {"deleted": True}
