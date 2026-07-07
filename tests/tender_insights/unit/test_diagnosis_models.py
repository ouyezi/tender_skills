from __future__ import annotations

import pytest

from tender_insights.diagnosis.models import (
    ChunkSummaryOutput,
    DiagnosisInvokeError,
    DiagnosisInvokeTimeoutError,
    DiagnosisPrerequisiteError,
    DiagnosisRunResult,
    DiagnosisSegment,
    DiagnosisState,
)


def test_diagnosis_state_to_invoke_input():
    seg = DiagnosisSegment(
        segment_index=2,
        markdown="正文",
        char_count=2,
        source_chunk_ids=["c1"],
        section_path=["第一章"],
    )
    state = DiagnosisState(
        tender_report="解读报告",
        preview_summary="上一段整体概述",
        segments=[DiagnosisSegment(1, "a", 1, ["c0"], []), seg],
    )
    payload = state.to_invoke_input(seg)
    assert payload == {
        "chunk": "正文",
        "tender_report": "解读报告",
        "total_chunk_count": "2",
        "current_count": "2",
        "preview_summary": "上一段整体概述",
    }


def test_diagnosis_state_apply_output_updates_preview():
    state = DiagnosisState(tender_report="r", preview_summary="", segments=[])
    out = ChunkSummaryOutput(current_summary="当前", total_summary="整体")
    state.apply_output(out)
    assert state.preview_summary == "整体"


def test_diagnosis_run_result_to_run_state_dict_includes_timeout_fields():
    state = DiagnosisState(tender_report="r", preview_summary="", segments=[])
    result = DiagnosisRunResult(
        status="failed",
        state=state,
        failed_segment=2,
        error_type="timeout",
        error_message="timeout",
        elapsed_ms=180000,
        configured_timeout_s=600,
    )
    data = result.to_run_state_dict()
    assert data["failed_segment"] == 2
    assert data["elapsed_ms"] == 180000
    assert data["configured_timeout_s"] == 600


def test_diagnosis_invoke_timeout_error_is_subclass():
    with pytest.raises(DiagnosisInvokeError):
        raise DiagnosisInvokeTimeoutError("timeout", elapsed_ms=180000, configured_timeout_s=600)


def test_diagnosis_prerequisite_error_message():
    err = DiagnosisPrerequisiteError("缺少 report.md")
    assert "report.md" in str(err)
