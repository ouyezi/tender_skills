from tender_insights.config import InsightsConfig


def test_from_env_defaults(monkeypatch) -> None:
    monkeypatch.delenv("OCR_ENABLED", raising=False)
    cfg = InsightsConfig.from_env()
    assert cfg.ocr_model == "qwen-vl-ocr"
    assert cfg.segment_max_tokens == 12000
    assert cfg.ocr_enabled is True
    assert cfg.brief_ocr_enabled is False


def test_from_env_overrides(monkeypatch) -> None:
    monkeypatch.setenv("OCR_ENABLED", "false")
    monkeypatch.setenv("SEGMENT_MAX_TOKENS", "8000")
    monkeypatch.setenv("BRIEF_CHUNK_CHAR_LIMIT", "15000")
    monkeypatch.setenv("BRIEF_SUMMARY_MAX_CHARS", "400")
    cfg = InsightsConfig.from_env()
    assert cfg.ocr_enabled is False
    assert cfg.segment_max_tokens == 8000
    assert cfg.brief_chunk_char_limit == 15000
    assert cfg.brief_summary_max_chars == 400


def test_template_config_from_env(monkeypatch) -> None:
    monkeypatch.setenv("TEMPLATE_WHOLE_DOC_MAX_CHARS", "100000")
    monkeypatch.setenv("TEMPLATE_SHARD_MAX_CHARS", "30000")
    monkeypatch.setenv("TEMPLATE_CHAR_CHUNK_OVERLAP", "600")
    monkeypatch.setenv("TEMPLATE_PLAN_ENABLED", "false")
    cfg = InsightsConfig.from_env()
    assert cfg.template_whole_doc_max_chars == 100000
    assert cfg.template_shard_max_chars == 30000
    assert cfg.template_char_chunk_overlap == 600
    assert cfg.template_plan_enabled is False


def test_template_config_defaults(monkeypatch) -> None:
    monkeypatch.delenv("TEMPLATE_WHOLE_DOC_MAX_CHARS", raising=False)
    monkeypatch.delenv("TEMPLATE_SHARD_MAX_CHARS", raising=False)
    cfg = InsightsConfig.from_env()
    assert cfg.template_whole_doc_max_chars == 6000
    assert cfg.template_shard_max_chars == 6000
