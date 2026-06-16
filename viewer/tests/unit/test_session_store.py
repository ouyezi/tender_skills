from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from viewer.models import SessionRecord
from viewer.services.session_store import SessionStore


def _record(session_id: str, *, title: str = "demo") -> SessionRecord:
    now = datetime.now(UTC).isoformat()
    return SessionRecord(
        id=session_id,
        title=title,
        workspace_path="/tmp/ws",
        source_type="upload",
        status="success",
        created_at=now,
        opened_at=now,
        error=None,
    )


def test_session_store_persists_and_lists(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "sessions.json", max_sessions=20)
    store.add(_record("s1", title="first"))
    store.add(_record("s2", title="second"))

    sessions = store.list_sessions()
    assert [s.id for s in sessions] == ["s2", "s1"]


def test_session_store_trims_to_max(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "sessions.json", max_sessions=2)
    store.add(_record("s1"))
    store.add(_record("s2"))
    store.add(_record("s3"))

    assert [s.id for s in store.list_sessions()] == ["s3", "s2"]
