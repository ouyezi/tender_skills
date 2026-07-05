from __future__ import annotations

import pytest

from agent_platform.models import AgentInvokeError, AgentInvokeResult


def test_agent_invoke_result_fields():
    result = AgentInvokeResult(
        call_type="outline_refine",
        status="completed",
        structured_output={"change_summary": "ok"},
        text_output=None,
        raw_response={"status": "completed"},
        duration_ms=12,
    )
    assert result.call_type == "outline_refine"
    assert result.structured_output["change_summary"] == "ok"


def test_agent_invoke_error_carries_message():
    err = AgentInvokeError("platform failed")
    assert str(err) == "platform failed"
    with pytest.raises(AgentInvokeError):
        raise AgentInvokeError("boom")
