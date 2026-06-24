from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LLMCompletionResult:
    text: str
    model: str | None = None
    usage: dict[str, Any] | None = None
    finish_reason: str | None = None
    stream: bool = False
    duration_ms: float | None = None


@dataclass(frozen=True)
class StreamCollectResult:
    text: str
    usage: dict[str, Any] | None = None
    finish_reason: str | None = None
