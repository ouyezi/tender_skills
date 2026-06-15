from __future__ import annotations

from doc_chunk.models.outline import RefinePreview


def build_preview(
    *,
    before_titles: list[str],
    after_titles: list[str],
    change_summary: str,
    warnings: list[str],
    validation_errors: list[str],
) -> RefinePreview:
    removed = [f"- {title}" for title in before_titles if title not in set(after_titles)]
    added = [f"+ {title}" for title in after_titles if title not in set(before_titles)]
    title_diff = removed + added
    return RefinePreview(
        node_count_before=len(before_titles),
        node_count_after=len(after_titles),
        change_summary=change_summary,
        warnings=warnings,
        title_diff=title_diff,
        validation_passed=not validation_errors,
        validation_errors=validation_errors,
    )
