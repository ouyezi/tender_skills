from doc_chunk.metadata.classify import classify_chunk


def test_keyword_rule_maps_suggested_candidate_type_without_taxonomy_hints() -> None:
    result = classify_chunk(title="技术方案", markdown="本章描述系统架构", llm_client=None)
    assert result.get("suggested_candidate_type") == "scheme"
    assert result.get("suggested_knowledge_type") == "scheme"


def test_ignore_rule_sets_null_knowledge_type() -> None:
    result = classify_chunk(title="目录", markdown="章节列表", llm_client=None)
    assert result.get("suggested_candidate_type") == "ignore"
    assert result.get("suggested_knowledge_type") is None
