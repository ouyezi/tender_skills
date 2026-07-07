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

from tender_insights.diagnosis.models import (
    ChunkSummaryOutput,
    DiagnosisInvokeError,
    DiagnosisInvokeTimeoutError,
)

APP_NAME = "bid_chunk_summary"


def _validate_http_header_value(name: str, value: str) -> str:
    try:
        value.encode("latin-1")
    except UnicodeEncodeError as exc:
        raise DiagnosisInvokeError(
            f"{name} must contain only ASCII characters (HTTP header limit); "
            f"check that AGENT_PLATFORM_API_KEY is the platform API key, not Chinese text or LLM_API_KEY"
        ) from exc
    return value


@dataclass(frozen=True)
class InvokeStructuredResult:
    output: ChunkSummaryOutput
    duration_ms: int
    raw_response: dict[str, Any]


class DiagnosisClient:
    def __init__(self, *, base_url: str, api_key: str, timeout_s: int = 600) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = _validate_http_header_value("X-API-Key", api_key.strip())
        self.timeout_s = timeout_s

    def invoke(self, input: dict[str, Any]) -> InvokeStructuredResult:
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
                raise DiagnosisInvokeTimeoutError(
                    "invoke timed out before configured limit — check client/server timeout alignment",
                    elapsed_ms=elapsed_ms,
                    configured_timeout_s=self.timeout_s,
                ) from exc
            raise DiagnosisInvokeError(str(exc), elapsed_ms=elapsed_ms) from exc
        except TimeoutError as exc:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            raise DiagnosisInvokeTimeoutError(
                "invoke timed out before configured limit — check client/server timeout alignment",
                elapsed_ms=elapsed_ms,
                configured_timeout_s=self.timeout_s,
            ) from exc

        duration_ms = int((time.perf_counter() - started) * 1000)
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            raise DiagnosisInvokeError(f"invalid JSON response: {exc}", elapsed_ms=duration_ms) from exc

        if not isinstance(payload, dict):
            raise DiagnosisInvokeError("platform response must be JSON object", elapsed_ms=duration_ms)

        status = str(payload.get("status") or "")
        if status != "completed":
            raise DiagnosisInvokeError(
                f"invoke not completed for {APP_NAME}: {payload}",
                elapsed_ms=duration_ms,
            )

        structured = coerce_structured_output(payload)
        if not isinstance(structured, dict):
            raise DiagnosisInvokeError("missing structuredOutput", elapsed_ms=duration_ms)

        try:
            output = ChunkSummaryOutput.model_validate(structured)
        except Exception as exc:
            raise DiagnosisInvokeError(f"invalid structuredOutput: {exc}", elapsed_ms=duration_ms) from exc

        if not output.current_summary.strip() or not output.total_summary.strip():
            raise DiagnosisInvokeError("empty summary fields in structuredOutput", elapsed_ms=duration_ms)

        return InvokeStructuredResult(output=output, duration_ms=duration_ms, raw_response=payload)


def create_diagnosis_client_from_env() -> DiagnosisClient:
    base_url = os.environ.get("AGENT_PLATFORM_BASE_URL", "http://localhost:8000")
    api_key = os.environ.get("AGENT_PLATFORM_API_KEY", "").strip()
    if not api_key:
        raise DiagnosisInvokeError("AGENT_PLATFORM_API_KEY is required for diagnosis")
    timeout_raw = os.environ.get("DIAGNOSIS_INVOKE_TIMEOUT_S", "600").strip()
    timeout_s = int(timeout_raw)
    return DiagnosisClient(base_url=base_url, api_key=api_key, timeout_s=timeout_s)
