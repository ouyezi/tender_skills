from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _parse_env_line(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if stripped.startswith("export "):
        stripped = stripped[7:].strip()
    if "=" not in stripped:
        return None
    key, _, value = stripped.partition("=")
    key = key.strip()
    if not key:
        return None
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return key, value


def load_project_env() -> Path | None:
    """Load repo `.env` into os.environ (does not override existing vars)."""
    candidates = [Path.cwd() / ".env", _REPO_ROOT / ".env"]
    for path in candidates:
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            parsed = _parse_env_line(line)
            if parsed is None:
                continue
            key, value = parsed
            os.environ.setdefault(key, value)
        return path
    return None


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
