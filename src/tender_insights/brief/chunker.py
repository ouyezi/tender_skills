from __future__ import annotations


def split_text_chunks(text: str, *, max_chars: int) -> list[str]:
    """Split text into chunks of at most *max_chars* characters, preferring paragraph breaks."""
    stripped = text.strip()
    if not stripped:
        return []
    if len(stripped) <= max_chars:
        return [stripped]

    chunks: list[str] = []
    start = 0
    length = len(stripped)
    while start < length:
        end = min(start + max_chars, length)
        if end < length:
            paragraph_break = stripped.rfind("\n\n", start, end)
            if paragraph_break > start + max_chars // 2:
                end = paragraph_break
            else:
                line_break = stripped.rfind("\n", start, end)
                if line_break > start + max_chars // 2:
                    end = line_break
        piece = stripped[start:end].strip()
        if piece:
            chunks.append(piece)
        if end <= start:
            end = min(start + max_chars, length)
        start = end
    return chunks
