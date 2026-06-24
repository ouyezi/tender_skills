from __future__ import annotations

from typing import Callable, TypeVar

T = TypeVar("T")


def _score(item: T) -> tuple[float, int]:
    confidence = float(getattr(item, "confidence", 0) or 0)
    excerpt_len = len(getattr(item, "source_excerpt", "") or "")
    return confidence, excerpt_len


def dedupe_by_title(
    items: list[T],
    *,
    title_getter: Callable[[T], str] = lambda x: getattr(x, "title"),
) -> list[T]:
    best: dict[str, T] = {}
    for item in items:
        key = title_getter(item).strip().lower()
        if not key:
            key = f"__empty__:{id(item)}"
        existing = best.get(key)
        if existing is None or _score(item) > _score(existing):
            best[key] = item
    return list(best.values())
