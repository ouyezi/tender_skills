from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from doc_chunk.workspace.layout import OutputWorkspace

from tender_insights.diagnosis.client import (
    DiagnosisClient,
    InvokeStructuredResult,
    create_diagnosis_client_from_env,
)
from tender_insights.diagnosis.loader import load_diagnosis_inputs
from tender_insights.diagnosis.models import (
    DiagnosisInvokeError,
    DiagnosisInvokeTimeoutError,
    DiagnosisRunResult,
    DiagnosisState,
    SegmentStepResult,
)
from tender_insights.diagnosis.segment_optimizer import optimize_segments
from tender_insights.diagnosis.writer import (
    init_diagnosis_dir,
    write_run_state,
    write_sec_in_total_index,
    write_segment_result,
    write_segments_plan,
    write_total_summary,
)

MAX_RETRIES = 1


class DiagnosisClientProtocol(Protocol):
    def invoke(self, input: dict) -> InvokeStructuredResult: ...


class DiagnosisRunner:
    def __init__(
        self,
        *,
        client: DiagnosisClientProtocol,
        on_progress: Callable[[str, dict], None] | None = None,
    ) -> None:
        self._client = client
        self._on_progress = on_progress

    def run(self, state: DiagnosisState) -> DiagnosisRunResult:
        result = DiagnosisRunResult(status="partial", state=state)
        total = len(state.segments)
        for segment in state.segments:
            if self._on_progress:
                self._on_progress(
                    "bid_summary",
                    {
                        "message": f"标书总结分段 {segment.segment_index}/{total}",
                        "current": segment.segment_index,
                        "total": total,
                    },
                )
            last_error: Exception | None = None
            succeeded = False
            for attempt in range(MAX_RETRIES + 1):
                try:
                    invoke_result = self._client.invoke(state.to_invoke_input(segment))
                    state.apply_output(invoke_result.output)
                    result.completed_segments.append(segment.segment_index)
                    result.step_results.append(
                        SegmentStepResult(
                            segment_index=segment.segment_index,
                            output=invoke_result.output,
                            duration_ms=invoke_result.duration_ms,
                            attempt=attempt + 1,
                            char_count=segment.char_count,
                            source_chunk_ids=list(segment.source_chunk_ids),
                        )
                    )
                    succeeded = True
                    break
                except DiagnosisInvokeTimeoutError as exc:
                    return self._failed_result(
                        result,
                        segment.segment_index,
                        error_type="timeout",
                        error_message=str(exc),
                        elapsed_ms=exc.elapsed_ms,
                        configured_timeout_s=exc.configured_timeout_s,
                    )
                except DiagnosisInvokeError as exc:
                    last_error = exc
                    if attempt >= MAX_RETRIES:
                        return self._failed_result(
                            result,
                            segment.segment_index,
                            error_type="invoke_error",
                            error_message=str(exc),
                            elapsed_ms=exc.elapsed_ms,
                        )
            if not succeeded:
                return self._failed_result(
                    result,
                    segment.segment_index,
                    error_type="invoke_error",
                    error_message=str(last_error),
                )

        result.status = "completed"
        return result

    @staticmethod
    def _failed_result(
        result: DiagnosisRunResult,
        failed_segment: int,
        *,
        error_type: str,
        error_message: str,
        elapsed_ms: int | None = None,
        configured_timeout_s: int | None = None,
    ) -> DiagnosisRunResult:
        result.status = "failed" if not result.completed_segments else "partial"
        result.failed_segment = failed_segment
        result.error_type = error_type
        result.error_message = error_message
        result.elapsed_ms = elapsed_ms
        result.configured_timeout_s = configured_timeout_s
        return result


def run_diagnosis(
    workspace: OutputWorkspace,
    *,
    client: DiagnosisClient | None = None,
    on_progress: Callable[[str, dict], None] | None = None,
    overwrite: bool = False,
    timeout_s: int | None = None,
) -> DiagnosisRunResult:
    tender_report, raw_chunks = load_diagnosis_inputs(workspace)
    segments = optimize_segments(raw_chunks)
    state = DiagnosisState(tender_report=tender_report, preview_summary="", segments=segments)

    resolved_client = client
    if resolved_client is None:
        resolved_client = create_diagnosis_client_from_env()
        if timeout_s is not None:
            resolved_client = DiagnosisClient(
                base_url=resolved_client.base_url,
                api_key=resolved_client.api_key,
                timeout_s=timeout_s,
            )

    diag_dir = init_diagnosis_dir(workspace.root, overwrite=overwrite)
    write_segments_plan(diag_dir, segments)

    runner = DiagnosisRunner(client=resolved_client, on_progress=on_progress)
    result = runner.run(state)

    for step_result in result.step_results:
        write_segment_result(diag_dir, step_result)

    write_run_state(diag_dir, result)
    if result.step_results:
        write_sec_in_total_index(diag_dir, result.step_results)
    if result.state.preview_summary:
        write_total_summary(diag_dir, result.state.preview_summary)

    return result
