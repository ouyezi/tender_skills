from tender_insights.template.merger import dedupe_template_hits
from tender_insights.template.models import TemplateHitLLM


def test_merger_keeps_higher_confidence_on_duplicate_title() -> None:
    hits = [
        TemplateHitLLM(
            title="授权书",
            type="authorization",
            type_label="授权书",
            markdown="# 授权书\n\n本授权书声明…",
            confidence=0.7,
            source_excerpt="授权",
        ),
        TemplateHitLLM(
            title="授权书",
            type="authorization",
            type_label="授权书",
            markdown="# 授权书\n\n本授权书声明…",
            confidence=0.95,
            source_excerpt="授权",
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
            markdown=excerpt,
            confidence=0.9,
            source_excerpt=excerpt,
        ),
        TemplateHitLLM(
            title="授 权书",
            type="authorization",
            type_label="授权书",
            markdown=excerpt,
            confidence=0.7,
            source_excerpt=excerpt,
        ),
    ]
    out = dedupe_template_hits(hits)
    assert len(out) == 1
    assert out[0].confidence == 0.9
