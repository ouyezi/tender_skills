from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


class SummaryLoopError(Exception):
    """Base error for summary_loop."""


class SummaryLoopInvokeError(SummaryLoopError):
    def __init__(self, message: str, *, elapsed_ms: int | None = None) -> None:
        super().__init__(message)
        self.elapsed_ms = elapsed_ms


class SummaryLoopInvokeTimeoutError(SummaryLoopInvokeError):
    def __init__(self, message: str, *, elapsed_ms: int, configured_timeout_s: int) -> None:
        super().__init__(message, elapsed_ms=elapsed_ms)
        self.configured_timeout_s = configured_timeout_s


@dataclass(frozen=True)
class TaskDefinition:
    step_index: int
    current_task: str
    task_skills: str
    output_requirement: str
    output_field: str | None
    step_filename: str


@dataclass
class LoopState:
    tender_info: str
    task_background: str
    tender_summary: str = ""
    score_points: str = ""
    disqualification_items: str = ""
    tender_responds: str = ""
    report: str = ""

    def to_invoke_input(self, task: TaskDefinition) -> dict[str, str]:
        return {
            "tender_info": self.tender_info,
            "task_background": self.task_background,
            "tender_summary": self.tender_summary,
            "score_points": self.score_points,
            "disqualification_items": self.disqualification_items,
            "tender_responds": self.tender_responds,
            "current_task": task.current_task,
            "task_skills": task.task_skills,
            "output_requirement": task.output_requirement,
        }

    def apply_output(self, task: TaskDefinition, output: str) -> None:
        if task.output_field is None:
            self.report = output
            return
        setattr(self, task.output_field, output)


@dataclass(frozen=True)
class StepResult:
    current_task: str
    output: str
    duration_ms: int
    attempt: int


@dataclass
class LoopRunResult:
    status: Literal["completed", "failed", "partial"]
    state: LoopState
    completed_steps: list[str] = field(default_factory=list)
    step_results: list[StepResult] = field(default_factory=list)
    failed_step: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    elapsed_ms: int | None = None
    configured_timeout_s: int | None = None

    def to_run_state_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "status": self.status,
            "completed_steps": self.completed_steps,
            "steps": [
                {
                    "current_task": s.current_task,
                    "duration_ms": s.duration_ms,
                    "attempt": s.attempt,
                }
                for s in self.step_results
            ],
        }
        if self.failed_step:
            data["failed_step"] = self.failed_step
        if self.error_type:
            data["error_type"] = self.error_type
        if self.error_message:
            data["message"] = self.error_message
        if self.elapsed_ms is not None:
            data["elapsed_ms"] = self.elapsed_ms
        if self.configured_timeout_s is not None:
            data["configured_timeout_s"] = self.configured_timeout_s
        return data

    def to_results_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "task_background": self.state.task_background,
            "tender_summary": self.state.tender_summary,
            "score_points": self.state.score_points,
            "disqualification_items": self.state.disqualification_items,
            "tender_responds": self.state.tender_responds,
            "report": self.state.report,
            "completed_steps": self.completed_steps,
            "status": self.status,
        }
