from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from tender_insights.diagnosis.client import InvokeStructuredResult
from tender_insights.diagnosis.models import (
    ChunkSummaryOutput,
    DiagnosisInvokeError,
    DiagnosisInvokeTimeoutError,
    DiagnosisSegment,
    DiagnosisState,
)
from tender_insights.diagnosis.runner import DiagnosisRunner


@dataclass
class FakeDiagnosisClient:
    outcomes: list[ChunkSummaryOutput | Exception] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)
    _index: int = 0

    def invoke(self, input: dict[str, Any]) -> InvokeStructuredResult:
        self.calls.append(dict(input))
        outcome = self.outcomes[self._index]
        self._index += 1
        if isinstance(outcome, Exception):
            raise outcome
        return InvokeStructuredResult(output=outcome, duration_ms=10, raw_response={"status": "completed"})


def _state_with_two_segments() -> DiagnosisState:
    segments = [
        DiagnosisSegment(1, "seg1", 4, ["c1"], []),
        DiagnosisSegment(2, "seg2", 4, ["c2"], []),
    ]
    return DiagnosisState(tender_report="report", preview_summary="", segments=segments)


def test_runner_passes_preview_summary_across_segments():
    client = FakeDiagnosisClient(
        outcomes=[
            ChunkSummaryOutput(current_summary="c1", total_summary="t1", sec_in_total="s1"),
            ChunkSummaryOutput(current_summary="c2", total_summary="t2", sec_in_total="s2"),
        ],
    )
    runner = DiagnosisRunner(client=client)
    result = runner.run(_state_with_two_segments())

    assert result.status == "completed"
    assert result.state.preview_summary == "t2"
    assert client.calls[0]["preview_summary"] == ""
    assert client.calls[1]["preview_summary"] == "t1"
    assert client.calls[1]["current_count"] == "2"
    assert client.calls[1]["total_chunk_count"] == "2"


def test_runner_retries_once_on_invoke_error():
    client = FakeDiagnosisClient(
        outcomes=[
            DiagnosisInvokeError("boom"),
            ChunkSummaryOutput(current_summary="c1", total_summary="t1", sec_in_total="s1"),
            ChunkSummaryOutput(current_summary="c2", total_summary="t2", sec_in_total="s2"),
        ],
    )
    runner = DiagnosisRunner(client=client)
    result = runner.run(_state_with_two_segments())
    assert result.status == "completed"
    assert result.step_results[0].attempt == 2


def test_runner_does_not_retry_on_timeout():
    client = FakeDiagnosisClient(
        outcomes=[DiagnosisInvokeTimeoutError("timeout", elapsed_ms=180000, configured_timeout_s=600)],
    )
    runner = DiagnosisRunner(client=client)
    result = runner.run(_state_with_two_segments())
    assert result.status == "failed"
    assert result.error_type == "timeout"
    assert result.failed_segment == 1
    assert len(client.calls) == 1
