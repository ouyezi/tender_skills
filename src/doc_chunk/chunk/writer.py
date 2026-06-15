from __future__ import annotations

import json
from pathlib import Path

from doc_chunk.models.chunk import ChunkIndex, ChunkIndexEntry, ContentChunk


def write_chunks(
    chunks: list[ContentChunk],
    chunks_dir: Path,
    *,
    outline_source: str = "original",
) -> ChunkIndex:
    chunks_dir.mkdir(parents=True, exist_ok=True)

    entries: list[ChunkIndexEntry] = []
    for idx, chunk in enumerate(chunks, start=1):
        file_name = f"chunk-{idx:04d}.json"
        path = chunks_dir / file_name
        chunk.chunk_id = f"chunk-{idx:04d}"
        path.write_text(
            json.dumps(chunk.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        entries.append(
            ChunkIndexEntry(
                chunk_id=chunk.chunk_id,
                title=chunk.title,
                section_path=list(chunk.section_path),
                heading_level=chunk.heading_level,
                token_estimate=chunk.token_estimate,
                refined_node_id=chunk.refined_node_id,
                original_node_ids=list(chunk.original_node_ids),
                primary_outline_node_id=chunk.original_node_ids[0] if chunk.original_node_ids else None,
                path=file_name,
            )
        )

    index = ChunkIndex(outline_source=outline_source, chunks=entries)
    (chunks_dir / "index.json").write_text(
        json.dumps(index.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return index
