from __future__ import annotations

import json
import shutil
from pathlib import Path

from tender_insights.bid_diagnose.models import BidDiagnoseRunResult, SegmentDiagnoseStepResult, TaskStepResult


def init_bid_diagnose_dir(workspace_root: Path, *, overwrite: bool) -> Path:
    diag_dir = workspace_root / "bid_diagnose"
    if diag_dir.exists():
        if not overwrite:
            raise FileExistsError(f"bid_diagnose already exists: {diag_dir}")
        shutil.rmtree(diag_dir)
    (diag_dir / "segments").mkdir(parents=True, exist_ok=True)
    return diag_dir


def write_segment_result(diag_dir: Path, step: SegmentDiagnoseStepResult) -> Path:
    dest = diag_dir / "segments" / f"{step.segment_index:03d}_diagnose.json"
    payload = {
        "schema_version": "1.0",
        "segment_index": step.segment_index,
        "char_count": step.char_count,
        "source_chunk_ids": step.source_chunk_ids,
        "sec_in_total": step.sec_in_total,
        "import_diagnose": step.import_diagnose,
        "segment_diagnose_result": step.segment_diagnose_result,
        "steps": [
            {
                "current_task": s.current_task,
                "duration_ms": s.duration_ms,
                "attempt": s.attempt,
            }
            for s in step.steps
        ],
    }
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return dest


def write_run_state(diag_dir: Path, result: BidDiagnoseRunResult) -> Path:
    dest = diag_dir / "run_state.json"
    dest.write_text(
        json.dumps(result.to_run_state_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return dest


def write_diagnose_result(diag_dir: Path, diagnose_result: str) -> Path:
    dest = diag_dir / "diagnose_result.md"
    dest.write_text(diagnose_result, encoding="utf-8")
    return dest
