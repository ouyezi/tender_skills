from pathlib import Path

from doc_chunk.metadata.classify import classify_chunk


def test_candidate_type_from_taxonomy_hints(tmp_path: Path) -> None:
    cfg = tmp_path / "hints.yaml"
    cfg.write_text(
        """
chapter_taxonomies:
  - aliases: ["技术方案"]
    hint: "技术方案"
rules:
  - taxonomy_hints: ["技术方案"]
    suggested_candidate_type: scheme
    suggested_knowledge_type: scheme
""",
        encoding="utf-8",
    )
    result = classify_chunk(
        title="技术方案",
        markdown="本章描述系统实施方案",
        llm_client=None,
        classification_config=cfg,
    )
    assert result.get("chapter_taxonomy_hints") == ["技术方案"]
    assert result.get("suggested_candidate_type") == "scheme"
    assert result.get("suggested_knowledge_type") == "scheme"


def test_no_candidate_type_when_taxonomy_unmatched() -> None:
    result = classify_chunk(
        title="其他章节",
        markdown="无匹配内容",
        llm_client=None,
    )
    assert "suggested_candidate_type" not in result
    assert "suggested_knowledge_type" not in result
