from __future__ import annotations

from viewer.models import InterpretSessionRecord
from viewer.services.interpret_session_store import InterpretSessionStore


def test_add_and_list_interpret_sessions(tmp_path) -> None:
    store = InterpretSessionStore(tmp_path / "interpret_sessions.json", max_sessions=20)
    record = InterpretSessionRecord(
        id="s1",
        title="bid.docx",
        workspace_path=str(tmp_path / "ws"),
        source_files=["bid.docx"],
        status="pending",
        created_at="2026-06-24T00:00:00+00:00",
        opened_at="2026-06-24T00:00:00+00:00",
        error=None,
    )
    store.add(record)
    sessions = store.list_sessions()
    assert len(sessions) == 1
    assert sessions[0].source_files == ["bid.docx"]
