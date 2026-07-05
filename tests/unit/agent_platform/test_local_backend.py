from __future__ import annotations

import json

from agent_platform.backends.local import LocalBackend
from agent_platform.client import AgentClient
from doc_chunk.llm.client import FakeLLMClient


OUTLINE_REFINE_RESPONSE = (
    '{"outline_refined":{"schema_version":"1.0","strategy":"heading_heuristic","nodes":[]},'
    '"node_mappings":[],"change_summary":"ok"}'
)


def test_local_backend_outline_refine_returns_structured_output():
    llm = FakeLLMClient(responses=[OUTLINE_REFINE_RESPONSE])
    client = AgentClient(LocalBackend(llm_client=llm))
    result = client.invoke(
        "outline_refine",
        {
            "instruction": "test",
            "original_outline": {"schema_version": "1.0", "nodes": []},
            "current_outline": {"schema_version": "1.0", "nodes": []},
        },
    )
    assert result.status == "completed"
    assert result.structured_output is not None
    assert result.structured_output["change_summary"] == "ok"
    assert len(llm.calls) == 1
    user_msg = llm.calls[0]["messages"][1]["content"]
    payload = json.loads(user_msg)
    assert payload["instruction"] == "test"


def test_local_backend_unknown_call_type_raises():
    llm = FakeLLMClient()
    backend = LocalBackend(llm_client=llm)
    try:
        backend.invoke("unknown_agent", {})
        assert False, "expected AgentInvokeError"
    except Exception as exc:
        from agent_platform.models import AgentInvokeError

        assert isinstance(exc, AgentInvokeError)
        assert "unknown_agent" in str(exc)
