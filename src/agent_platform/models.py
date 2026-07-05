from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class AgentInvokeError(Exception):
    pass


@dataclass(frozen=True)
class AgentInvokeRequest:
    call_type: str
    input: dict[str, Any]


@dataclass(frozen=True)
class AgentInvokeResult:
    call_type: str
    status: str
    structured_output: dict[str, Any] | None
    text_output: str | None
    raw_response: dict[str, Any]
    duration_ms: int | None = None
