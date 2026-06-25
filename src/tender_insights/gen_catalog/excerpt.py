from __future__ import annotations


def _paragraphs(text: str) -> list[str]:
    parts = [p.strip() for p in text.split("\n\n") if p.strip()]
    return parts or [text.strip()]


def pick_node_excerpt(
    markdown: str,
    *,
    node_title: str,
    max_chars: int = 2000,
    min_chars: int = 200,
) -> str:
    paragraphs = _paragraphs(markdown)
    lowered_title = node_title.strip().lower()
    start_idx = 0
    for idx, para in enumerate(paragraphs):
        if lowered_title and lowered_title in para.lower():
            start_idx = idx
            break

    selected: list[str] = []
    total = 0
    idx = start_idx
    while idx < len(paragraphs) and total < max_chars:
        piece = paragraphs[idx]
        if not selected and len(piece) < min_chars and idx + 1 < len(paragraphs):
            combined = piece
            j = idx + 1
            while len(combined) < min_chars and j < len(paragraphs):
                combined = combined + "\n\n" + paragraphs[j]
                j += 1
            piece = combined[:max_chars]
            idx = j
        else:
            idx += 1
        if total + len(piece) > max_chars:
            piece = piece[: max_chars - total]
        if piece:
            selected.append(piece)
            total += len(piece)
        if total >= max_chars:
            break
    return "\n\n".join(selected).strip()
