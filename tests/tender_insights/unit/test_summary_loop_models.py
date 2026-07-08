from __future__ import annotations

import pytest

from tender_insights.summary_loop.models import (
    LoopRunResult,
    LoopState,
    SummaryLoopError,
    SummaryLoopInvokeError,
    SummaryLoopInvokeTimeoutError,
    TaskDefinition,
)


def test_loop_state_to_invoke_input_includes_task_fields():
    state = LoopState(tender_info="正文", task_background="背景")
    task = TaskDefinition(
        step_index=1,
        current_task="get_tender_summary",
        task_skills="概要提取",
        output_requirement="输出 Markdown 概要",
        output_field="tender_summary",
        step_filename="01_tender_summary.txt",
    )
    payload = state.to_invoke_input(task)
    assert payload["tender_info"] == "正文"
    assert payload["task_background"] == "背景"
    assert payload["current_task"] == "get_tender_summary"
    assert payload["tender_summary"] == ""


def test_loop_state_to_invoke_input_includes_api_fields():
    state = LoopState(
        tender_info="正文",
        task_background="背景",
        needs_clarify="需澄清",
        diagnosis_criteria="诊断",
        analysis_report="报告",
    )
    task = TaskDefinition(
        step_index=6,
        current_task="diagnosis_criteria",
        task_skills="诊断",
        output_requirement="输出诊断",
        output_field="diagnosis_criteria",
        step_filename="06_diagnosis_criteria.md",
    )
    payload = state.to_invoke_input(task)
    assert payload["needs_clearify"] == "需澄清"
    assert payload["analysisi_report"] == "报告"
    assert payload["diagnosis_criteria"] == "诊断"


def test_loop_state_apply_output_updates_field():
    state = LoopState(tender_info="x", task_background="y")
    task = TaskDefinition(
        step_index=1,
        current_task="get_tender_summary",
        task_skills="s",
        output_requirement="r",
        output_field="tender_summary",
        step_filename="01_tender_summary.txt",
    )
    state.apply_output(task, "概要内容")
    assert state.tender_summary == "概要内容"


def test_summary_loop_invoke_timeout_error_is_subclass():
    with pytest.raises(SummaryLoopInvokeError):
        raise SummaryLoopInvokeTimeoutError("timeout", elapsed_ms=180000, configured_timeout_s=600)
