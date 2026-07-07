from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from tender_insights.summary_loop.client import InvokeTextResult
from tender_insights.summary_loop.models import (
    LoopState,
    SummaryLoopInvokeError,
    SummaryLoopInvokeTimeoutError,
)
from tender_insights.summary_loop.runner import SummaryLoopRunner
from tender_insights.summary_loop.tasks import TASK_DEFINITIONS


@dataclass
class FakeSummaryLoopClient:
    outcomes: list[str | Exception] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)
    _index: int = 0

    def invoke(self, input: dict[str, Any]) -> InvokeTextResult:
        self.calls.append(dict(input))
        outcome = self.outcomes[self._index]
        self._index += 1
        if isinstance(outcome, Exception):
            raise outcome
        return InvokeTextResult(output=outcome, duration_ms=10, raw_response={"status": "completed"})


def test_runner_accumulates_state_across_five_steps():
    client = FakeSummaryLoopClient(
        outcomes=["概要", "得分", "废标", "响应", "完整报告"],
    )
    runner = SummaryLoopRunner(client=client)
    result = runner.run(LoopState(tender_info="正文", task_background="背景"))

    assert result.status == "completed"
    assert result.state.tender_summary == "概要"
    assert result.state.score_points == "得分"
    assert result.state.report == "完整报告"
    assert len(result.completed_steps) == 5
    assert client.calls[1]["tender_summary"] == "概要"
    assert client.calls[4]["disqualification_items"] == "废标"


def test_runner_retries_once_on_invoke_error():
    client = FakeSummaryLoopClient(
        outcomes=[
            SummaryLoopInvokeError("boom"),
            "概要",
            "得分",
            "废标",
            "响应",
            "完整报告",
        ],
    )
    runner = SummaryLoopRunner(client=client)
    result = runner.run(LoopState(tender_info="x", task_background="y"))
    assert result.status == "completed"
    assert result.step_results[0].attempt == 2


def test_runner_does_not_retry_on_timeout():
    client = FakeSummaryLoopClient(
        outcomes=[SummaryLoopInvokeTimeoutError("timeout", elapsed_ms=180000, configured_timeout_s=600)],
    )
    runner = SummaryLoopRunner(client=client)
    result = runner.run(LoopState(tender_info="x", task_background="y"))
    assert result.status == "failed"
    assert result.error_type == "timeout"
    assert result.failed_step == TASK_DEFINITIONS[0].current_task
    assert result.elapsed_ms == 180000
    assert len(client.calls) == 1


def test_runner_fails_after_two_non_timeout_errors():
    client = FakeSummaryLoopClient(
        outcomes=[
            SummaryLoopInvokeError("e1"),
            SummaryLoopInvokeError("e2"),
        ],
    )
    runner = SummaryLoopRunner(client=client)
    result = runner.run(LoopState(tender_info="x", task_background="y"))
    assert result.status == "failed"
    assert result.error_type == "invoke_error"
    assert len(client.calls) == 2
