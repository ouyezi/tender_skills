from __future__ import annotations

import json

from doc_chunk.models.chunk import ChunkIndex, ContentChunk
from doc_chunk.workspace.layout import OutputWorkspace

from tender_insights.diagnosis.models import DiagnosisPrerequisiteError

_REPORT_HINT = (
    "缺少 summary_loop/report.md，请先运行：\n"
    "  tender-insights loop <workspace> --background \"...\""
)
_CHUNKS_HINT = (
    "缺少 chunks/，请先运行：\n"
    "  doc-chunk pipeline <file> -o <workspace> --overwrite"
)


def load_diagnosis_inputs(workspace: OutputWorkspace) -> tuple[str, list[ContentChunk]]:
    report_path = workspace.root / "summary_loop" / "report.md"
    if not report_path.is_file():
        raise DiagnosisPrerequisiteError(_REPORT_HINT)

    index_path = workspace.chunks_dir / "index.json"
    if not index_path.is_file():
        raise DiagnosisPrerequisiteError(_CHUNKS_HINT)

    index = ChunkIndex.model_validate_json(index_path.read_text(encoding="utf-8"))
    if not index.chunks:
        raise DiagnosisPrerequisiteError(_CHUNKS_HINT)

    chunks: list[ContentChunk] = []
    for entry in index.chunks:
        chunk_path = workspace.chunks_dir / entry.path
        if not chunk_path.is_file():
            continue
        chunk = ContentChunk.model_validate(json.loads(chunk_path.read_text(encoding="utf-8")))
        chunks.append(chunk)

    if not chunks:
        raise DiagnosisPrerequisiteError(_CHUNKS_HINT)

    tender_report = report_path.read_text(encoding="utf-8")
    return tender_report, chunks
