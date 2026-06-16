from __future__ import annotations


def _normalize_ws(text: str) -> str:
    return " ".join(text.split())


def backfill_char_range(content_md: str, excerpt: str) -> tuple[int | None, int | None]:
    if not excerpt or not excerpt.strip():
        return None, None

    idx = content_md.find(excerpt)
    if idx >= 0:
        return idx, idx + len(excerpt)

    norm_content = _normalize_ws(content_md)
    norm_excerpt = _normalize_ws(excerpt)
    if not norm_excerpt:
        return None, None

    # 滑动窗口：在归一化文本中找最长匹配子串对应的原位置近似
    best_len = 0
    best_start: int | None = None
    words = excerpt.strip()
    for length in range(len(words), max(8, len(words) // 3), -1):
        candidate = words[:length]
        pos = content_md.find(candidate)
        if pos >= 0 and length > best_len:
            best_len = length
            best_start = pos
            break

    if best_start is not None:
        return best_start, best_start + best_len

    norm_pos = norm_content.find(norm_excerpt[: min(40, len(norm_excerpt))])
    if norm_pos >= 0:
        # 兜底：无法在原文精确定位时返回 None
        return None, None

    return None, None
