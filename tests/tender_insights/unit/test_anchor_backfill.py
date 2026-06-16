from tender_insights.common.anchor_backfill import backfill_char_range


CONTENT = "前言\n\n# 第一章\n\n投标人须具备资质。\n\n# 第二章\n\n其他内容。"


def test_backfill_exact_excerpt() -> None:
    excerpt = "投标人须具备资质。"
    start, end = backfill_char_range(CONTENT, excerpt)
    assert start is not None
    assert CONTENT[start:end] == excerpt


def test_backfill_missing_returns_none() -> None:
    start, end = backfill_char_range(CONTENT, "完全不存在的句子")
    assert start is None
    assert end is None
