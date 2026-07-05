from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from agent_platform.json_coerce import coerce_structured_output
from agent_platform.models import AgentInvokeError, AgentInvokeResult


class PlatformBackend:
    def __init__(self, *, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")

    def invoke(self, call_type: str, input: dict[str, Any]) -> AgentInvokeResult:
        url = f"{self._base_url}/v1/apps/invoke"
        body = json.dumps({"appName": call_type, "input": input}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise AgentInvokeError(f"HTTP {exc.code} POST /v1/apps/invoke: {detail}") from exc

        duration_ms = int((time.perf_counter() - started) * 1000)
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            raise AgentInvokeError(f"invalid JSON response from platform: {exc}") from exc

        if not isinstance(payload, dict):
            raise AgentInvokeError("platform response must be JSON object")

        status = str(payload.get("status") or "")
        if status != "completed":
            raise AgentInvokeError(f"invoke not completed for {call_type}: {payload}")

        structured = coerce_structured_output(payload)
        text_output = payload.get("output")
        if not isinstance(text_output, str):
            text_output = None
        elif structured is not None:
            text_output = None

        return AgentInvokeResult(
            call_type=call_type,
            status=status,
            structured_output=structured,
            text_output=text_output,
            raw_response=payload,
            duration_ms=duration_ms,
        )
