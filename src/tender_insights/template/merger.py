from __future__ import annotations

import re
import unicodedata

from tender_insights.template.models import TemplateHitLLM

_PAREN_RE = re.compile(r"[（(][^）)]*[）)]|[（()）]")
_MARKDOWN_PREFIX_LEN = 300


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


def _markdown_fingerprint(hit: TemplateHitLLM) -> str:
    text = hit.markdown.strip() or hit.source_excerpt
    return text[:_MARKDOWN_PREFIX_LEN]


def dedupe_template_hits(hits: list[TemplateHitLLM]) -> list[TemplateHitLLM]:
    sorted_hits = sorted(hits, key=lambda h: (-h.confidence, h.title))
    kept: list[TemplateHitLLM] = []
    for hit in sorted_hits:
        title_key = _normalized_title(hit.title)
        fp = _markdown_fingerprint(hit)
        if any(
            _normalized_title(k.title) == title_key
            and _jaccard(fp, _markdown_fingerprint(k)) > 0.8
            for k in kept
        ):
            continue
        if any(
            fp
            and _jaccard(fp, _markdown_fingerprint(k)) > 0.9
            for k in kept
        ):
            continue
        kept.append(hit)
    return sorted(kept, key=lambda h: h.title)
