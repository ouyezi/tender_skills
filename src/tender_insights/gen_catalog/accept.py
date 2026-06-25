from __future__ import annotations

from datetime import UTC, datetime

from doc_chunk.workspace.layout import OutputWorkspace

from tender_insights.common.output_writer import write_json_artifact
from tender_insights.gen_catalog.models import BidOutlineFile
from tender_insights.gen_catalog.render import render_bid_outline_markdown
from tender_insights.gen_catalog.session import DRAFT_NAME


def accept_gen_catalog_draft(workspace: OutputWorkspace) -> BidOutlineFile:
    draft_path = workspace.root / DRAFT_NAME
    if not draft_path.is_file():
        raise FileNotFoundError("bid_outline.draft.json not found")
    draft = BidOutlineFile.model_validate_json(draft_path.read_text(encoding="utf-8"))
    if draft.status != "awaiting_accept":
        raise ValueError("draft is not awaiting accept")
    draft.status = "accepted"
    draft.accepted_at = datetime.now(UTC).isoformat()
    write_json_artifact(
        workspace,
        "bid_outline.json",
        draft.model_dump(mode="json"),
        stage_name="gen_catalog",
        output_key="bid_outline",
    )
    (workspace.root / "bid_outline.md").write_text(
        render_bid_outline_markdown(draft),
        encoding="utf-8",
    )
    return draft
