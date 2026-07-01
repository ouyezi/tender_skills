from __future__ import annotations

from viewer.config import ViewerSettings
from viewer.models import InterpretSessionRecord, SessionRecord
from viewer.services.interpret_session_store import InterpretSessionStore
from viewer.services.session_store import SessionStore


def _upload_source_files(session_id: str, settings: ViewerSettings) -> list[str]:
    for upload_dir in (
        settings.interpret_uploads_dir / session_id,
        settings.data_dir / "uploads" / session_id,
    ):
        if upload_dir.is_dir():
            files = sorted(f.name for f in upload_dir.iterdir() if f.is_file())
            if files:
                return files
    return []


def viewer_to_interpret(session: SessionRecord, settings: ViewerSettings) -> InterpretSessionRecord:
    source_files = _upload_source_files(session.id, settings)
    if not source_files:
        source_files = [session.title]
    return InterpretSessionRecord(
        id=session.id,
        title=session.title,
        workspace_path=session.workspace_path,
        source_files=source_files,
        status=session.status,
        created_at=session.created_at,
        opened_at=session.opened_at,
        error=session.error,
    )


def interpret_to_viewer(session: InterpretSessionRecord) -> SessionRecord:
    return SessionRecord(
        id=session.id,
        title=session.title,
        workspace_path=session.workspace_path,
        source_type="upload",
        status=session.status,
        created_at=session.created_at,
        opened_at=session.opened_at,
        error=session.error,
    )


def _merge_by_opened_at(
    primary: list,
    secondary: list,
    *,
    max_sessions: int,
) -> list:
    seen: set[str] = set()
    merged = []
    for item in primary + secondary:
        if item.id in seen:
            continue
        seen.add(item.id)
        merged.append(item)
    merged.sort(key=lambda record: record.opened_at, reverse=True)
    return merged[:max_sessions]


def list_merged_viewer_sessions(
    viewer_store: SessionStore,
    interpret_store: InterpretSessionStore,
    settings: ViewerSettings,
) -> list[SessionRecord]:
    viewer_sessions = viewer_store.list_sessions()
    interpret_only = [
        interpret_to_viewer(session)
        for session in interpret_store.list_sessions()
        if viewer_store.get(session.id) is None
    ]
    return _merge_by_opened_at(
        viewer_sessions,
        interpret_only,
        max_sessions=viewer_store._max_sessions,
    )


def list_merged_interpret_sessions(
    viewer_store: SessionStore,
    interpret_store: InterpretSessionStore,
    settings: ViewerSettings,
) -> list[InterpretSessionRecord]:
    interpret_sessions = interpret_store.list_sessions()
    viewer_only = [
        viewer_to_interpret(session, settings)
        for session in viewer_store.list_sessions()
        if interpret_store.get(session.id) is None
    ]
    return _merge_by_opened_at(
        interpret_sessions,
        viewer_only,
        max_sessions=interpret_store._max_sessions,
    )


def mirror_viewer_session(
    record: SessionRecord,
    interpret_store: InterpretSessionStore,
    settings: ViewerSettings,
) -> None:
    interpret_store.add(viewer_to_interpret(record, settings))


def mirror_interpret_session(record: InterpretSessionRecord, viewer_store: SessionStore) -> None:
    viewer_store.add(interpret_to_viewer(record))


def resolve_viewer_session(
    session_id: str,
    *,
    viewer_store: SessionStore,
    interpret_store: InterpretSessionStore,
) -> SessionRecord | None:
    session = viewer_store.get(session_id)
    if session is not None:
        return session
    interpret = interpret_store.get(session_id)
    if interpret is None:
        return None
    session = interpret_to_viewer(interpret)
    viewer_store.add(session)
    return session


def resolve_interpret_session(
    session_id: str,
    *,
    viewer_store: SessionStore,
    interpret_store: InterpretSessionStore,
    settings: ViewerSettings,
) -> InterpretSessionRecord | None:
    session = interpret_store.get(session_id)
    if session is not None:
        return session
    viewer = viewer_store.get(session_id)
    if viewer is None:
        return None
    session = viewer_to_interpret(viewer, settings)
    interpret_store.add(session)
    return session


def sync_session_status(
    session_id: str,
    *,
    viewer_store: SessionStore,
    interpret_store: InterpretSessionStore,
    settings: ViewerSettings,
    **fields: object,
) -> None:
    viewer = viewer_store.get(session_id)
    interpret = interpret_store.get(session_id)

    if viewer is not None:
        viewer_store.update(session_id, **fields)
    if interpret is not None:
        interpret_store.update(session_id, **fields)

    viewer = viewer_store.get(session_id)
    interpret = interpret_store.get(session_id)
    if viewer is not None and interpret is None:
        mirror_viewer_session(viewer, interpret_store, settings)
    elif interpret is not None and viewer is None:
        mirror_interpret_session(interpret, viewer_store)
