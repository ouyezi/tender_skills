from __future__ import annotations

import json
import shutil
from pathlib import Path

from tender_insights.diagnosis.models import DiagnosisRunResult, DiagnosisSegment, SegmentStepResult
from tender_insights.diagnosis.segment_optimizer import MAX_CHARS, MIN_CHARS


def init_diagnosis_dir(workspace_root: Path, *, overwrite: bool) -> Path:
    summary_dir = workspace_root / "bid_summary"
    if summary_dir.exists():
        if not overwrite:
            raise FileExistsError(f"bid_summary already exists: {summary_dir}")
        shutil.rmtree(summary_dir)
    (summary_dir / "chunks").mkdir(parents=True, exist_ok=True)
    return summary_dir


def write_segments_plan(diag_dir: Path, segments: list[DiagnosisSegment]) -> Path:
    dest = diag_dir / "segments.json"
    payload = {
        "schema_version": "1.0",
        "min_chars": MIN_CHARS,
        "max_chars": MAX_CHARS,
        "total_segments": len(segments),
        "segments": [
            {
                "segment_index": s.segment_index,
                "char_count": s.char_count,
                "source_chunk_ids": s.source_chunk_ids,
                "section_path": s.section_path,
            }
            for s in segments
        ],
    }
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return dest


def write_segment_result(diag_dir: Path, step: SegmentStepResult) -> Path:
    dest = diag_dir / "chunks" / f"{step.segment_index:03d}_summary.json"
    payload = {
        "schema_version": "1.0",
        "segment_index": step.segment_index,
        "char_count": step.char_count,
        "source_chunk_ids": step.source_chunk_ids,
        "current_summary": step.output.current_summary,
        "total_summary": step.output.total_summary,
        "sec_in_total": step.output.sec_in_total,
        "duration_ms": step.duration_ms,
        "attempt": step.attempt,
    }
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return dest


def write_run_state(diag_dir: Path, result: DiagnosisRunResult) -> Path:
    dest = diag_dir / "run_state.json"
    dest.write_text(
        json.dumps(result.to_run_state_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return dest


def write_total_summary(diag_dir: Path, total_summary: str) -> Path:
    dest = diag_dir / "total_summary.md"
    dest.write_text(total_summary, encoding="utf-8")
    return dest


def write_sec_in_total_index(diag_dir: Path, step_results: list[SegmentStepResult]) -> Path:
    dest = diag_dir / "sec_in_total.json"
    payload = {
        "schema_version": "1.0",
        "segments": [
            {
                "segment_index": step.segment_index,
                "sec_in_total": step.output.sec_in_total,
            }
            for step in step_results
        ],
    }
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return dest
