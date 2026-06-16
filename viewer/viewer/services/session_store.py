from __future__ import annotations

import json
from pathlib import Path

from viewer.models import SessionRecord


class SessionStore:
    def __init__(self, path: Path, *, max_sessions: int = 20) -> None:
        self._path = path
        self._max_sessions = max_sessions

    def _load(self) -> list[SessionRecord]:
        if not self._path.exists():
            return []
        data = json.loads(self._path.read_text(encoding="utf-8"))
        return [SessionRecord.model_validate(item) for item in data]

    def _save(self, sessions: list[SessionRecord]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = [s.model_dump() for s in sessions[: self._max_sessions]]
        self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def list_sessions(self) -> list[SessionRecord]:
        return self._load()

    def get(self, session_id: str) -> SessionRecord | None:
        return next((s for s in self._load() if s.id == session_id), None)

    def add(self, record: SessionRecord) -> SessionRecord:
        sessions = [r for r in self._load() if r.id != record.id]
        sessions.insert(0, record)
        self._save(sessions)
        return record

    def update(self, session_id: str, **fields: object) -> SessionRecord:
        sessions = self._load()
        updated: SessionRecord | None = None
        for idx, session in enumerate(sessions):
            if session.id == session_id:
                updated = session.model_copy(update=fields)
                sessions[idx] = updated
                break
        if updated is None:
            raise KeyError(session_id)
        self._save(sessions)
        return updated

    def delete(self, session_id: str) -> bool:
        sessions = self._load()
        kept = [s for s in sessions if s.id != session_id]
        if len(kept) == len(sessions):
            return False
        self._save(kept)
        return True
