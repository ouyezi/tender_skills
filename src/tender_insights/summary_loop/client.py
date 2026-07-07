from __future__ import annotations

import json
import os
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from tender_insights.summary_loop.models import SummaryLoopInvokeError, SummaryLoopInvokeTimeoutError

APP_NAME = "tender_summary_app"


@dataclass(frozen=True)
class InvokeTextResult:
    output: str
    duration_ms: int
    raw_response: dict[str, Any]


class SummaryLoopClient:
    def __init__(self, *, base_url: str, api_key: str, timeout_s: int = 600) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_s = timeout_s

    def invoke(self, input: dict[str, Any]) -> InvokeTextResult:
        url = f"{self.base_url}/v1/apps/invoke"
        body = json.dumps({"appName": APP_NAME, "input": input}).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": self.api_key,
        }
        req = urllib.request.Request(url, data=body, method="POST", headers=headers)
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.URLError as exc:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                raise SummaryLoopInvokeTimeoutError(
                    "invoke timed out before configured limit — check client/server timeout alignment",
                    elapsed_ms=elapsed_ms,
                    configured_timeout_s=self.timeout_s,
                ) from exc
            raise SummaryLoopInvokeError(str(exc), elapsed_ms=elapsed_ms) from exc
        except TimeoutError as exc:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            raise SummaryLoopInvokeTimeoutError(
                "invoke timed out before configured limit — check client/server timeout alignment",
                elapsed_ms=elapsed_ms,
                configured_timeout_s=self.timeout_s,
            ) from exc

        duration_ms = int((time.perf_counter() - started) * 1000)
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            raise SummaryLoopInvokeError(f"invalid JSON response: {exc}", elapsed_ms=duration_ms) from exc

        if not isinstance(payload, dict):
            raise SummaryLoopInvokeError("platform response must be JSON object", elapsed_ms=duration_ms)

        status = str(payload.get("status") or "")
        if status != "completed":
            raise SummaryLoopInvokeError(
                f"invoke not completed for {APP_NAME}: {payload}",
                elapsed_ms=duration_ms,
            )

        output = payload.get("output")
        if not isinstance(output, str) or not output.strip():
            raise SummaryLoopInvokeError("missing non-empty text output", elapsed_ms=duration_ms)

        return InvokeTextResult(output=output, duration_ms=duration_ms, raw_response=payload)


def create_summary_loop_client_from_env() -> SummaryLoopClient:
    base_url = os.environ.get("AGENT_PLATFORM_BASE_URL", "http://localhost:8000")
    api_key = os.environ.get("AGENT_PLATFORM_API_KEY", "").strip()
    if not api_key:
        raise SummaryLoopInvokeError("AGENT_PLATFORM_API_KEY is required for summary loop")
    timeout_raw = os.environ.get("SUMMARY_LOOP_INVOKE_TIMEOUT_S", "600").strip()
    timeout_s = int(timeout_raw)
    return SummaryLoopClient(base_url=base_url, api_key=api_key, timeout_s=timeout_s)
