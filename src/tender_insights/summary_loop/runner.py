from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from doc_chunk.workspace.layout import OutputWorkspace

from tender_insights.common.content_source import prepare_interpret_source
from tender_insights.config import InsightsConfig
from tender_insights.summary_loop.client import (
    InvokeTextResult,
    SummaryLoopClient,
    create_summary_loop_client_from_env,
)
from tender_insights.summary_loop.models import (
    LoopRunResult,
    LoopState,
    StepResult,
    SummaryLoopInvokeError,
    SummaryLoopInvokeTimeoutError,
)
from tender_insights.summary_loop.tasks import TASK_DEFINITIONS
from tender_insights.summary_loop.writer import init_loop_dir, write_results, write_run_state, write_step

MAX_RETRIES = 1


class SummaryLoopClientProtocol(Protocol):
    def invoke(self, input: dict) -> InvokeTextResult: ...


class SummaryLoopRunner:
    def __init__(
        self,
        *,
        client: SummaryLoopClientProtocol,
        on_progress: Callable[[str, dict], None] | None = None,
    ) -> None:
        self._client = client
        self._on_progress = on_progress

    def run(self, state: LoopState) -> LoopRunResult:
        result = LoopRunResult(status="partial", state=state)
        total = len(TASK_DEFINITIONS)
        for index, task in enumerate(TASK_DEFINITIONS, start=1):
            if self._on_progress:
                self._on_progress(
                    "summary_loop",
                    {
                        "message": f"执行 {task.current_task}",
                        "current": index,
                        "total": total,
                        "step": task.current_task,
                    },
                )
            last_error: Exception | None = None
            succeeded = False
            for attempt in range(MAX_RETRIES + 1):
                try:
                    invoke_result = self._client.invoke(state.to_invoke_input(task))
                    state.apply_output(task, invoke_result.output)
                    result.completed_steps.append(task.current_task)
                    result.step_results.append(
                        StepResult(
                            current_task=task.current_task,
                            output=invoke_result.output,
                            duration_ms=invoke_result.duration_ms,
                            attempt=attempt + 1,
                        )
                    )
                    succeeded = True
                    break
                except SummaryLoopInvokeTimeoutError as exc:
                    return self._failed_result(
                        result,
                        task.current_task,
                        error_type="timeout",
                        error_message=str(exc),
                        elapsed_ms=exc.elapsed_ms,
                        configured_timeout_s=exc.configured_timeout_s,
                    )
                except SummaryLoopInvokeError as exc:
                    last_error = exc
                    if attempt >= MAX_RETRIES:
                        return self._failed_result(
                            result,
                            task.current_task,
                            error_type="invoke_error",
                            error_message=str(exc),
                            elapsed_ms=exc.elapsed_ms,
                        )
            if not succeeded:
                return self._failed_result(
                    result,
                    task.current_task,
                    error_type="invoke_error",
                    error_message=str(last_error),
                )

        result.status = "completed"
        return result

    @staticmethod
    def _failed_result(
        result: LoopRunResult,
        failed_step: str,
        *,
        error_type: str,
        error_message: str,
        elapsed_ms: int | None = None,
        configured_timeout_s: int | None = None,
    ) -> LoopRunResult:
        result.status = "failed" if not result.completed_steps else "partial"
        result.failed_step = failed_step
        result.error_type = error_type
        result.error_message = error_message
        result.elapsed_ms = elapsed_ms
        result.configured_timeout_s = configured_timeout_s
        return result


def run_summary_loop(
    workspace: OutputWorkspace,
    *,
    task_background: str,
    client: SummaryLoopClient | None = None,
    config: InsightsConfig | None = None,
    on_progress: Callable[[str, dict], None] | None = None,
    overwrite: bool = False,
    timeout_s: int | None = None,
) -> LoopRunResult:
    config = config or InsightsConfig.from_env()
    resolved_client = client
    if resolved_client is None:
        resolved_client = create_summary_loop_client_from_env()
        if timeout_s is not None:
            resolved_client = SummaryLoopClient(
                base_url=resolved_client.base_url,
                api_key=resolved_client.api_key,
                timeout_s=timeout_s,
            )

    source = prepare_interpret_source(workspace, config=config)
    state = LoopState(tender_info=source.markdown, task_background=task_background)
    loop_dir = init_loop_dir(workspace.root, overwrite=overwrite)

    runner = SummaryLoopRunner(client=resolved_client, on_progress=on_progress)
    result = runner.run(state)

    for step_result, task in zip(result.step_results, TASK_DEFINITIONS[: len(result.step_results)], strict=False):
        write_step(loop_dir, task.step_filename, step_result.output)

    write_run_state(loop_dir, result)
    write_results(loop_dir, result)
    return result
