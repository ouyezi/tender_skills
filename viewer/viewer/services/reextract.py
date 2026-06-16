from __future__ import annotations

import json
from pathlib import Path

from viewer.config import ViewerSettings
from viewer.models import SessionRecord


def resolve_reextract_input(session: SessionRecord, settings: ViewerSettings) -> Path:
    upload_dir = settings.data_dir / "uploads" / session.id
    if upload_dir.is_dir():
        files = sorted(f for f in upload_dir.iterdir() if f.is_file())
        if files:
            return files[0].resolve()

    workspace = Path(session.workspace_path)
    manifest_path = workspace / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        source_path = manifest.get("source", {}).get("path")
        if source_path:
            path = Path(source_path).expanduser().resolve()
            if path.is_file():
                return path

    raise FileNotFoundError("no source file available for re-extract")
