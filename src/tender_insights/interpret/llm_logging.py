from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger("tender_insights.interpret.llm")

LLM_CALLS_FILENAME = "llm_calls.jsonl"


def _prompts_enabled() -> bool:
    raw = os.environ.get("INTERPRET_LOG_PROMPTS")
    if raw is None:
        return True
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _jsonl_path() -> Path | None:
    raw = os.environ.get("INTERPRET_LOG_JSONL")
    if not raw:
        return None
    return Path(raw)


def append_llm_jsonl(payload: dict) -> None:
    path = _jsonl_path()
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def log_llm_prompt(
    *,
    call_type: str,
    messages: list[dict[str, str]],
    workspace: str | None = None,
    segment_id: str | None = None,
    section_path: list[str] | None = None,
    token_estimate: int | None = None,
    response: str | None = None,
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
    if response is not None:
        payload["response"] = response
    logger.info(
        "interpret_llm_prompt call_type=%s segment_id=%s section_path=%s messages=%s",
        call_type,
        segment_id or "-",
        " > ".join(section_path or []) or "-",
        json.dumps(messages, ensure_ascii=False),
    )

    append_llm_jsonl(payload)

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


def log_llm_response(
    *,
    call_type: str,
    segment_id: str | None = None,
    response: str,
) -> None:
    if not _prompts_enabled():
        return
    append_llm_jsonl(
        {
            "timestamp": datetime.now(UTC).isoformat(),
            "call_type": call_type,
            "segment_id": segment_id,
            "event": "response",
            "response": response,
        }
    )


def log_llm_attempt(
    *,
    call_type: str,
    segment_id: str | None = None,
    attempt: int,
    success: bool,
    response_raw: str,
    response_parsed: str | None = None,
    validation_error: str | None = None,
    usage: dict | None = None,
    model: str | None = None,
    finish_reason: str | None = None,
    stream: bool | None = None,
    duration_ms: float | None = None,
) -> None:
    if not _prompts_enabled():
        return
    payload: dict = {
        "timestamp": datetime.now(UTC).isoformat(),
        "event": "attempt",
        "call_type": call_type,
        "segment_id": segment_id,
        "attempt": attempt,
        "success": success,
        "response_raw": response_raw,
        "response_chars": len(response_raw),
    }
    if response_parsed is not None:
        payload["response_parsed"] = response_parsed
    if validation_error:
        payload["validation_error"] = validation_error
    if usage:
        payload["usage"] = usage
    if model:
        payload["model"] = model
    if finish_reason:
        payload["finish_reason"] = finish_reason
    if stream is not None:
        payload["stream"] = stream
    if duration_ms is not None:
        payload["duration_ms"] = round(duration_ms, 2)
    append_llm_jsonl(payload)
