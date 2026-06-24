from tender_insights.config import InsightsConfig


def test_from_env_defaults(monkeypatch) -> None:
    monkeypatch.delenv("OCR_ENABLED", raising=False)
    cfg = InsightsConfig.from_env()
    assert cfg.ocr_model == "qwen-vl-ocr"
    assert cfg.segment_max_tokens == 12000
    assert cfg.ocr_enabled is True


def test_from_env_overrides(monkeypatch) -> None:
    monkeypatch.setenv("OCR_ENABLED", "false")
    monkeypatch.setenv("SEGMENT_MAX_TOKENS", "8000")
    cfg = InsightsConfig.from_env()
    assert cfg.ocr_enabled is False
    assert cfg.segment_max_tokens == 8000
