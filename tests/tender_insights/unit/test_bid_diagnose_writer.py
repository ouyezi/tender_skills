from __future__ import annotations

import json
from pathlib import Path

import pytest

from tender_insights.bid_diagnose.models import (
    BidDiagnoseRunResult,
    BidDiagnoseState,
    SegmentDiagnoseStepResult,
    TaskStepResult,
)
from tender_insights.bid_diagnose.writer import (
    init_bid_diagnose_dir,
    write_diagnose_result,
    write_run_state,
    write_segment_result,
)


def test_init_bid_diagnose_dir_creates_structure(tmp_path: Path):
    root = tmp_path / "ws"
    root.mkdir()
    diag_dir = init_bid_diagnose_dir(root, overwrite=False)
    assert diag_dir == root / "bid_diagnose"
    assert (diag_dir / "segments").is_dir()


def test_init_raises_when_exists_without_overwrite(tmp_path: Path):
    root = tmp_path / "ws"
    (root / "bid_diagnose").mkdir(parents=True)
    with pytest.raises(FileExistsError):
        init_bid_diagnose_dir(root, overwrite=False)


def test_write_segment_result_payload(tmp_path: Path):
    diag_dir = init_bid_diagnose_dir(tmp_path / "ws", overwrite=True)
    step = SegmentDiagnoseStepResult(
        segment_index=1,
        char_count=100,
        source_chunk_ids=["c1"],
        sec_in_total="作用",
        import_diagnose="重点",
        segment_diagnose_result="段结果",
        steps=[TaskStepResult("import_diagnose", 10, 1)],
    )
    path = write_segment_result(diag_dir, step)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["segment_index"] == 1
    assert payload["import_diagnose"] == "重点"
    assert payload["segment_diagnose_result"] == "段结果"


def test_write_diagnose_result_md(tmp_path: Path):
    diag_dir = init_bid_diagnose_dir(tmp_path / "ws2", overwrite=True)
    path = write_diagnose_result(diag_dir, "# 累积\n")
    assert path.read_text(encoding="utf-8") == "# 累积\n"


def test_write_run_state(tmp_path: Path):
    diag_dir = init_bid_diagnose_dir(tmp_path / "ws3", overwrite=True)
    state = BidDiagnoseState(bid_background="", analysis_report="r", diagnose_before="", segments=[])
    result = BidDiagnoseRunResult(status="completed", state=state, completed_segments=[1])
    path = write_run_state(diag_dir, result)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["status"] == "completed"
    assert data["completed_segments"] == [1]
