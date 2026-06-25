from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from doc_chunk.workspace.layout import OutputWorkspace

from tender_insights.gen_catalog.models import GenCatalogSession

SESSION_REL = Path("gen_catalog") / "session.json"
DRAFT_NAME = "bid_outline.draft.json"


def session_path(workspace: OutputWorkspace) -> Path:
    return workspace.root / SESSION_REL


def load_session(workspace: OutputWorkspace) -> GenCatalogSession:
    path = session_path(workspace)
    if not path.is_file():
        raise FileNotFoundError("gen_catalog session not found")
    return GenCatalogSession.model_validate_json(path.read_text(encoding="utf-8"))


def save_session(workspace: OutputWorkspace, session: GenCatalogSession) -> None:
    session.updated_at = datetime.now(UTC).isoformat()
    path = session_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(session.model_dump_json(), encoding="utf-8")


def clear_gen_catalog_artifacts(workspace: OutputWorkspace) -> None:
    for rel in (SESSION_REL, Path(DRAFT_NAME)):
        target = workspace.root / rel
        if target.is_file():
            target.unlink()
