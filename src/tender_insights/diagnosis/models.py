from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel


class DiagnosisError(Exception):
    """Base error for diagnosis."""


class DiagnosisPrerequisiteError(DiagnosisError):
    """Missing summary_loop/report.md or chunks/."""


class DiagnosisInvokeError(DiagnosisError):
    def __init__(self, message: str, *, elapsed_ms: int | None = None) -> None:
        super().__init__(message)
        self.elapsed_ms = elapsed_ms


class DiagnosisInvokeTimeoutError(DiagnosisInvokeError):
    def __init__(self, message: str, *, elapsed_ms: int, configured_timeout_s: int) -> None:
        super().__init__(message, elapsed_ms=elapsed_ms)
        self.configured_timeout_s = configured_timeout_s


class ChunkSummaryOutput(BaseModel):
    current_summary: str
    total_summary: str
    sec_in_total: str


@dataclass(frozen=True)
class DiagnosisSegment:
    segment_index: int
    markdown: str
    char_count: int
    source_chunk_ids: list[str]
    section_path: list[str]


@dataclass
class DiagnosisState:
    tender_report: str
    preview_summary: str
    segments: list[DiagnosisSegment]

    def to_invoke_input(self, segment: DiagnosisSegment) -> dict[str, str]:
        return {
            "chunk": segment.markdown,
            "tender_report": self.tender_report,
            "total_chunk_count": str(len(self.segments)),
            "current_count": str(segment.segment_index),
            "preview_summary": self.preview_summary,
        }

    def apply_output(self, output: ChunkSummaryOutput) -> None:
        self.preview_summary = output.total_summary


@dataclass(frozen=True)
class SegmentStepResult:
    segment_index: int
    output: ChunkSummaryOutput
    duration_ms: int
    attempt: int
    char_count: int
    source_chunk_ids: list[str]


@dataclass
class DiagnosisRunResult:
    status: Literal["completed", "failed", "partial"]
    state: DiagnosisState
    completed_segments: list[int] = field(default_factory=list)
    step_results: list[SegmentStepResult] = field(default_factory=list)
    failed_segment: int | None = None
    error_type: str | None = None
    error_message: str | None = None
    elapsed_ms: int | None = None
    configured_timeout_s: int | None = None

    def to_run_state_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "status": self.status,
            "completed_segments": self.completed_segments,
            "steps": [
                {
                    "segment_index": s.segment_index,
                    "duration_ms": s.duration_ms,
                    "attempt": s.attempt,
                    "char_count": s.char_count,
                }
                for s in self.step_results
            ],
        }
        if self.failed_segment is not None:
            data["failed_segment"] = self.failed_segment
        if self.error_type:
            data["error_type"] = self.error_type
        if self.error_message:
            data["message"] = self.error_message
        if self.elapsed_ms is not None:
            data["elapsed_ms"] = self.elapsed_ms
        if self.configured_timeout_s is not None:
            data["configured_timeout_s"] = self.configured_timeout_s
        return data
