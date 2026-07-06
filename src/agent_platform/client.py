from __future__ import annotations

from typing import Any

from agent_platform.backends.base import AgentBackend
from agent_platform.models import AgentInvokeResult


class AgentClient:
    def __init__(self, backend: AgentBackend) -> None:
        self._backend = backend

    def invoke(self, call_type: str, input: dict[str, Any]) -> AgentInvokeResult:
        return self._backend.invoke(call_type, input)
