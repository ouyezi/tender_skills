import jsonschema

from tender_insights.interpret.models import InterpretationFile


def test_interpretation_schema_accepts_minimal_fixture() -> None:
    schema = InterpretationFile.model_json_schema()
    fixture = {
        "schema_version": "1.0",
        "source_workspace": "/tmp/ws",
        "analyzed_at": "2026-06-16T00:00:00+00:00",
        "disqualification_items": [],
        "scoring_items": [],
        "bid_risk_items": [],
        "directory_requirements": [],
    }
    jsonschema.validate(fixture, schema)
