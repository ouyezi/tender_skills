from __future__ import annotations

from collections.abc import Callable

from doc_chunk.llm.client import LLMClient
from doc_chunk.workspace.layout import OutputWorkspace

from tender_insights.brief.chunker import split_text_chunks
from tender_insights.brief.models import (
    TenderBriefFields,
    TenderBriefFile,
    TenderBriefLLMResponse,
    TenderBriefPartialFacts,
)
from tender_insights.brief.prompts import (
    EXTRACT_SYSTEM_PROMPT,
    MERGE_SYSTEM_PROMPT,
    SINGLE_SYSTEM_PROMPT,
    build_extract_prompt,
    build_merge_prompt,
    build_single_prompt,
)
from tender_insights.common.content_source import prepare_interpret_source
from tender_insights.common.llm_extractor import extract_json_model
from tender_insights.common.output_writer import write_json_artifact
from tender_insights.common.section_slice import slice_for_llm
from tender_insights.config import InsightsConfig
from tender_insights.interpret.llm_logging import log_llm_prompt


def _merge_partial_dicts(partials: list[TenderBriefPartialFacts]) -> list[dict]:
    return [partial.model_dump() for partial in partials]


def _enforce_summary_limit(text: str, *, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    trimmed = text[:max_chars]
    for sep in ("。", "；", "\n", "，", " "):
        cut = trimmed.rfind(sep)
        if cut > max_chars // 2:
            return trimmed[: cut + 1].strip()
    return trimmed.strip()


def _extract_single(
    client: LLMClient,
    *,
    markdown: str,
    config: InsightsConfig,
    workspace: str,
) -> TenderBriefLLMResponse:
    messages = [
        {
            "role": "system",
            "content": SINGLE_SYSTEM_PROMPT.format(max_chars=config.brief_summary_max_chars),
        },
        {
            "role": "user",
            "content": build_single_prompt(markdown=markdown, max_chars=config.brief_summary_max_chars),
        },
    ]
    log_llm_prompt(
        call_type="brief_single",
        messages=messages,
        workspace=workspace,
        segment_id="brief-001",
    )
    response = extract_json_model(
        client,
        messages,
        TenderBriefLLMResponse,
        max_retries=config.max_retries,
        log_context={"call_type": "brief_single", "segment_id": "brief-001"},
    )
    response.summary_text = _enforce_summary_limit(
        response.summary_text,
        max_chars=config.brief_summary_max_chars,
    )
    return response


def _extract_chunked(
    client: LLMClient,
    *,
    chunks: list[str],
    config: InsightsConfig,
    workspace: str,
    on_progress: Callable[[str, dict], None] | None = None,
) -> TenderBriefLLMResponse:
    partials: list[TenderBriefPartialFacts] = []
    total = len(chunks)
    for index, chunk in enumerate(chunks, start=1):
        if on_progress:
            on_progress(
                "brief",
                {
                    "message": f"提取分片 ({index}/{total})",
                    "current": index,
                    "total": total,
                },
            )
        segment_id = f"brief-{index:03d}"
        messages = [
            {"role": "system", "content": EXTRACT_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": build_extract_prompt(
                    segment_index=index,
                    segment_total=total,
                    markdown=chunk,
                ),
            },
        ]
        log_llm_prompt(
            call_type="brief_segment",
            messages=messages,
            workspace=workspace,
            segment_id=segment_id,
        )
        partial = extract_json_model(
            client,
            messages,
            TenderBriefPartialFacts,
            max_retries=config.max_retries,
            log_context={"call_type": "brief_segment", "segment_id": segment_id},
        )
        partials.append(partial)

    if on_progress:
        on_progress(
            "brief",
            {
                "message": "合并分片生成概要",
                "current": total,
                "total": total,
            },
        )

    messages = [
        {
            "role": "system",
            "content": MERGE_SYSTEM_PROMPT.format(max_chars=config.brief_summary_max_chars),
        },
        {
            "role": "user",
            "content": build_merge_prompt(
                partials=_merge_partial_dicts(partials),
                max_chars=config.brief_summary_max_chars,
            ),
        },
    ]
    log_llm_prompt(
        call_type="brief_merge",
        messages=messages,
        workspace=workspace,
        segment_id="brief-merge",
    )
    response = extract_json_model(
        client,
        messages,
        TenderBriefLLMResponse,
        max_retries=config.max_retries,
        log_context={"call_type": "brief_merge", "segment_id": "brief-merge"},
    )
    response.summary_text = _enforce_summary_limit(
        response.summary_text,
        max_chars=config.brief_summary_max_chars,
    )
    return response


def extract_brief_workspace(
    workspace: OutputWorkspace,
    client: LLMClient,
    *,
    config: InsightsConfig | None = None,
    on_progress: Callable[[str, dict], None] | None = None,
) -> TenderBriefFile:
    config = config or InsightsConfig.from_env()
    source = prepare_interpret_source(workspace, config=config)
    full_md = slice_for_llm(
        workspace,
        source.markdown,
        0,
        len(source.markdown),
        blocks=source.blocks,
    )
    chunks = split_text_chunks(full_md, max_chars=config.brief_chunk_char_limit)

    if not chunks:
        empty_fields = TenderBriefFields(
            issuer_company="未提及",
            procurement_subject="未提及",
            budget_info="未提及",
            qualification_requirements="未提及",
            key_timelines="未提及",
        )
        empty = TenderBriefLLMResponse(fields=empty_fields, summary_text="未提及")
        result = TenderBriefFile(
            source_workspace=str(workspace.root),
            segment_count=0,
            ocr_image_count=source.ocr_image_count,
            summary_char_count=len(empty.summary_text),
            **empty.model_dump(),
        )
    elif len(chunks) == 1:
        extracted = _extract_single(
            client,
            markdown=chunks[0],
            config=config,
            workspace=str(workspace.root),
        )
        result = TenderBriefFile(
            source_workspace=str(workspace.root),
            segment_count=1,
            ocr_image_count=source.ocr_image_count,
            summary_char_count=len(extracted.summary_text),
            **extracted.model_dump(),
        )
    else:
        extracted = _extract_chunked(
            client,
            chunks=chunks,
            config=config,
            workspace=str(workspace.root),
            on_progress=on_progress,
        )
        result = TenderBriefFile(
            source_workspace=str(workspace.root),
            segment_count=len(chunks),
            ocr_image_count=source.ocr_image_count,
            summary_char_count=len(extracted.summary_text),
            **extracted.model_dump(),
        )

    write_json_artifact(
        workspace,
        "tender_brief.json",
        result.model_dump(mode="json"),
        stage_name="brief",
        output_key="tender_brief",
    )
    (workspace.root / "tender_brief.txt").write_text(result.summary_text, encoding="utf-8")
    return result
