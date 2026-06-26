import jsonschema

from tender_insights.gen_catalog.models import BidOutlineFile


def test_bid_outline_schema_accepts_fixture() -> None:
    schema = BidOutlineFile.model_json_schema()
    fixture = {
        "schema_version": "1.0",
        "source_workspace": "/tmp/ws",
        "generated_at": "2026-06-25T00:00:00+00:00",
        "accepted_at": None,
        "interpretation_schema": "1.2",
        "mode": "step",
        "status": "paused",
        "step_index": 1,
        "step_total": 3,
        "overview_snapshot": {"summary": "概要"},
        "brief_snapshot": {"summary_text": "brief"},
        "root": {
            "id": "bid-root",
            "title": "投标文件",
            "level": 0,
            "order": 0,
            "mandatory": True,
            "number": None,
            "summary": "",
            "writing_spec": "",
            "template_ref": None,
            "scoring_refs": ["sc-001"],
            "disqualification_refs": ["dq-001"],
            "bid_risk_refs": [],
            "source_refs": [],
            "children": [
                {
                    "id": "bid-001",
                    "title": "投标函",
                    "level": 1,
                    "order": 1,
                    "mandatory": True,
                    "number": "1",
                    "summary": "投标承诺",
                    "writing_spec": "须法定代表人签字盖章",
                    "template_ref": {
                        "template_id": "tpl-001",
                        "file": "templates/tpl-001.md",
                        "type": "commitment",
                    },
                    "scoring_refs": [],
                    "disqualification_refs": ["dq-001"],
                    "bid_risk_refs": [],
                    "source_refs": [
                        {
                            "section_path": ["格式"],
                            "char_start": 10,
                            "char_end": 50,
                            "excerpt": "投标函格式见附件",
                        }
                    ],
                    "children": [],
                }
            ],
        },
    }
    jsonschema.validate(fixture, schema)
