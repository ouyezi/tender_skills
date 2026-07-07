from __future__ import annotations

import json
from pathlib import Path

from tender_insights.summary_loop.models import LoopRunResult, LoopState, StepResult
from tender_insights.summary_loop.writer import (
    init_loop_dir,
    write_results,
    write_run_state,
    write_step,
)


def test_init_loop_dir_creates_structure(tmp_path: Path):
    loop_dir = init_loop_dir(tmp_path, overwrite=False)
    assert loop_dir == tmp_path / "summary_loop"
    assert (loop_dir / "steps").is_dir()


def test_write_step_and_results(tmp_path: Path):
    loop_dir = init_loop_dir(tmp_path, overwrite=True)
    write_step(loop_dir, "01_tender_summary.txt", "概要")
    result = LoopRunResult(
        status="completed",
        state=LoopState(
            tender_info="i",
            task_background="b",
            tender_summary="概要",
            analysis_report="报告",
        ),
        completed_steps=["get_tender_summary"],
        step_results=[StepResult("get_tender_summary", "概要", 100, 1)],
    )
    write_run_state(loop_dir, result)
    write_results(loop_dir, result)

    assert (loop_dir / "steps" / "01_tender_summary.txt").read_text(encoding="utf-8") == "概要"
    run_state = json.loads((loop_dir / "run_state.json").read_text(encoding="utf-8"))
    assert run_state["status"] == "completed"
    results = json.loads((loop_dir / "results.json").read_text(encoding="utf-8"))
    assert results["tender_summary"] == "概要"
    assert results["schema_version"] == "1.1"
    assert (loop_dir / "report.md").read_text(encoding="utf-8") == "报告"
    assert (loop_dir / "analysis_report.md").read_text(encoding="utf-8") == "报告"
