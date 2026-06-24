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


def test_interpretation_schema_accepts_v12_fixture() -> None:
    schema = InterpretationFile.model_json_schema()
    fixture = {
        "schema_version": "1.2",
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
        "scoring_items": [
            {
                "id": "sc-001",
                "title": "技术部分",
                "summary": "s",
                "max_score": 40.0,
                "weight": "40%",
                "criteria": "c",
                "children": [
                    {
                        "id": "sc-001-01",
                        "title": "细则",
                        "criteria": "细则全文",
                        "source_excerpt": "x",
                    }
                ],
                "source_excerpt": "x",
                "section_path": [],
                "confidence": 0.9,
            }
        ],
        "bid_risk_items": [],
        "directory_requirements": [
            {
                "id": "dr-001",
                "title": "推断投标文件组成",
                "required_sections": [],
                "mandatory": True,
                "inferred": True,
                "structure": [],
                "source_excerpt": "",
                "section_path": [],
                "confidence": 0.6,
            }
        ],
        "directory_outline": {"confidence": 0.0, "nodes": []},
    }
    jsonschema.validate(fixture, schema)
