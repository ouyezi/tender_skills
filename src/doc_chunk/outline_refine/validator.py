from __future__ import annotations

from dataclasses import dataclass, field

from doc_chunk.models.outline import OutlineMappingFile, OutlineTree


@dataclass
class ValidationResult:
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class OutlineMappingValidator:
    def __init__(self, *, strict: bool = True) -> None:
        self.strict = strict

    def validate(
        self,
        *,
        original_outline: OutlineTree,
        refined_outline: OutlineTree,
        mapping: OutlineMappingFile,
    ) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []

        original_ids = {node.node_id for node in original_outline.nodes}
        refined_ids = {node.node_id for node in refined_outline.nodes}
        refined_lookup = {node.node_id: node for node in refined_outline.nodes}

        mapping_ids = set()
        ranges: list[tuple[int, int, str]] = []
        for entry in mapping.mappings:
            mapping_ids.add(entry.refined_node_id)
            if entry.refined_node_id not in refined_ids:
                errors.append(f"mapping references unknown refined node: {entry.refined_node_id}")

            missing_sources = [node_id for node_id in entry.source_node_ids if node_id not in original_ids]
            if missing_sources:
                errors.append(f"mapping has unknown source node ids: {', '.join(missing_sources)}")

            char_start = int(entry.markdown_range.get("char_start", -1))
            char_end = int(entry.markdown_range.get("char_end", -1))
            if char_start < 0 or char_end < 0 or char_end < char_start:
                errors.append(f"invalid markdown_range for node {entry.refined_node_id}")
            else:
                ranges.append((char_start, char_end, entry.refined_node_id))

        for node in refined_outline.nodes:
            if not (node.source_refs or node.anchor):
                errors.append(f"refined node {node.node_id} must have source_refs or anchor")
            if node.node_id not in mapping_ids:
                errors.append(f"missing mapping for refined node: {node.node_id}")

            for source_ref in node.source_refs:
                if source_ref not in original_ids:
                    errors.append(f"refined node {node.node_id} references unknown source id: {source_ref}")

        ranges.sort(key=lambda item: item[0])
        for idx in range(1, len(ranges)):
            prev_start, prev_end, prev_id = ranges[idx - 1]
            cur_start, cur_end, cur_id = ranges[idx]
            if cur_start <= prev_end:
                errors.append(f"overlapping ranges between {prev_id} and {cur_id}")
            if self.strict and cur_start > prev_end + 1:
                errors.append(f"non-contiguous ranges between {prev_id} and {cur_id}")
            if not self.strict and cur_start > prev_end + 1:
                warnings.append(f"gap ranges between {prev_id} and {cur_id}")

        return ValidationResult(passed=not errors, errors=errors, warnings=warnings)
