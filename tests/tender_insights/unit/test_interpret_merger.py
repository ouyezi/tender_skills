from tender_insights.interpret.merger import dedupe_by_title
from tender_insights.interpret.models import DisqualificationItem


def test_dedupe_by_title_keeps_higher_confidence() -> None:
    items = [
        DisqualificationItem(
            id="dq-001", title="逾期", summary="a", trigger_condition="t",
            source_excerpt="x", section_path=[], confidence=0.5,
        ),
        DisqualificationItem(
            id="dq-002", title="逾期", summary="b", trigger_condition="t",
            source_excerpt="y", section_path=[], confidence=0.9,
        ),
    ]
    out = dedupe_by_title(items)
    assert len(out) == 1
    assert out[0].confidence == 0.9
