from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from tender_insights.bid_diagnose.client import InvokeStructuredResult
from tender_insights.bid_diagnose.models import (
    BidDiagnoseInvokeError,
    BidDiagnoseInvokeTimeoutError,
    BidDiagnoseState,
)
from tender_insights.bid_diagnose.runner import BidDiagnoseRunner
from tender_insights.diagnosis.models import DiagnosisSegment


@dataclass
class FakeBidDiagnoseClient:
    outcomes: list[dict[str, str] | Exception] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)
    _index: int = 0

    def invoke(self, input: dict[str, Any]) -> InvokeStructuredResult:
        self.calls.append(dict(input))
        outcome = self.outcomes[self._index]
        self._index += 1
        if isinstance(outcome, Exception):
            raise outcome
        return InvokeStructuredResult(output=outcome, duration_ms=10, raw_response={"status": "completed"})


def _state_two_segments() -> tuple[BidDiagnoseState, dict[int, str]]:
    segments = [
        DiagnosisSegment(1, "seg1", 4, ["c1"], []),
        DiagnosisSegment(2, "seg2", 4, ["c2"], []),
    ]
    state = BidDiagnoseState(
        bid_background="bg",
        analysis_report="report",
        diagnose_before="",
        segments=segments,
    )
    return state, {1: "s1", 2: "s2"}


def test_runner_executes_three_tasks_per_segment_and_rolls_diagnose_before():
    client = FakeBidDiagnoseClient(
        outcomes=[
            {"import_diagnose": "i1"},
            {"diagnose_result": "d1"},
            {"diagnose_result": "acc1"},
            {"import_diagnose": "i2"},
            {"diagnose_result": "d2"},
            {"diagnose_result": "acc2"},
        ]
    )
    state, sec_map = _state_two_segments()
    runner = BidDiagnoseRunner(client=client)
    result = runner.run(state, sec_map)

    assert result.status == "completed"
    assert result.state.diagnose_before == "acc2"
    assert len(client.calls) == 6
    assert client.calls[0]["current_task"] == "import_diagnose"
    assert client.calls[1]["import_diagnose"] == "i1"
    assert client.calls[2]["diagnose_result"] == "d1"
    assert client.calls[3]["diagnose_before"] == "acc1"
    assert client.calls[3]["current_task"] == "import_diagnose"


def test_runner_does_not_retry_on_timeout():
    client = FakeBidDiagnoseClient(
        outcomes=[BidDiagnoseInvokeTimeoutError("t", elapsed_ms=1, configured_timeout_s=600)]
    )
    state, sec_map = _state_two_segments()
    runner = BidDiagnoseRunner(client=client)
    result = runner.run(state, sec_map)
    assert result.status == "failed"
    assert result.failed_segment == 1
    assert result.failed_task == "import_diagnose"
    assert len(client.calls) == 1


def test_runner_retries_once_on_invoke_error():
    client = FakeBidDiagnoseClient(
        outcomes=[
            BidDiagnoseInvokeError("boom"),
            {"import_diagnose": "i1"},
            {"diagnose_result": "d1"},
            {"diagnose_result": "acc1"},
            {"import_diagnose": "i2"},
            {"diagnose_result": "d2"},
            {"diagnose_result": "acc2"},
        ]
    )
    state, sec_map = _state_two_segments()
    runner = BidDiagnoseRunner(client=client)
    result = runner.run(state, sec_map)
    assert result.status == "completed"
    assert result.segment_results[0].steps[0].attempt == 2
