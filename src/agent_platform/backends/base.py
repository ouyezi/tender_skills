from __future__ import annotations

from typing import Any, Protocol

from agent_platform.models import AgentInvokeResult


class AgentBackend(Protocol):
    def invoke(self, call_type: str, input: dict[str, Any]) -> AgentInvokeResult: ...
