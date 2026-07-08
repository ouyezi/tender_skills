from __future__ import annotations

import json
from pathlib import Path

from tender_insights.diagnosis.models import (
    ChunkSummaryOutput,
    DiagnosisRunResult,
    DiagnosisSegment,
    DiagnosisState,
    SegmentStepResult,
)
from tender_insights.diagnosis.writer import (
    init_diagnosis_dir,
    write_run_state,
    write_segment_result,
    write_segments_plan,
    write_total_summary,
    write_sec_in_total_index,
)


def test_init_diagnosis_dir_creates_structure(tmp_path: Path):
    loop_dir = init_diagnosis_dir(tmp_path, overwrite=False)
    assert loop_dir == tmp_path / "bid_summary"
    assert (loop_dir / "chunks").is_dir()


def test_write_segments_plan_and_step(tmp_path: Path):
    diag_dir = init_diagnosis_dir(tmp_path, overwrite=True)
    segments = [
        DiagnosisSegment(1, "a" * 9000, 9000, ["c1"], ["第一章"]),
    ]
    write_segments_plan(diag_dir, segments)

    step = SegmentStepResult(
        segment_index=1,
        output=ChunkSummaryOutput(
            current_summary="当前",
            total_summary="整体",
            sec_in_total="分段作用",
        ),
        duration_ms=100,
        attempt=1,
        char_count=9000,
        source_chunk_ids=["c1"],
    )
    write_segment_result(diag_dir, step)

    plan = json.loads((diag_dir / "segments.json").read_text(encoding="utf-8"))
    assert plan["total_segments"] == 1
    assert plan["segments"][0]["char_count"] == 9000

    chunk_file = diag_dir / "chunks" / "001_summary.json"
    payload = json.loads(chunk_file.read_text(encoding="utf-8"))
    assert payload["total_summary"] == "整体"
    assert payload["sec_in_total"] == "分段作用"


def test_write_sec_in_total_index(tmp_path: Path):
    diag_dir = init_diagnosis_dir(tmp_path, overwrite=True)
    steps = [
        SegmentStepResult(
            segment_index=1,
            output=ChunkSummaryOutput(
                current_summary="c1",
                total_summary="t1",
                sec_in_total="作用1",
            ),
            duration_ms=10,
            attempt=1,
            char_count=100,
            source_chunk_ids=["c1"],
        ),
        SegmentStepResult(
            segment_index=2,
            output=ChunkSummaryOutput(
                current_summary="c2",
                total_summary="t2",
                sec_in_total="作用2",
            ),
            duration_ms=20,
            attempt=1,
            char_count=200,
            source_chunk_ids=["c2"],
        ),
    ]
    write_sec_in_total_index(diag_dir, steps)
    payload = json.loads((diag_dir / "sec_in_total.json").read_text(encoding="utf-8"))
    assert payload["segments"][0]["sec_in_total"] == "作用1"
    assert payload["segments"][1]["sec_in_total"] == "作用2"


def test_write_run_state_and_total_summary(tmp_path: Path):
    diag_dir = init_diagnosis_dir(tmp_path, overwrite=True)
    state = DiagnosisState(tender_report="r", preview_summary="整体", segments=[])
    result = DiagnosisRunResult(status="completed", state=state, completed_segments=[1])
    write_run_state(diag_dir, result)
    write_total_summary(diag_dir, "整体")

    run_state = json.loads((diag_dir / "run_state.json").read_text(encoding="utf-8"))
    assert run_state["status"] == "completed"
    assert (diag_dir / "total_summary.md").read_text(encoding="utf-8") == "整体"
