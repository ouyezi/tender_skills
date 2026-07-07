from __future__ import annotations

import json
import shutil
from pathlib import Path

from tender_insights.diagnosis.models import DiagnosisRunResult, DiagnosisSegment, SegmentStepResult
from tender_insights.diagnosis.segment_optimizer import MAX_CHARS, MIN_CHARS


def init_diagnosis_dir(workspace_root: Path, *, overwrite: bool) -> Path:
    diag_dir = workspace_root / "diagnosis"
    if diag_dir.exists():
        if not overwrite:
            raise FileExistsError(f"diagnosis already exists: {diag_dir}")
        shutil.rmtree(diag_dir)
    (diag_dir / "chunks").mkdir(parents=True, exist_ok=True)
    return diag_dir


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
