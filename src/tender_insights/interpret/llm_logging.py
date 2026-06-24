from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger("tender_insights.interpret.llm")


def _prompts_enabled() -> bool:
    raw = os.environ.get("INTERPRET_LOG_PROMPTS")
    if raw is None:
        return True
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def log_llm_prompt(
    *,
    call_type: str,
    messages: list[dict[str, str]],
    workspace: str | None = None,
    segment_id: str | None = None,
    section_path: list[str] | None = None,
    token_estimate: int | None = None,
) -> None:
    if not _prompts_enabled():
        return

    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "call_type": call_type,
        "workspace": workspace,
        "segment_id": segment_id,
        "section_path": section_path or [],
        "token_estimate": token_estimate,
        "messages": messages,
    }
    logger.info(
        "interpret_llm_prompt call_type=%s segment_id=%s section_path=%s messages=%s",
        call_type,
        segment_id or "-",
        " > ".join(section_path or []) or "-",
        json.dumps(messages, ensure_ascii=False),
    )

    dump_dir = os.environ.get("INTERPRET_LOG_PROMPTS_DIR")
    if not dump_dir:
        return
    out = Path(dump_dir)
    out.mkdir(parents=True, exist_ok=True)
    fname = segment_id or call_type
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in fname)
    (out / f"{safe}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
