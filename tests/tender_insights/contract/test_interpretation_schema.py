import jsonschema

from tender_insights.interpret.models import InterpretationFile


def test_interpretation_schema_accepts_v11_fixture() -> None:
    schema = InterpretationFile.model_json_schema()
    fixture = {
        "schema_version": "1.1",
        "source_workspace": "/tmp/ws",
        "analyzed_at": "2026-06-24T00:00:00+00:00",
        "segment_count": 1,
        "ocr_image_count": 0,
        "overview": {
            "summary": "概要",
            "disqualification_summary": "废标",
            "scoring_summary": "得分",
            "bid_risk_summary": "风险",
            "directory_summary": "目录",
        },
        "disqualification_items": [],
        "scoring_items": [],
        "bid_risk_items": [],
        "directory_requirements": [],
        "directory_outline": {"confidence": 0.0, "nodes": []},
    }
    jsonschema.validate(fixture, schema)
