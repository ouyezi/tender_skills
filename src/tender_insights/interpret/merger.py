from __future__ import annotations

from typing import Callable, TypeVar

from tender_insights.interpret.models import (
    DirectoryRequirement,
    DirectoryStructureNode,
    ScoringCriterionNode,
    ScoringItem,
)

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


def _child_score(child: ScoringCriterionNode) -> tuple[int, int]:
    return len(child.criteria or ""), len(child.source_excerpt or "")


def _merge_children(
    existing: list[ScoringCriterionNode],
    incoming: list[ScoringCriterionNode],
) -> list[ScoringCriterionNode]:
    best: dict[str, ScoringCriterionNode] = {}
    for child in [*existing, *incoming]:
        key = child.title.strip().lower()
        if not key:
            key = f"__empty__:{child.id}"
        prev = best.get(key)
        if prev is None or _child_score(child) > _child_score(prev):
            best[key] = child
    return list(best.values())


def merge_scoring_items(items: list[ScoringItem]) -> list[ScoringItem]:
    merged: dict[tuple[str, float | None], ScoringItem] = {}
    order: list[tuple[str, float | None]] = []
    for item in items:
        key = (item.title.strip().lower(), item.max_score)
        if key not in merged:
            merged[key] = item.model_copy(deep=True)
            order.append(key)
            continue
        existing = merged[key]
        if _score(item) > _score(existing):
            existing.summary = item.summary
            existing.criteria = item.criteria
            existing.weight = item.weight or existing.weight
            existing.source_excerpt = item.source_excerpt
            existing.confidence = item.confidence
            existing.section_path = item.section_path or existing.section_path
        existing.children = _merge_children(existing.children, item.children)
    return [merged[k] for k in order]


def _has_explicit_structure(req: DirectoryRequirement) -> bool:
    return not req.inferred and bool(req.structure)


def normalize_directory_requirements(
    items: list[DirectoryRequirement],
) -> list[DirectoryRequirement]:
    explicit = [r for r in items if _has_explicit_structure(r)]
    if explicit:
        return dedupe_by_title(explicit)

    flat_titles: list[str] = []
    seen: set[str] = set()
    best_confidence = 0.0
    for req in items:
        best_confidence = max(best_confidence, req.confidence)
        for title in req.required_sections:
            key = title.strip().lower()
            if key and key not in seen:
                seen.add(key)
                flat_titles.append(title.strip())
        for node in req.structure:
            key = node.title.strip().lower()
            if key and key not in seen:
                seen.add(key)
                flat_titles.append(node.title.strip())

    if not flat_titles:
        return dedupe_by_title(items)

    structure = [
        DirectoryStructureNode(order=i + 1, title=title, mandatory=True)
        for i, title in enumerate(flat_titles)
    ]
    return [
        DirectoryRequirement(
            id="dr-inferred-001",
            title="推断投标文件组成",
            required_sections=[],
            mandatory=True,
            inferred=True,
            structure=structure,
            source_excerpt="",
            section_path=[],
            confidence=min(best_confidence, 0.65),
        )
    ]
