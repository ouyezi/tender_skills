from __future__ import annotations

import json
import shutil
from pathlib import Path

from tender_insights.summary_loop.models import LoopRunResult


def init_loop_dir(workspace_root: Path, *, overwrite: bool) -> Path:
    loop_dir = workspace_root / "summary_loop"
    if loop_dir.exists():
        if not overwrite:
            raise FileExistsError(f"summary_loop already exists: {loop_dir}")
        shutil.rmtree(loop_dir)
    (loop_dir / "steps").mkdir(parents=True, exist_ok=True)
    return loop_dir


def write_step(loop_dir: Path, filename: str, content: str) -> Path:
    dest = loop_dir / "steps" / filename
    dest.write_text(content, encoding="utf-8")
    return dest


def write_run_state(loop_dir: Path, result: LoopRunResult) -> Path:
    dest = loop_dir / "run_state.json"
    dest.write_text(
        json.dumps(result.to_run_state_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return dest


def write_results(loop_dir: Path, result: LoopRunResult) -> Path:
    dest = loop_dir / "results.json"
    dest.write_text(
        json.dumps(result.to_results_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if result.state.analysis_report:
        (loop_dir / "report.md").write_text(result.state.analysis_report, encoding="utf-8")
        (loop_dir / "analysis_report.md").write_text(result.state.analysis_report, encoding="utf-8")
    return dest
