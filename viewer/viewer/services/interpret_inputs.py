from __future__ import annotations

from pathlib import Path

from viewer.config import ViewerSettings
from viewer.models import InterpretSessionRecord


def resolve_interpret_input_paths(session: InterpretSessionRecord, settings: ViewerSettings) -> list[Path]:
    for upload_dir in (
        settings.interpret_uploads_dir / session.id,
        settings.data_dir / "uploads" / session.id,
    ):
        if upload_dir.is_dir():
            files = sorted(f for f in upload_dir.iterdir() if f.is_file())
            if files:
                return [path.resolve() for path in files]
    raise FileNotFoundError(f"no uploaded source files for interpret session {session.id}")
