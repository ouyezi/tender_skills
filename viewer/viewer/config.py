from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ViewerSettings:
    data_dir: Path
    host: str = "127.0.0.1"
    port: int = 8765
    max_sessions: int = 20

    @property
    def workspaces_dir(self) -> Path:
        return self.data_dir / "workspaces"

    @property
    def sessions_file(self) -> Path:
        return self.data_dir / "sessions.json"

    @property
    def interpret_sessions_file(self) -> Path:
        return self.data_dir / "interpret_sessions.json"

    @property
    def interpret_uploads_dir(self) -> Path:
        return self.data_dir / "uploads" / "interpret"

    @classmethod
    def load(cls) -> ViewerSettings:
        data_dir = Path.home() / ".doc-chunk-viewer"
        if custom := os.environ.get("DOC_CHUNK_VIEWER_DATA"):
            data_dir = Path(custom)
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "workspaces").mkdir(parents=True, exist_ok=True)
        return cls(data_dir=data_dir.resolve())
