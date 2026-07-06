from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from agent_platform.backends.local import LocalBackend
from agent_platform.client import AgentClient
from agent_platform.models import AgentInvokeError, AgentInvokeResult
from agent_platform.structured import invoke_json_model, invoke_text
from doc_chunk.llm.client import FakeLLMClient


class _SampleModel(BaseModel):
    knowledge_type: str
    confidence: float = Field(ge=0, le=1)


class _CountingBackend:
    def __init__(self, results: list[AgentInvokeResult | Exception]) -> None:
        self._results = list(results)
        self.inputs: list[dict[str, Any]] = []

    def invoke(self, call_type: str, input: dict[str, Any]) -> AgentInvokeResult:
        self.inputs.append(dict(input))
        item = self._results.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def test_invoke_json_model_blind_retries_same_input():
    backend = _CountingBackend(
        [
            AgentInvokeResult(
                call_type="chunk_classify",
                status="completed",
                structured_output={"knowledge_type": "x"},  # missing confidence
                text_output=None,
                raw_response={},
            ),
            AgentInvokeResult(
                call_type="chunk_classify",
                status="completed",
                structured_output={"knowledge_type": "scheme", "confidence": 0.8},
                text_output=None,
                raw_response={},
            ),
        ]
    )
    client = AgentClient(backend)
    payload = {"title": "t", "markdown": "m"}
    model = invoke_json_model(client, "chunk_classify", payload, _SampleModel, max_retries=1)
    assert model.knowledge_type == "scheme"
    assert backend.inputs == [payload, payload]


def test_invoke_text_returns_text_output():
    llm = FakeLLMClient(responses=["摘要文本"])
    client = AgentClient(LocalBackend(llm_client=llm))
    text = invoke_text(
        client,
        "chunk_describe",
        {"title": "t", "markdown": "m"},
    )
    assert text == "摘要文本"


def test_invoke_json_model_raises_after_retries():
    backend = _CountingBackend(
        [
            AgentInvokeError("boom"),
            AgentInvokeError("boom"),
        ]
    )
    client = AgentClient(backend)
    try:
        invoke_json_model(
            client,
            "chunk_classify",
            {"title": "t", "markdown": "m"},
            _SampleModel,
            max_retries=1,
        )
        assert False, "expected AgentInvokeError"
    except AgentInvokeError as exc:
        assert "failed after retries" in str(exc)
