import json
import logging

import pytest

from tender_insights.interpret.llm_logging import log_llm_attempt, log_llm_prompt


def test_log_llm_prompt_emits_full_messages(caplog, monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("INTERPRET_LOG_PROMPTS", raising=False)
    out_dir = tmp_path / "prompts"
    monkeypatch.setenv("INTERPRET_LOG_PROMPTS_DIR", str(out_dir))

    messages = [
        {"role": "system", "content": "SYSTEM TEXT"},
        {"role": "user", "content": "USER TEXT with 商品方案 0-2分"},
    ]
    with caplog.at_level(logging.INFO, logger="tender_insights.interpret.llm"):
        log_llm_prompt(
            call_type="segment",
            messages=messages,
            workspace="/tmp/ws",
            segment_id="seg-001",
            section_path=["第三章", "5.2 评分"],
            token_estimate=42,
        )

    assert any("SYSTEM TEXT" in r.message for r in caplog.records)
    assert any("USER TEXT with 商品方案" in r.message for r in caplog.records)
    dumped = json.loads((out_dir / "seg-001.json").read_text(encoding="utf-8"))
    assert dumped["call_type"] == "segment"
    assert dumped["messages"] == messages


def test_log_llm_prompt_disabled(monkeypatch, caplog) -> None:
    monkeypatch.setenv("INTERPRET_LOG_PROMPTS", "0")
    with caplog.at_level(logging.INFO, logger="tender_insights.interpret.llm"):
        log_llm_prompt(call_type="overview", messages=[{"role": "user", "content": "x"}])
    assert caplog.records == []


def test_log_llm_prompt_appends_jsonl(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("INTERPRET_LOG_PROMPTS", raising=False)
    jsonl_path = tmp_path / "calls.jsonl"
    monkeypatch.setenv("INTERPRET_LOG_JSONL", str(jsonl_path))

    messages = [{"role": "user", "content": "hello"}]
    log_llm_prompt(call_type="segment", messages=messages, segment_id="seg-a")

    lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["segment_id"] == "seg-a"
    assert record["messages"] == messages


def test_log_llm_attempt_appends_jsonl(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("INTERPRET_LOG_PROMPTS", raising=False)
    jsonl_path = tmp_path / "calls.jsonl"
    monkeypatch.setenv("INTERPRET_LOG_JSONL", str(jsonl_path))

    log_llm_attempt(
        call_type="segment",
        segment_id="seg-a",
        attempt=0,
        success=False,
        response_raw='{"scoring_items":[',
        validation_error="json decode",
        usage={"prompt_tokens": 1, "prompt_tokens_details": {"cached_tokens": 1}},
        model="qwen3.7-max",
        stream=True,
        duration_ms=1234.5,
    )

    record = json.loads(jsonl_path.read_text(encoding="utf-8").strip())
    assert record["event"] == "attempt"
    assert record["success"] is False
    assert record["usage"]["prompt_tokens_details"]["cached_tokens"] == 1
    assert record["duration_ms"] == 1234.5
