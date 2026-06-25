from __future__ import annotations

import json
from pathlib import Path

import pytest
from doc_chunk.llm.client import FakeLLMClient
from doc_chunk.workspace.layout import OutputWorkspace

from tender_insights.brief.chunker import split_text_chunks
from tender_insights.brief.extractor import _enforce_summary_limit, extract_brief_workspace
from tender_insights.config import InsightsConfig


def test_split_text_chunks_single_piece() -> None:
    text = "a" * 100
    assert split_text_chunks(text, max_chars=20000) == [text]


def test_split_text_chunks_splits_long_text() -> None:
    text = "x" * 25000
    chunks = split_text_chunks(text, max_chars=20000)
    assert len(chunks) == 2
    assert all(len(chunk) <= 20000 for chunk in chunks)
    assert "".join(chunks) == text


def test_split_text_chunks_prefers_paragraph_break() -> None:
    head = "a" * 19900
    tail = "b" * 500
    text = f"{head}\n\n{tail}"
    chunks = split_text_chunks(text, max_chars=20000)
    assert len(chunks) == 2
    assert chunks[0] == head
    assert chunks[1] == tail


def test_enforce_summary_limit_truncates() -> None:
    long_text = "第一句。" + ("很长" * 300)
    trimmed = _enforce_summary_limit(long_text, max_chars=500)
    assert len(trimmed) <= 500


class BriefFakeLLM(FakeLLMClient):
    def __init__(self, *, single_json: str, partial_json: str | None = None, merge_json: str | None = None) -> None:
        super().__init__()
        self._single_json = single_json
        self._partial_json = partial_json or single_json
        self._merge_json = merge_json or single_json

    def complete_with_meta(self, messages, *, response_format="text", timeout=None):
        from doc_chunk.llm.completion import LLMCompletionResult

        user = " ".join(str(m.get("content", "")) for m in messages if m.get("role") == "user")
        if "分片提取的事实" in user:
            text = self._merge_json
        elif "分片" in user:
            text = self._partial_json
        else:
            text = self._single_json
        self.calls.append({"messages": messages, "response_format": response_format, "timeout": timeout})
        return LLMCompletionResult(text=text)


def _brief_response(
    *,
    issuer: str = "某某有限公司",
    subject: str = "办公用品采购",
    budget: str = "预算 100 万元",
    qualification: str = "具有独立法人资格",
    timelines: str = "工期 30 日，2026-07-01 开标",
    summary: str = "概要",
) -> str:
    return json.dumps(
        {
            "fields": {
                "issuer_company": issuer,
                "procurement_subject": subject,
                "budget_info": budget,
                "qualification_requirements": qualification,
                "key_timelines": timelines,
            },
            "summary_text": summary,
        },
        ensure_ascii=False,
    )


def _partial_response() -> str:
    return json.dumps(
        {
            "issuer_company": ["某某有限公司"],
            "procurement_subject": ["办公用品采购"],
            "budget_info": ["预算 100 万元"],
            "qualification_requirements": ["具有独立法人资格"],
            "key_timelines": ["2026-07-01 开标"],
        },
        ensure_ascii=False,
    )


def test_extract_brief_workspace_single_chunk(sample_workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCR_ENABLED", "false")
    workspace = OutputWorkspace.open_existing(sample_workspace)
    summary = "【招标人】某某有限公司。【标的】办公用品采购。【预算】100 万元。【资质】独立法人。【时间】2026-07-01 开标。"
    client = BriefFakeLLM(single_json=_brief_response(summary=summary))

    result = extract_brief_workspace(
        workspace,
        client,
        config=InsightsConfig(ocr_enabled=False, brief_summary_max_chars=500),
    )

    assert result.fields.issuer_company == "某某有限公司"
    assert len(result.summary_text) <= 500
    assert (workspace.root / "tender_brief.json").is_file()
    assert (workspace.root / "tender_brief.txt").read_text(encoding="utf-8") == result.summary_text


def test_extract_brief_workspace_chunked(sample_workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCR_ENABLED", "false")
    workspace = OutputWorkspace.open_existing(sample_workspace)
    long_md = "正文\n\n" + ("采购内容说明。" * 8000)
    (workspace.root / "content.md").write_text(long_md, encoding="utf-8")

    summary = "【招标人】某某有限公司。【标的】办公用品。【预算】100万。【资质】法人资格。【时间】7月开标。"
    client = BriefFakeLLM(
        single_json=_brief_response(summary=summary),
        partial_json=_partial_response(),
        merge_json=_brief_response(summary=summary),
    )

    result = extract_brief_workspace(
        workspace,
        client,
        config=InsightsConfig(
            ocr_enabled=False,
            brief_chunk_char_limit=20000,
            brief_summary_max_chars=500,
        ),
    )

    assert result.segment_count >= 2
    assert len(result.summary_text) <= 500
