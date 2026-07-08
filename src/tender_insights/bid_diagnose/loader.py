from __future__ import annotations

import json

from doc_chunk.models.chunk import ChunkIndex, ContentChunk
from doc_chunk.workspace.layout import OutputWorkspace

from tender_insights.bid_diagnose.models import BidDiagnosePrerequisiteError
from tender_insights.diagnosis.models import DiagnosisSegment
from tender_insights.diagnosis.segment_optimizer import optimize_segments

_BID_SUMMARY_HINT = (
    "缺少 bid_summary/ 或关键文件，请先运行：\n"
    "  tender-insights bid-summary <workspace> --overwrite"
)
_CHUNKS_HINT = (
    "缺少 chunks/，请先运行：\n"
    "  doc-chunk pipeline <file> -o <workspace> --overwrite"
)


def load_bid_diagnose_inputs(
    workspace: OutputWorkspace,
) -> tuple[str, list[DiagnosisSegment], dict[int, str]]:
    summary_dir = workspace.root / "bid_summary"
    required = [
        summary_dir / "segments.json",
        summary_dir / "sec_in_total.json",
        summary_dir / "total_summary.md",
        summary_dir / "run_state.json",
    ]
    if not summary_dir.is_dir() or not all(p.is_file() for p in required):
        raise BidDiagnosePrerequisiteError(_BID_SUMMARY_HINT)

    run_state = json.loads((summary_dir / "run_state.json").read_text(encoding="utf-8"))
    if run_state.get("status") != "completed":
        raise BidDiagnosePrerequisiteError(
            "bid-summary 尚未成功完成（run_state.status != completed），请先重跑 bid-summary"
        )

    analysis_report = (summary_dir / "total_summary.md").read_text(encoding="utf-8")

    sec_payload = json.loads((summary_dir / "sec_in_total.json").read_text(encoding="utf-8"))
    sec_map: dict[int, str] = {}
    for entry in sec_payload.get("segments", []):
        sec_map[int(entry["segment_index"])] = str(entry["sec_in_total"])

    plan = json.loads((summary_dir / "segments.json").read_text(encoding="utf-8"))
    planned_segments = plan.get("segments", [])

    index_path = workspace.chunks_dir / "index.json"
    if not index_path.is_file():
        raise BidDiagnosePrerequisiteError(_CHUNKS_HINT)

    index = ChunkIndex.model_validate_json(index_path.read_text(encoding="utf-8"))
    chunks: list[ContentChunk] = []
    for entry in index.chunks:
        chunk_path = workspace.chunks_dir / entry.path
        if chunk_path.is_file():
            chunks.append(ContentChunk.model_validate(json.loads(chunk_path.read_text(encoding="utf-8"))))
    if not chunks:
        raise BidDiagnosePrerequisiteError(_CHUNKS_HINT)

    rebuilt = optimize_segments(chunks)
    if len(rebuilt) != len(planned_segments):
        raise BidDiagnosePrerequisiteError(
            "分段计划与 bid-summary 不一致（段数不同），请重跑 bid-summary"
        )

    for rebuilt_seg, planned in zip(rebuilt, planned_segments, strict=True):
        if rebuilt_seg.segment_index != planned["segment_index"]:
            raise BidDiagnosePrerequisiteError("分段计划与 bid-summary 不一致，请重跑 bid-summary")
        if rebuilt_seg.char_count != planned["char_count"]:
            raise BidDiagnosePrerequisiteError("分段计划与 bid-summary 不一致，请重跑 bid-summary")
        if rebuilt_seg.source_chunk_ids != planned["source_chunk_ids"]:
            raise BidDiagnosePrerequisiteError("分段计划与 bid-summary 不一致，请重跑 bid-summary")
        if rebuilt_seg.segment_index not in sec_map:
            raise BidDiagnosePrerequisiteError(
                f"sec_in_total.json 缺少 segment_index={rebuilt_seg.segment_index}"
            )

    return analysis_report, rebuilt, sec_map
