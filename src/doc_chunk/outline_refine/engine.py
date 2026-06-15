from __future__ import annotations

import json
from pathlib import Path

from doc_chunk.errors import ValidationError
from doc_chunk.llm.client import LLMClient
from doc_chunk.models.outline import OutlineMappingFile, OutlineTree, RefinePreview
from doc_chunk.outline_refine.preview import build_preview
from doc_chunk.outline_refine.session import RefineSession
from doc_chunk.outline_refine.validator import OutlineMappingValidator


def _load_prompt() -> str:
    prompt_path = Path(__file__).parent.parent / "llm" / "prompts" / "outline_refine.txt"
    return prompt_path.read_text(encoding="utf-8")


class OutlineRefineEngine:
    def __init__(self, *, llm_client: LLMClient, strict: bool = True, max_retries: int = 2) -> None:
        self.llm_client = llm_client
        self.max_retries = max_retries
        self.validator = OutlineMappingValidator(strict=strict)
        self.system_prompt = _load_prompt()

    def run_round(self, *, session: RefineSession, instruction: str) -> tuple[OutlineTree, OutlineMappingFile, str, RefinePreview]:
        last_errors: list[str] = []
        base_outline = session.base_outline()
        original_outline = session.original_outline

        for _ in range(self.max_retries + 1):
            user_content = {
                "instruction": instruction,
                "original_outline": original_outline.model_dump(mode="json"),
                "current_outline": base_outline.model_dump(mode="json"),
            }
            raw = self.llm_client.complete(
                [
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": json.dumps(user_content, ensure_ascii=False)},
                ],
                response_format="json",
                timeout=60.0,
            )
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                last_errors = [f"invalid JSON: {exc}"]
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
