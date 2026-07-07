from __future__ import annotations

import json
from pathlib import Path

import pytest

from doc_chunk.workspace.layout import OutputWorkspace
from tender_insights.diagnosis.loader import load_diagnosis_inputs
from tender_insights.diagnosis.models import DiagnosisPrerequisiteError


def _minimal_workspace(tmp_path: Path) -> OutputWorkspace:
    root = tmp_path / "ws"
    root.mkdir()
    (root / "manifest.json").write_text("{}", encoding="utf-8")
    (root / "content.md").write_text("# doc\n", encoding="utf-8")
    (root / "outline.json").write_text(
        json.dumps({"schema_version": "1.0", "strategy": "heading_heuristic", "nodes": []}),
        encoding="utf-8",
    )
    return OutputWorkspace.open_existing(root)


def test_loader_raises_when_report_missing(tmp_path: Path):
    ws = _minimal_workspace(tmp_path)
    chunks_dir = ws.root / "chunks"
    chunks_dir.mkdir()
    (chunks_dir / "index.json").write_text(
        json.dumps({"schema_version": "1.0", "chunks": []}),
        encoding="utf-8",
    )
    with pytest.raises(DiagnosisPrerequisiteError, match="summary_loop/report.md"):
        load_diagnosis_inputs(ws)


def test_loader_raises_when_chunks_missing(tmp_path: Path):
    ws = _minimal_workspace(tmp_path)
    loop_dir = ws.root / "summary_loop"
    loop_dir.mkdir()
    (loop_dir / "report.md").write_text("# 解读\n", encoding="utf-8")
    with pytest.raises(DiagnosisPrerequisiteError, match="chunks/"):
        load_diagnosis_inputs(ws)


def test_loader_returns_report_and_chunks(tmp_path: Path):
    ws = _minimal_workspace(tmp_path)
    loop_dir = ws.root / "summary_loop"
    loop_dir.mkdir()
    (loop_dir / "report.md").write_text("# 解读报告\n", encoding="utf-8")

    chunks_dir = ws.root / "chunks"
    chunks_dir.mkdir()
    chunk_path = "0001.json"
    (chunks_dir / chunk_path).write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "chunk_id": "chunk-001",
                "title": "第一章",
                "markdown": "正文内容",
            }
        ),
        encoding="utf-8",
    )
    (chunks_dir / "index.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "chunks": [
                    {
                        "chunk_id": "chunk-001",
                        "title": "第一章",
                        "path": chunk_path,
                        "section_path": ["第一章"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    report, chunks = load_diagnosis_inputs(ws)
    assert report == "# 解读报告\n"
    assert len(chunks) == 1
    assert chunks[0].chunk_id == "chunk-001"
