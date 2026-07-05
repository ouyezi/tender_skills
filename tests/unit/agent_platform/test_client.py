from __future__ import annotations

from typing import Any

from agent_platform.client import AgentClient
from agent_platform.models import AgentInvokeResult


class _StubBackend:
    def invoke(self, call_type: str, input: dict[str, Any]) -> AgentInvokeResult:
        return AgentInvokeResult(
            call_type=call_type,
            status="completed",
            structured_output={"echo": input.get("x")},
            text_output=None,
            raw_response={"status": "completed"},
        )


def test_agent_client_delegates_to_backend():
    client = AgentClient(_StubBackend())
    result = client.invoke("outline_refine", {"x": 1})
    assert result.call_type == "outline_refine"
    assert result.structured_output == {"echo": 1}
