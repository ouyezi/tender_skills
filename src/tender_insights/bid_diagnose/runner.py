from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from doc_chunk.workspace.layout import OutputWorkspace

from tender_insights.bid_diagnose.client import (
    BidDiagnoseClient,
    InvokeStructuredResult,
    create_bid_diagnose_client_from_env,
)
from tender_insights.bid_diagnose.loader import load_bid_diagnose_inputs
from tender_insights.bid_diagnose.models import (
    BidDiagnoseInvokeError,
    BidDiagnoseInvokeTimeoutError,
    BidDiagnoseRunResult,
    BidDiagnoseState,
    SegmentDiagnoseState,
    SegmentDiagnoseStepResult,
    TaskStepResult,
)
from tender_insights.bid_diagnose.tasks import TASK_DEFINITIONS
from tender_insights.bid_diagnose.writer import (
    init_bid_diagnose_dir,
    write_diagnose_result,
    write_run_state,
    write_segment_result,
)

MAX_RETRIES = 1


class BidDiagnoseClientProtocol(Protocol):
    def invoke(self, input: dict) -> InvokeStructuredResult: ...


class BidDiagnoseRunner:
    def __init__(
        self,
        *,
        client: BidDiagnoseClientProtocol,
        on_progress: Callable[[str, dict], None] | None = None,
    ) -> None:
        self._client = client
        self._on_progress = on_progress

    def run(self, state: BidDiagnoseState, sec_map: dict[int, str]) -> BidDiagnoseRunResult:
        result = BidDiagnoseRunResult(status="partial", state=state)
        total_segments = len(state.segments)

        for segment in state.segments:
            segment_state = SegmentDiagnoseState()
            sec_in_total = sec_map[segment.segment_index]
            step_results: list[TaskStepResult] = []

            for task in TASK_DEFINITIONS:
                if self._on_progress:
                    self._on_progress(
                        "bid_diagnose",
                        {
                            "message": (
                                f"标书诊断 分段 {segment.segment_index}/{total_segments} · "
                                f"{task.current_task}"
                            ),
                            "segment": segment.segment_index,
                            "total_segments": total_segments,
                            "task": task.current_task,
                        },
                    )

                last_error: Exception | None = None
                succeeded = False
                for attempt in range(MAX_RETRIES + 1):
                    try:
                        invoke_result = self._client.invoke(
                            state.to_invoke_input(
                                segment,
                                task,
                                segment_state,
                                sec_in_total=sec_in_total,
                            )
                        )
                        state.apply_output(task, invoke_result.output, segment_state)
                        step_results.append(
                            TaskStepResult(
                                current_task=task.current_task,
                                duration_ms=invoke_result.duration_ms,
                                attempt=attempt + 1,
                            )
                        )
                        succeeded = True
                        break
                    except BidDiagnoseInvokeTimeoutError as exc:
                        return self._failed_result(
                            result,
                            segment.segment_index,
                            task.current_task,
                            error_type="timeout",
                            error_message=str(exc),
                            elapsed_ms=exc.elapsed_ms,
                            configured_timeout_s=exc.configured_timeout_s,
                        )
                    except BidDiagnoseInvokeError as exc:
                        last_error = exc
                        if attempt >= MAX_RETRIES:
                            return self._failed_result(
                                result,
                                segment.segment_index,
                                task.current_task,
                                error_type="invoke_error",
                                error_message=str(exc),
                                elapsed_ms=exc.elapsed_ms,
                            )
                if not succeeded:
                    return self._failed_result(
                        result,
                        segment.segment_index,
                        task.current_task,
                        error_type="invoke_error",
                        error_message=str(last_error),
                    )

            result.completed_segments.append(segment.segment_index)
            result.segment_results.append(
                SegmentDiagnoseStepResult(
                    segment_index=segment.segment_index,
                    char_count=segment.char_count,
                    source_chunk_ids=list(segment.source_chunk_ids),
                    sec_in_total=sec_in_total,
                    import_diagnose=segment_state.import_diagnose,
                    segment_diagnose_result=segment_state.segment_diagnose_result,
                    steps=step_results,
                )
            )

        result.status = "completed"
        return result

    @staticmethod
    def _failed_result(
        result: BidDiagnoseRunResult,
        failed_segment: int,
        failed_task: str,
        *,
        error_type: str,
        error_message: str,
        elapsed_ms: int | None = None,
        configured_timeout_s: int | None = None,
    ) -> BidDiagnoseRunResult:
        result.status = "failed" if not result.completed_segments else "partial"
        result.failed_segment = failed_segment
        result.failed_task = failed_task
        result.error_type = error_type
        result.error_message = error_message
        result.elapsed_ms = elapsed_ms
        result.configured_timeout_s = configured_timeout_s
        return result


def run_bid_diagnose(
    workspace: OutputWorkspace,
    *,
    bid_background: str = "",
    client: BidDiagnoseClient | None = None,
    on_progress: Callable[[str, dict], None] | None = None,
    overwrite: bool = False,
    timeout_s: int | None = None,
) -> BidDiagnoseRunResult:
    analysis_report, segments, sec_map = load_bid_diagnose_inputs(workspace)
    state = BidDiagnoseState(
        bid_background=bid_background,
        analysis_report=analysis_report,
        diagnose_before="",
        segments=segments,
    )

    resolved_client = client
    if resolved_client is None:
        resolved_client = create_bid_diagnose_client_from_env()
        if timeout_s is not None:
            resolved_client = BidDiagnoseClient(
                base_url=resolved_client.base_url,
                api_key=resolved_client.api_key,
                timeout_s=timeout_s,
            )

    diag_dir = init_bid_diagnose_dir(workspace.root, overwrite=overwrite)
    runner = BidDiagnoseRunner(client=resolved_client, on_progress=on_progress)
    result = runner.run(state, sec_map)

    for segment_result in result.segment_results:
        write_segment_result(diag_dir, segment_result)
    write_run_state(diag_dir, result)
    if state.diagnose_before:
        write_diagnose_result(diag_dir, state.diagnose_before)

    return result
