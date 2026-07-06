from __future__ import annotations

from agent_platform.client import AgentClient
from agent_platform.models import AgentInvokeError

from doc_chunk.errors import ValidationError
from doc_chunk.models.outline import OutlineMappingFile, OutlineTree, RefinePreview
from doc_chunk.outline_refine.preview import build_preview
from doc_chunk.outline_refine.session import RefineSession
from doc_chunk.outline_refine.validator import OutlineMappingValidator


class OutlineRefineEngine:
    def __init__(self, *, agent_client: AgentClient, strict: bool = True, max_retries: int = 2) -> None:
        self.agent_client = agent_client
        self.max_retries = max_retries
        self.validator = OutlineMappingValidator(strict=strict)

    def run_round(
        self,
        *,
        session: RefineSession,
        instruction: str,
    ) -> tuple[OutlineTree, OutlineMappingFile, str, RefinePreview]:
        last_errors: list[str] = []
        base_outline = session.base_outline()
        original_outline = session.original_outline

        for _ in range(self.max_retries + 1):
            try:
                result = self.agent_client.invoke(
                    "outline_refine",
                    {
                        "instruction": instruction,
                        "original_outline": original_outline.model_dump(mode="json"),
                        "current_outline": base_outline.model_dump(mode="json"),
                    },
                )
            except AgentInvokeError as exc:
                last_errors = [str(exc)]
                continue

            payload = result.structured_output
            if not isinstance(payload, dict):
                last_errors = ["LLM response missing structured output"]
                continue

            outline_raw = payload.get("outline_refined")
            mapping_raw = payload.get("node_mappings")
            summary = str(payload.get("change_summary", "")).strip() or "no summary"
            if not isinstance(outline_raw, dict) or not isinstance(mapping_raw, list):
                last_errors = ["LLM response missing outline_refined or node_mappings"]
                continue

            try:
                refined = OutlineTree.model_validate(outline_raw)
                mapping = OutlineMappingFile.model_validate({"mappings": mapping_raw})
            except Exception as exc:
                last_errors = [f"invalid payload schema: {exc}"]
                continue

            validation = self.validator.validate(
                original_outline=original_outline,
                refined_outline=refined,
                mapping=mapping,
            )
            preview = build_preview(
                before_titles=[node.title for node in base_outline.nodes],
                after_titles=[node.title for node in refined.nodes],
                change_summary=summary,
                warnings=validation.warnings,
                validation_errors=validation.errors,
            )
            if validation.passed:
                return refined, mapping, summary, preview
            last_errors = validation.errors

        raise ValidationError("; ".join(last_errors) if last_errors else "outline refinement failed")
