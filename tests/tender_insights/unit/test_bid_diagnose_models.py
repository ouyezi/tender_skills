from __future__ import annotations

import pytest

from tender_insights.bid_diagnose.models import (
    BidDiagnoseInvokeError,
    BidDiagnoseInvokeTimeoutError,
    BidDiagnoseRunResult,
    BidDiagnoseState,
    SegmentDiagnoseState,
    TaskDefinition,
)
from tender_insights.diagnosis.models import DiagnosisSegment


def _segment(index: int = 1) -> DiagnosisSegment:
    return DiagnosisSegment(
        segment_index=index,
        markdown=f"chunk-{index}",
        char_count=len(f"chunk-{index}"),
        source_chunk_ids=[f"c{index}"],
        section_path=["第一章"],
    )


def test_bid_diagnose_state_to_invoke_input_for_import_diagnose():
    task = TaskDefinition(
        step_index=1,
        current_task="import_diagnose",
        task_skills="skills",
        output_requirement="req",
        output_field="import_diagnose",
    )
    state = BidDiagnoseState(
        bid_background="bg",
        analysis_report="report",
        diagnose_before="",
        segments=[_segment()],
    )
    seg_state = SegmentDiagnoseState()
    payload = state.to_invoke_input(_segment(), task, seg_state, sec_in_total="段作用")
    assert payload["bid_background"] == "bg"
    assert payload["analysis_report"] == "report"
    assert payload["diagnose_before"] == ""
    assert payload["sec_in_total"] == "段作用"
    assert payload["current_chunk"] == "chunk-1"
    assert payload["import_diagnose"] == ""
    assert payload["diagnose_result"] == ""
    assert payload["current_task"] == "import_diagnose"
    assert payload["task_skills"] == "skills"
    assert payload["output_requirement"] == "req"


def test_bid_diagnose_state_apply_output_import_diagnose():
    task = TaskDefinition(
        step_index=1,
        current_task="import_diagnose",
        task_skills="s",
        output_requirement="r",
        output_field="import_diagnose",
    )
    state = BidDiagnoseState(bid_background="", analysis_report="r", diagnose_before="", segments=[])
    seg_state = SegmentDiagnoseState()
    state.apply_output(task, {"import_diagnose": "重点"}, seg_state)
    assert seg_state.import_diagnose == "重点"
    assert state.diagnose_before == ""


def test_bid_diagnose_state_apply_output_update_diagnose_rolls_before():
    task = TaskDefinition(
        step_index=3,
        current_task="update_diagnose",
        task_skills="s",
        output_requirement="r",
        output_field="diagnose_result",
    )
    state = BidDiagnoseState(bid_background="", analysis_report="r", diagnose_before="old", segments=[])
    seg_state = SegmentDiagnoseState(segment_diagnose_result="seg")
    state.apply_output(task, {"diagnose_result": "累积新"}, seg_state)
    assert state.diagnose_before == "累积新"


def test_bid_diagnose_run_result_includes_failed_task():
    state = BidDiagnoseState(bid_background="", analysis_report="r", diagnose_before="", segments=[])
    result = BidDiagnoseRunResult(
        status="failed",
        state=state,
        failed_segment=2,
        failed_task="diagnose_result",
        error_type="invoke_error",
        error_message="boom",
    )
    data = result.to_run_state_dict()
    assert data["failed_segment"] == 2
    assert data["failed_task"] == "diagnose_result"


def test_bid_diagnose_invoke_timeout_is_subclass():
    with pytest.raises(BidDiagnoseInvokeError):
        raise BidDiagnoseInvokeTimeoutError("timeout", elapsed_ms=1, configured_timeout_s=600)
