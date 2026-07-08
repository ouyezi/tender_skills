from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from tender_insights.diagnosis.models import DiagnosisSegment


class BidDiagnoseError(Exception):
    """Base error for bid diagnose."""


class BidDiagnosePrerequisiteError(BidDiagnoseError):
    """Missing or invalid bid_summary/ prerequisites."""


class BidDiagnoseInvokeError(BidDiagnoseError):
    def __init__(self, message: str, *, elapsed_ms: int | None = None) -> None:
        super().__init__(message)
        self.elapsed_ms = elapsed_ms


class BidDiagnoseInvokeTimeoutError(BidDiagnoseInvokeError):
    def __init__(self, message: str, *, elapsed_ms: int, configured_timeout_s: int) -> None:
        super().__init__(message, elapsed_ms=elapsed_ms)
        self.configured_timeout_s = configured_timeout_s


@dataclass(frozen=True)
class TaskDefinition:
    step_index: int
    current_task: str
    task_skills: str
    output_requirement: str
    output_field: str


@dataclass
class SegmentDiagnoseState:
    import_diagnose: str = ""
    segment_diagnose_result: str = ""


@dataclass
class BidDiagnoseState:
    bid_background: str
    analysis_report: str
    diagnose_before: str
    segments: list[DiagnosisSegment]

    def to_invoke_input(
        self,
        segment: DiagnosisSegment,
        task: TaskDefinition,
        segment_state: SegmentDiagnoseState,
        *,
        sec_in_total: str,
    ) -> dict[str, str]:
        return {
            "bid_background": self.bid_background,
            "analysis_report": self.analysis_report,
            "diagnose_before": self.diagnose_before,
            "sec_in_total": sec_in_total,
            "current_chunk": segment.markdown,
            "import_diagnose": segment_state.import_diagnose,
            "diagnose_result": segment_state.segment_diagnose_result,
            "current_task": task.current_task,
            "task_skills": task.task_skills,
            "output_requirement": task.output_requirement,
        }

    def apply_output(
        self,
        task: TaskDefinition,
        structured: dict[str, str],
        segment_state: SegmentDiagnoseState,
    ) -> None:
        value = structured.get(task.output_field, "").strip()
        if not value:
            raise BidDiagnoseInvokeError(f"empty {task.output_field} in structuredOutput")
        if task.current_task == "import_diagnose":
            segment_state.import_diagnose = value
        elif task.current_task == "diagnose_result":
            segment_state.segment_diagnose_result = value
        elif task.current_task == "update_diagnose":
            self.diagnose_before = value


@dataclass(frozen=True)
class TaskStepResult:
    current_task: str
    duration_ms: int
    attempt: int


@dataclass(frozen=True)
class SegmentDiagnoseStepResult:
    segment_index: int
    char_count: int
    source_chunk_ids: list[str]
    sec_in_total: str
    import_diagnose: str
    segment_diagnose_result: str
    steps: list[TaskStepResult]


@dataclass
class BidDiagnoseRunResult:
    status: Literal["completed", "failed", "partial"]
    state: BidDiagnoseState
    completed_segments: list[int] = field(default_factory=list)
    segment_results: list[SegmentDiagnoseStepResult] = field(default_factory=list)
    failed_segment: int | None = None
    failed_task: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    elapsed_ms: int | None = None
    configured_timeout_s: int | None = None

    def to_run_state_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "status": self.status,
            "completed_segments": self.completed_segments,
            "segments": [
                {
                    "segment_index": s.segment_index,
                    "steps": [
                        {
                            "current_task": step.current_task,
                            "duration_ms": step.duration_ms,
                            "attempt": step.attempt,
                        }
                        for step in s.steps
                    ],
                }
                for s in self.segment_results
            ],
        }
        if self.failed_segment is not None:
            data["failed_segment"] = self.failed_segment
        if self.failed_task:
            data["failed_task"] = self.failed_task
        if self.error_type:
            data["error_type"] = self.error_type
        if self.error_message:
            data["message"] = self.error_message
        if self.elapsed_ms is not None:
            data["elapsed_ms"] = self.elapsed_ms
        if self.configured_timeout_s is not None:
            data["configured_timeout_s"] = self.configured_timeout_s
        return data
