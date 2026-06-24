import json

import pytest
from pydantic import BaseModel

from doc_chunk.llm.client import FakeLLMClient
from tender_insights.common.llm_extractor import extract_json_model


class _SampleModel(BaseModel):
    value: str


def test_extract_json_model_logs_failed_attempts(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("INTERPRET_LOG_PROMPTS", raising=False)
    jsonl_path = tmp_path / "calls.jsonl"
    monkeypatch.setenv("INTERPRET_LOG_JSONL", str(jsonl_path))

    client = FakeLLMClient(responses=["not-json", '{"value":"ok"}'])
    result = extract_json_model(
        client,
        [{"role": "user", "content": "hi"}],
        _SampleModel,
        log_context={"call_type": "segment", "segment_id": "seg-1"},
    )

    assert result.value == "ok"
    records = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines()]
    attempts = [r for r in records if r.get("event") == "attempt"]
    responses = [r for r in records if r.get("event") == "response"]
    assert len(attempts) == 2
    assert attempts[0]["success"] is False
    assert attempts[0]["response_raw"] == "not-json"
    assert attempts[1]["success"] is True
    assert len(responses) == 1
