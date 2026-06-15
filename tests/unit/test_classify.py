from __future__ import annotations

from pathlib import Path

from doc_chunk.llm.client import FakeLLMClient
from doc_chunk.metadata.classify import classify_chunk


def test_classify_chunk_matches_builtin_rule() -> None:
    result = classify_chunk(title="资质要求", markdown="供应商需要提供资质证书。")
    assert result["knowledge_type"] == "qualification"
    assert result["classification_source"] == "rule"


def test_classify_chunk_supports_yaml_extension(tmp_path: Path) -> None:
    cfg = tmp_path / "classification.yaml"
    cfg.write_text(
        "labels:\n"
        "  compliance:\n"
        "    chapter_type: 合规\n"
        "    keywords: [合规条款, 监管要求]\n",
        encoding="utf-8",
    )
    result = classify_chunk(
        title="合规条款",
        markdown="本章包含监管要求。",
        classification_config=cfg,
    )
    assert result["knowledge_type"] == "compliance"
    assert result["chapter_type"] == "合规"


def test_classify_chunk_uses_llm_as_fallback() -> None:
    llm = FakeLLMClient(
        responses=[
            '{"knowledge_type":"other","chapter_type":"其他","confidence":0.88,"rationale":"llm fallback"}'
        ]
    )
    result = classify_chunk(
        title="未知标题",
        markdown="无明显关键词",
        llm_client=llm,
    )
    assert result["classification_source"] == "llm"
    assert result["classification_confidence"] == 0.88
