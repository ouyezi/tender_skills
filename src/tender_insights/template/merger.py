from __future__ import annotations

import re
import unicodedata

from tender_insights.template.models import TemplateHitLLM

_PAREN_RE = re.compile(r"[（(][^）)]*[）)]|[（()）]")


def _normalize_fullwidth(text: str) -> str:
    return "".join(
        unicodedata.normalize("NFKC", ch)
        if unicodedata.east_asian_width(ch) in ("F", "W")
        else ch
        for ch in text
    )


def _normalized_title(title: str) -> str:
    text = _normalize_fullwidth(title)
    text = _PAREN_RE.sub("", text)
    text = re.sub(r"\s+", "", text)
    return text.lower()


def _jaccard(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    set_a = set(a)
    set_b = set(b)
    union = set_a | set_b
    if not union:
        return 0.0
    return len(set_a & set_b) / len(union)


def _overlap_ratio(a_start: int, a_end: int, b_start: int, b_end: int) -> float:
    inter = max(0, min(a_end, b_end) - max(a_start, b_start))
    shorter = min(a_end - a_start, b_end - b_start)
    return inter / shorter if shorter else 0.0


def dedupe_template_hits(hits: list[TemplateHitLLM]) -> list[TemplateHitLLM]:
    sorted_hits = sorted(hits, key=lambda h: (-h.confidence, h.char_start))
    kept: list[TemplateHitLLM] = []
    for hit in sorted_hits:
        if any(
            _overlap_ratio(hit.char_start, hit.char_end, k.char_start, k.char_end) > 0.5
            for k in kept
        ):
            continue
        if any(
            _normalized_title(hit.title) == _normalized_title(k.title)
            and _jaccard(hit.source_excerpt, k.source_excerpt) > 0.8
            for k in kept
        ):
            continue
        kept.append(hit)
    return sorted(kept, key=lambda h: h.char_start)
