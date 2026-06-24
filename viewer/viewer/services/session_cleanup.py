from __future__ import annotations

import shutil
from pathlib import Path

from viewer.config import ViewerSettings
from viewer.services.interpret_job_registry import InterpretJobRegistry
from viewer.services.interpret_session_store import InterpretSessionStore
from viewer.services.job_registry import JobRegistry
from viewer.services.session_store import SessionStore


def _remove_tree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def delete_session_fully(
    session_id: str,
    *,
    settings: ViewerSettings,
    session_store: SessionStore,
    interpret_store: InterpretSessionStore,
    job_registry: JobRegistry,
    interpret_job_registry: InterpretJobRegistry,
) -> bool:
    """Remove session records and all on-disk artifacts for *session_id*."""
    viewer_session = session_store.get(session_id)
    interpret_session = interpret_store.get(session_id)
    if viewer_session is None and interpret_session is None:
        return False

    workspace_paths: set[Path] = set()
    if viewer_session is not None:
        workspace_paths.add(Path(viewer_session.workspace_path))
    if interpret_session is not None:
        workspace_paths.add(Path(interpret_session.workspace_path))

    for workspace in workspace_paths:
        _remove_tree(workspace)

    _remove_tree(settings.data_dir / "uploads" / session_id)
    _remove_tree(settings.interpret_uploads_dir / session_id)

    if viewer_session is not None:
        session_store.delete(session_id)
    if interpret_session is not None:
        interpret_store.delete(session_id)

    job_registry.remove_for_session(session_id)
    interpret_job_registry.remove_for_session(session_id)
    return True
