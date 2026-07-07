from __future__ import annotations

from doc_chunk.models.chunk import ContentChunk

from tender_insights.diagnosis.segment_optimizer import (
    MAX_CHARS,
    MIN_CHARS,
    optimize_segments,
)


def _chunk(chunk_id: str, markdown: str) -> ContentChunk:
    return ContentChunk(chunk_id=chunk_id, title=chunk_id, markdown=markdown)


def test_single_short_chunk_is_one_segment_exempt_min():
    chunks = [_chunk("c1", "x" * 500)]
    segments = optimize_segments(chunks)
    assert len(segments) == 1
    assert segments[0].char_count == 500
    assert segments[0].source_chunk_ids == ["c1"]


def test_merges_small_chunks_into_non_last_segment():
    chunks = [
        _chunk("c1", "a" * 4000),
        _chunk("c2", "b" * 5000),
        _chunk("c3", "c" * 3000),
        _chunk("c4", "d" * 9000),
        _chunk("c5", "e" * 500),
    ]
    segments = optimize_segments(chunks)
    assert len(segments) == 2
    assert MIN_CHARS <= segments[0].char_count <= MAX_CHARS
    assert segments[0].source_chunk_ids == ["c1", "c2", "c3"]
    assert segments[1].char_count == 9502  # 9000 + "\n\n" + 500
    assert segments[1].source_chunk_ids == ["c4", "c5"]


def test_splits_oversized_chunk_by_lines():
    big = "line\n" * 4000
    chunks = [_chunk("c1", big), _chunk("c2", "z" * 9000)]
    segments = optimize_segments(chunks)
    assert all(s.char_count <= MAX_CHARS for s in segments[:-1])
    assert segments[0].char_count >= MIN_CHARS


def test_non_last_segments_respect_char_bounds_when_multiple():
    chunks = [_chunk(f"c{i}", "x" * 10000) for i in range(4)]
    segments = optimize_segments(chunks)
    assert len(segments) >= 2
    for seg in segments[:-1]:
        assert MIN_CHARS <= seg.char_count <= MAX_CHARS
