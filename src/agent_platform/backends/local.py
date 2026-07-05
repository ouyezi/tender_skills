from __future__ import annotations

from typing import Any, Callable

from doc_chunk.llm.client import LLMClient

from agent_platform.handlers.outline_refine import invoke_outline_refine
from agent_platform.models import AgentInvokeError, AgentInvokeResult

Handler = Callable[[LLMClient, dict[str, Any]], AgentInvokeResult]

_HANDLERS: dict[str, Handler] = {
    "outline_refine": invoke_outline_refine,
}


class LocalBackend:
    def __init__(self, *, llm_client: LLMClient) -> None:
        self._llm_client = llm_client

    def invoke(self, call_type: str, input: dict[str, Any]) -> AgentInvokeResult:
        handler = _HANDLERS.get(call_type)
        if handler is None:
            raise AgentInvokeError(f"no local handler registered for call_type: {call_type}")
        return handler(self._llm_client, input)
