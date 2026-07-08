from __future__ import annotations

import json
from pathlib import Path

import pytest

from doc_chunk.workspace.layout import OutputWorkspace
from tender_insights.bid_diagnose.loader import load_bid_diagnose_inputs
from tender_insights.bid_diagnose.models import BidDiagnosePrerequisiteError
from tender_insights.diagnosis.segment_optimizer import optimize_segments


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


def _write_chunk(ws: OutputWorkspace, markdown: str, chunk_id: str = "chunk-001") -> None:
    chunks_dir = ws.root / "chunks"
    chunks_dir.mkdir(exist_ok=True)
    chunk_path = "0001.json"
    (chunks_dir / chunk_path).write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "chunk_id": chunk_id,
                "title": "第一章",
                "markdown": markdown,
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
                        "chunk_id": chunk_id,
                        "title": "第一章",
                        "path": chunk_path,
                        "section_path": ["第一章"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def _write_bid_summary(ws: OutputWorkspace, segments_payload: list[dict], *, status: str = "completed") -> None:
    summary_dir = ws.root / "bid_summary"
    summary_dir.mkdir(parents=True)
    (summary_dir / "total_summary.md").write_text("# 概要\n", encoding="utf-8")
    (summary_dir / "run_state.json").write_text(
        json.dumps({"status": status, "completed_segments": [1]}),
        encoding="utf-8",
    )
    (summary_dir / "sec_in_total.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "segments": [
                    {"segment_index": s["segment_index"], "sec_in_total": f"作用{s['segment_index']}"}
                    for s in segments_payload
                ],
            }
        ),
        encoding="utf-8",
    )
    (summary_dir / "segments.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "min_chars": 8000,
                "max_chars": 15000,
                "total_segments": len(segments_payload),
                "segments": segments_payload,
            }
        ),
        encoding="utf-8",
    )


def test_loader_raises_when_bid_summary_missing(tmp_path: Path):
    ws = _minimal_workspace(tmp_path)
    with pytest.raises(BidDiagnosePrerequisiteError, match="bid_summary"):
        load_bid_diagnose_inputs(ws)


def test_loader_raises_when_bid_summary_not_completed(tmp_path: Path):
    ws = _minimal_workspace(tmp_path)
    _write_chunk(ws, "x" * 9000)
    from doc_chunk.models.chunk import ContentChunk

    chunks = [
        ContentChunk.model_validate_json((ws.root / "chunks" / "0001.json").read_text(encoding="utf-8"))
    ]
    segments = optimize_segments(chunks)
    payload = [
        {
            "segment_index": s.segment_index,
            "char_count": s.char_count,
            "source_chunk_ids": s.source_chunk_ids,
            "section_path": s.section_path,
        }
        for s in segments
    ]
    _write_bid_summary(ws, payload, status="failed")
    with pytest.raises(BidDiagnosePrerequisiteError, match="completed"):
        load_bid_diagnose_inputs(ws)


def test_loader_returns_aligned_segments_and_maps(tmp_path: Path):
    ws = _minimal_workspace(tmp_path)
    _write_chunk(ws, "x" * 9000)
    from doc_chunk.models.chunk import ContentChunk

    chunks = [
        ContentChunk.model_validate_json((ws.root / "chunks" / "0001.json").read_text(encoding="utf-8"))
    ]
    segments = optimize_segments(chunks)
    payload = [
        {
            "segment_index": s.segment_index,
            "char_count": s.char_count,
            "source_chunk_ids": s.source_chunk_ids,
            "section_path": s.section_path,
        }
        for s in segments
    ]
    _write_bid_summary(ws, payload)
    analysis_report, loaded_segments, sec_map = load_bid_diagnose_inputs(ws)
    assert analysis_report == "# 概要\n"
    assert len(loaded_segments) == len(segments)
    assert loaded_segments[0].char_count == segments[0].char_count
    assert sec_map[1].startswith("作用")
