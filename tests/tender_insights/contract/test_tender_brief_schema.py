import jsonschema

from tender_insights.brief.models import TenderBriefFile


def test_tender_brief_schema_accepts_fixture() -> None:
    schema = TenderBriefFile.model_json_schema()
    fixture = {
        "schema_version": "1.0",
        "source_workspace": "/tmp/ws",
        "generated_at": "2026-06-25T00:00:00+00:00",
        "segment_count": 1,
        "ocr_image_count": 0,
        "summary_char_count": 12,
        "fields": {
            "issuer_company": "某某有限公司",
            "procurement_subject": "办公用品采购",
            "budget_info": "预算 100 万元",
            "qualification_requirements": "具有独立法人资格",
            "key_timelines": "工期 30 日，2026-07-01 开标",
        },
        "summary_text": "标准化概要示例文本",
    }
    jsonschema.validate(fixture, schema)
