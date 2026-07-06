from __future__ import annotations

import json

from pydantic import BaseModel, Field

from agent_platform.backends.local import LocalBackend
from agent_platform.client import AgentClient
from agent_platform.models import AgentInvokeError, AgentInvokeResult
from doc_chunk.llm.client import FakeLLMClient
from tender_insights.common.agent_extractor import extract_json_via_agent
from tender_insights.errors import LLMExtractionError


class _SampleModel(BaseModel):
    value: str
    confidence: float = Field(ge=0, le=1)


class _CountingBackend:
    def __init__(self, results: list[AgentInvokeResult | Exception]) -> None:
        self._results = list(results)
        self.inputs: list[dict] = []

    def invoke(self, call_type: str, input: dict) -> AgentInvokeResult:
        self.inputs.append(dict(input))
        item = self._results.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def test_extract_json_via_agent_blind_retries_same_input(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("INTERPRET_LOG_PROMPTS", raising=False)
    jsonl_path = tmp_path / "calls.jsonl"
    monkeypatch.setenv("INTERPRET_LOG_JSONL", str(jsonl_path))

    payload = {"segment_id": "seg-1", "section_path": "a", "markdown": "m"}
    backend = _CountingBackend(
        [
            AgentInvokeResult(
                call_type="interpret_segment",
                status="completed",
                structured_output={"value": "x"},
                text_output=None,
                raw_response={},
            ),
            AgentInvokeResult(
                call_type="interpret_segment",
                status="completed",
                structured_output={"value": "ok", "confidence": 0.9},
                text_output=None,
                raw_response={},
            ),
        ]
    )
    model = extract_json_via_agent(
        AgentClient(backend),
        "interpret_segment",
        payload,
        _SampleModel,
        max_retries=1,
        log_context={"call_type": "interpret_segment", "segment_id": "seg-1"},
    )
    assert model.value == "ok"
    assert backend.inputs == [payload, payload]
    records = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines()]
    attempts = [r for r in records if r.get("event") == "attempt"]
    assert len(attempts) == 2
    assert attempts[0]["success"] is False
    assert attempts[1]["success"] is True


def test_extract_json_via_agent_maps_to_llm_extraction_error() -> None:
    backend = _CountingBackend([AgentInvokeError("boom"), AgentInvokeError("boom")])
    try:
        extract_json_via_agent(
            AgentClient(backend),
            "interpret_segment",
            {"segment_id": "s", "section_path": "p", "markdown": "m"},
            _SampleModel,
            max_retries=1,
        )
        assert False, "expected LLMExtractionError"
    except LLMExtractionError as exc:
        assert "failed after retries" in str(exc)


def test_extract_json_via_agent_real_local_handler() -> None:
    llm = FakeLLMClient(
        responses=[
            '{"disqualification_items":[],"scoring_items":[],'
            '"bid_risk_items":[],"directory_requirements":[]}'
        ]
    )
    from tender_insights.interpret.models import InterpretationLLMResponse

    batch = extract_json_via_agent(
        AgentClient(LocalBackend(llm_client=llm)),
        "interpret_segment",
        {
            "segment_id": "seg-001",
            "section_path": "第一章",
            "markdown": "正文",
        },
        InterpretationLLMResponse,
    )
    assert batch.disqualification_items == []
