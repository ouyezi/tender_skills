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
)


def test_init_diagnosis_dir_creates_structure(tmp_path: Path):
    loop_dir = init_diagnosis_dir(tmp_path, overwrite=False)
    assert loop_dir == tmp_path / "diagnosis"
    assert (loop_dir / "chunks").is_dir()


def test_write_segments_plan_and_step(tmp_path: Path):
    diag_dir = init_diagnosis_dir(tmp_path, overwrite=True)
    segments = [
        DiagnosisSegment(1, "a" * 9000, 9000, ["c1"], ["第一章"]),
    ]
    write_segments_plan(diag_dir, segments)

    step = SegmentStepResult(
        segment_index=1,
        output=ChunkSummaryOutput(current_summary="当前", total_summary="整体"),
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


def test_write_run_state_and_total_summary(tmp_path: Path):
    diag_dir = init_diagnosis_dir(tmp_path, overwrite=True)
    state = DiagnosisState(tender_report="r", preview_summary="整体", segments=[])
    result = DiagnosisRunResult(status="completed", state=state, completed_segments=[1])
    write_run_state(diag_dir, result)
    write_total_summary(diag_dir, "整体")

    run_state = json.loads((diag_dir / "run_state.json").read_text(encoding="utf-8"))
    assert run_state["status"] == "completed"
    assert (diag_dir / "total_summary.md").read_text(encoding="utf-8") == "整体"
