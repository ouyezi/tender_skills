from tender_insights.template.merger import dedupe_template_hits
from tender_insights.template.models import TemplateHitLLM


def test_merger_keeps_higher_confidence_on_overlap() -> None:
    hits = [
        TemplateHitLLM(
            title="授权书",
            type="authorization",
            type_label="授权书",
            char_start=100,
            char_end=500,
            confidence=0.7,
            source_excerpt="a",
        ),
        TemplateHitLLM(
            title="授权书",
            type="authorization",
            type_label="授权书",
            char_start=120,
            char_end=480,
            confidence=0.95,
            source_excerpt="a",
        ),
    ]
    out = dedupe_template_hits(hits)
    assert len(out) == 1
    assert out[0].confidence == 0.95


def test_merger_dedupes_by_title_and_excerpt_jaccard() -> None:
    excerpt = "授权书：本人授权代表参加本次招标活动并签署相关文件"
    hits = [
        TemplateHitLLM(
            title="授权书",
            type="authorization",
            type_label="授权书",
            char_start=100,
            char_end=200,
            confidence=0.9,
            source_excerpt=excerpt,
        ),
        TemplateHitLLM(
            title="授 权书",
            type="authorization",
            type_label="授权书",
            char_start=500,
            char_end=600,
            confidence=0.7,
            source_excerpt=excerpt,
        ),
    ]
    out = dedupe_template_hits(hits)
    assert len(out) == 1
    assert out[0].confidence == 0.9
    assert out[0].char_start == 100
