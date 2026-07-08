from __future__ import annotations

import json
import os
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from agent_platform.json_coerce import coerce_structured_output

from tender_insights.bid_diagnose.models import (
    BidDiagnoseInvokeError,
    BidDiagnoseInvokeTimeoutError,
)

APP_NAME = "bid_diagnose_app"

_OUTPUT_FIELD_BY_TASK = {
    "import_diagnose": "import_diagnose",
    "diagnose_result": "diagnose_result",
    "update_diagnose": "diagnose_result",
}


def _validate_http_header_value(name: str, value: str) -> str:
    try:
        value.encode("latin-1")
    except UnicodeEncodeError as exc:
        raise BidDiagnoseInvokeError(
            f"{name} must contain only ASCII characters (HTTP header limit); "
            f"check that AGENT_PLATFORM_API_KEY is the platform API key, not Chinese text or LLM_API_KEY"
        ) from exc
    return value


@dataclass(frozen=True)
class InvokeStructuredResult:
    output: dict[str, str]
    duration_ms: int
    raw_response: dict[str, Any]


class BidDiagnoseClient:
    def __init__(self, *, base_url: str, api_key: str, timeout_s: int = 600) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = _validate_http_header_value("X-API-Key", api_key.strip())
        self.timeout_s = timeout_s

    def invoke(self, input: dict[str, Any]) -> InvokeStructuredResult:
        current_task = str(input.get("current_task") or "")
        output_field = _OUTPUT_FIELD_BY_TASK.get(current_task)
        if not output_field:
            raise BidDiagnoseInvokeError(f"unknown current_task: {current_task}")

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
                raise BidDiagnoseInvokeTimeoutError(
                    "invoke timed out before configured limit — check client/server timeout alignment",
                    elapsed_ms=elapsed_ms,
                    configured_timeout_s=self.timeout_s,
                ) from exc
            raise BidDiagnoseInvokeError(str(exc), elapsed_ms=elapsed_ms) from exc
        except TimeoutError as exc:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            raise BidDiagnoseInvokeTimeoutError(
                "invoke timed out before configured limit — check client/server timeout alignment",
                elapsed_ms=elapsed_ms,
                configured_timeout_s=self.timeout_s,
            ) from exc

        duration_ms = int((time.perf_counter() - started) * 1000)
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            raise BidDiagnoseInvokeError(f"invalid JSON response: {exc}", elapsed_ms=duration_ms) from exc

        if not isinstance(payload, dict):
            raise BidDiagnoseInvokeError("platform response must be JSON object", elapsed_ms=duration_ms)

        status = str(payload.get("status") or "")
        if status != "completed":
            raise BidDiagnoseInvokeError(
                f"invoke not completed for {APP_NAME}: {payload}",
                elapsed_ms=duration_ms,
            )

        value = _extract_output_value(payload, output_field)
        if not value:
            raise BidDiagnoseInvokeError(f"empty {output_field} in structuredOutput", elapsed_ms=duration_ms)

        return InvokeStructuredResult(
            output={output_field: value},
            duration_ms=duration_ms,
            raw_response=payload,
        )


def _extract_output_value(payload: dict[str, Any], output_field: str) -> str:
    structured = coerce_structured_output(payload)
    if isinstance(structured, dict):
        value = str(structured.get(output_field) or "").strip()
        if value:
            return value

    output = payload.get("output")
    if isinstance(output, str) and output.strip():
        return output.strip()

    return ""


def create_bid_diagnose_client_from_env() -> BidDiagnoseClient:
    base_url = os.environ.get("AGENT_PLATFORM_BASE_URL", "http://localhost:8000")
    api_key = os.environ.get("AGENT_PLATFORM_API_KEY", "").strip()
    if not api_key:
        raise BidDiagnoseInvokeError("AGENT_PLATFORM_API_KEY is required for bid diagnose")
    timeout_raw = os.environ.get("BID_DIAGNOSE_INVOKE_TIMEOUT_S", "600").strip()
    timeout_s = int(timeout_raw)
    return BidDiagnoseClient(base_url=base_url, api_key=api_key, timeout_s=timeout_s)
