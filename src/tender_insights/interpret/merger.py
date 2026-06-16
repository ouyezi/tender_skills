from __future__ import annotations

from typing import Callable, TypeVar

T = TypeVar("T")


def dedupe_by_title(items: list[T], *, title_getter: Callable[[T], str] = lambda x: getattr(x, "title")) -> list[T]:
    best: dict[str, T] = {}
    for item in items:
        key = title_getter(item).strip().lower()
        existing = best.get(key)
        if existing is None or getattr(item, "confidence", 0) > getattr(existing, "confidence", 0):
            best[key] = item
    return list(best.values())
