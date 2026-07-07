from __future__ import annotations

from dataclasses import dataclass

from doc_chunk.models.chunk import ContentChunk

from tender_insights.diagnosis.models import DiagnosisSegment

MIN_CHARS = 8000
MAX_CHARS = 15000


@dataclass(frozen=True, slots=True)
class _Atom:
    markdown: str
    source_chunk_id: str
    section_path: list[str]


def _split_by_lines(markdown: str, max_chars: int) -> list[str]:
    if len(markdown) <= max_chars:
        return [markdown]
    parts: list[str] = []
    current: list[str] = []
    for line in markdown.splitlines(keepends=True):
        candidate = "".join(current + [line])
        if current and len(candidate) > max_chars:
            parts.append("".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        parts.append("".join(current))
    return parts or [markdown]


def _atomize_chunks(chunks: list[ContentChunk]) -> list[_Atom]:
    atoms: list[_Atom] = []
    for chunk in chunks:
        for piece in _split_by_lines(chunk.markdown, MAX_CHARS):
            if not piece.strip():
                continue
            atoms.append(
                _Atom(
                    markdown=piece,
                    source_chunk_id=chunk.chunk_id,
                    section_path=list(chunk.section_path),
                )
            )
    return atoms


def _join_atoms(atoms: list[_Atom]) -> str:
    return "\n\n".join(a.markdown.strip() for a in atoms if a.markdown.strip())


def _make_segment(atoms: list[_Atom], segment_index: int) -> DiagnosisSegment:
    markdown = _join_atoms(atoms)
    return DiagnosisSegment(
        segment_index=segment_index,
        markdown=markdown,
        char_count=len(markdown),
        source_chunk_ids=list(dict.fromkeys(a.source_chunk_id for a in atoms)),
        section_path=list(atoms[0].section_path) if atoms else [],
    )


def optimize_segments(chunks: list[ContentChunk]) -> list[DiagnosisSegment]:
    atoms = _atomize_chunks(chunks)
    if not atoms:
        return []
    if len(atoms) == 1:
        return [_make_segment(atoms, 1)]

    segments: list[DiagnosisSegment] = []
    idx = 0
    while idx < len(atoms):
        if len(atoms) - idx == 1:
            segments.append(_make_segment([atoms[idx]], len(segments) + 1))
            break

        buf: list[_Atom] = []
        while idx < len(atoms):
            atom = atoms[idx]
            candidate = _join_atoms(buf + [atom]) if buf else atom.markdown
            if len(candidate) <= MAX_CHARS:
                buf.append(atom)
                idx += 1
                joined = _join_atoms(buf)
                if len(joined) >= MIN_CHARS and idx < len(atoms):
                    next_joined = _join_atoms(buf + [atoms[idx]])
                    if len(next_joined) > MAX_CHARS:
                        break
                continue

            if buf and len(_join_atoms(buf)) >= MIN_CHARS:
                break

            buf.append(atom)
            idx += 1
            break

        if not buf:
            raise ValueError("unable to pack diagnosis segments")
        segments.append(_make_segment(buf, len(segments) + 1))

    return segments
