from __future__ import annotations

import json
from pathlib import Path

from doc_chunk.workspace.layout import OutputWorkspace

from tender_insights.api import render_interpretation_report
from tender_insights.interpret.models import InterpretationFile, InterpretationOverview
from tender_insights.interpret.render import render_interpretation_markdown


def test_render_includes_overview_and_sections() -> None:
    data = InterpretationFile(
        source_workspace="/tmp/ws",
        overview=InterpretationOverview(
            summary="总览",
            disqualification_summary="废标概要",
            scoring_summary="得分概要",
            bid_risk_summary="风险概要",
            directory_summary="目录概要",
        ),
    )
    md = render_interpretation_markdown(data)
    assert "# 招标解读报告" in md
    assert "## 废标项" in md
    assert "总览" in md


def test_render_interpretation_report_writes_file(tmp_path: Path) -> None:
    ws_root = tmp_path / "ws"
    ws_root.mkdir()
    (ws_root / "manifest.json").write_text("{}", encoding="utf-8")
    (ws_root / "content.md").write_text("# x\n", encoding="utf-8")
    (ws_root / "outline.json").write_text(
        json.dumps({"schema_version": "1.0", "strategy": "heading_heuristic", "nodes": []}),
        encoding="utf-8",
    )
    interpretation = InterpretationFile(
        source_workspace=str(ws_root),
        overview=InterpretationOverview(
            summary="概要",
            disqualification_summary="",
            scoring_summary="",
            bid_risk_summary="",
            directory_summary="",
        ),
    )
    (ws_root / "interpretation.json").write_text(
        interpretation.model_dump_json(indent=2),
        encoding="utf-8",
    )
    ws = OutputWorkspace.open_existing(ws_root)
    dest = render_interpretation_report(ws)
    assert dest.exists()
    assert "概要" in dest.read_text(encoding="utf-8")
