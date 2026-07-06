from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from agent_platform.client import AgentClient
from agent_platform.factory import create_agent_client_from_env
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
from tender_insights.common.agent_extractor import extract_json_via_agent
from tender_insights.common.content_source import prepare_interpret_source
from tender_insights.common.output_writer import write_json_artifact
from tender_insights.common.section_slice import slice_for_llm
from tender_insights.config import InsightsConfig
from tender_insights.interpret.llm_logging import log_llm_prompt

_BRIEF_FIELD_KEYS = (
    "issuer_company",
    "procurement_subject",
    "budget_info",
    "qualification_requirements",
    "key_timelines",
)


def _merge_partial_dicts(partials: list[TenderBriefPartialFacts]) -> list[dict]:
    """将分片事实模型转为 dict 列表。"""
    return [partial.model_dump() for partial in partials]


def _enforce_summary_limit(text: str, *, max_chars: int) -> str:
    """截断 summary_text 至 max_chars，尽量在句读处断开。"""
    if len(text) <= max_chars:
        return text
    trimmed = text[:max_chars]
    for sep in ("。", "；", "\n", "，", " "):
        cut = trimmed.rfind(sep)
        if cut > max_chars // 2:
            return trimmed[: cut + 1].strip()
    return trimmed.strip()


def _normalize_brief_response(data: dict[str, Any]) -> dict[str, Any]:
    """兼容平台扁平字段与业务嵌套 fields 两种形态。"""
    if isinstance(data.get("fields"), dict):
        return data
    fields = {key: str(data.get(key) or "未提及") for key in _BRIEF_FIELD_KEYS}
    return {
        "fields": fields,
        "summary_text": str(data.get("summary_text") or "未提及"),
    }


def _resolve_agent_client(
    client: LLMClient | AgentClient,
    agent_client: AgentClient | None,
) -> AgentClient:
    """解析可用于 invoke 的 AgentClient。"""
    if agent_client is not None:
        return agent_client
    if isinstance(client, AgentClient):
        return client
    return create_agent_client_from_env(llm_client=client)


def _extract_single(
    agent_client: AgentClient,
    *,
    markdown: str,
    config: InsightsConfig,
    workspace: str,
) -> TenderBriefLLMResponse:
    """单段模式：调用 brief_single。"""
    max_chars = config.brief_summary_max_chars
    messages = [
        {
            "role": "system",
            "content": SINGLE_SYSTEM_PROMPT.format(max_chars=max_chars),
        },
        {
            "role": "user",
            "content": build_single_prompt(markdown=markdown, max_chars=max_chars),
        },
    ]
    log_llm_prompt(
        call_type="brief_single",
        messages=messages,
        workspace=workspace,
        segment_id="brief-001",
    )
    response = extract_json_via_agent(
        agent_client,
        "brief_single",
        {"markdown": markdown, "max_chars": max_chars},
        TenderBriefLLMResponse,
        max_retries=config.max_retries,
        normalize=_normalize_brief_response,
        log_context={"call_type": "brief_single", "segment_id": "brief-001"},
    )
    response.summary_text = _enforce_summary_limit(
        response.summary_text,
        max_chars=max_chars,
    )
    return response


def _extract_chunked(
    agent_client: AgentClient,
    *,
    chunks: list[str],
    config: InsightsConfig,
    workspace: str,
    on_progress: Callable[[str, dict], None] | None = None,
) -> TenderBriefLLMResponse:
    """分片模式：brief_segment × N + brief_merge。"""
    partials: list[TenderBriefPartialFacts] = []
    total = len(chunks)
    step_total = total + 1
    max_chars = config.brief_summary_max_chars
    if on_progress:
        on_progress(
            "brief",
            {
                "message": f"共 {total} 个分片待处理",
                "current": 0,
                "total": total,
                "step_total": step_total,
                "step_current": 0,
            },
        )
    for index, chunk in enumerate(chunks, start=1):
        if on_progress:
            on_progress(
                "brief",
                {
                    "message": f"大模型处理分片 ({index}/{total})…",
                    "current": index,
                    "total": total,
                    "step_total": step_total,
                    "step_current": index,
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
        partial = extract_json_via_agent(
            agent_client,
            "brief_segment",
            {
                "segment_index": index,
                "segment_total": total,
                "markdown": chunk,
            },
            TenderBriefPartialFacts,
            max_retries=config.max_retries,
            log_context={"call_type": "brief_segment", "segment_id": segment_id},
        )
        partials.append(partial)

    if on_progress:
        on_progress(
            "brief",
            {
                "message": "大模型合并分片…",
                "current": total,
                "total": total,
                "step_total": step_total,
                "step_current": step_total,
                "phase": "merge",
            },
        )

    partial_dicts = _merge_partial_dicts(partials)
    messages = [
        {
            "role": "system",
            "content": MERGE_SYSTEM_PROMPT.format(max_chars=max_chars),
        },
        {
            "role": "user",
            "content": build_merge_prompt(
                partials=partial_dicts,
                max_chars=max_chars,
            ),
        },
    ]
    log_llm_prompt(
        call_type="brief_merge",
        messages=messages,
        workspace=workspace,
        segment_id="brief-merge",
    )
    response = extract_json_via_agent(
        agent_client,
        "brief_merge",
        {
            "partials_json": json.dumps(partial_dicts, ensure_ascii=False),
            "max_chars": max_chars,
        },
        TenderBriefLLMResponse,
        max_retries=config.max_retries,
        normalize=_normalize_brief_response,
        log_context={"call_type": "brief_merge", "segment_id": "brief-merge"},
    )
    response.summary_text = _enforce_summary_limit(
        response.summary_text,
        max_chars=max_chars,
    )
    return response


def extract_brief_workspace(
    workspace: OutputWorkspace,
    client: LLMClient | AgentClient,
    *,
    config: InsightsConfig | None = None,
    on_progress: Callable[[str, dict], None] | None = None,
    agent_client: AgentClient | None = None,
) -> TenderBriefFile:
    """提取招标基础概要并写入 tender_brief.json / tender_brief.txt。"""
    config = config or InsightsConfig.from_env()
    resolved = _resolve_agent_client(client, agent_client)
    if on_progress:
        ocr_note = "含图片 OCR" if config.brief_ocr_enabled else "跳过图片 OCR"
        on_progress(
            "brief",
            {
                "message": f"准备文档源（{ocr_note}）",
                "current": 0,
                "total": 1,
                "step_total": 1,
                "step_current": 0,
            },
        )
    source = prepare_interpret_source(
        workspace,
        config=config,
        ocr_enabled=config.brief_ocr_enabled,
    )
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
        if on_progress:
            on_progress(
                "brief",
                {
                    "message": "大模型提取概要…",
                    "current": 1,
                    "total": 1,
                    "step_total": 1,
                    "step_current": 1,
                },
            )
        extracted = _extract_single(
            resolved,
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
            resolved,
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
