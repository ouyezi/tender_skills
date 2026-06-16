import jsonschema

from tender_insights.legal.models import LegalReviewFile


def test_legal_review_schema_accepts_minimal_fixture() -> None:
    schema = LegalReviewFile.model_json_schema()
    fixture = {
        "schema_version": "1.0",
        "source_workspace": "/tmp/ws",
        "analyzed_at": "2026-06-16T00:00:00+00:00",
        "risk_items": [],
        "pending_confirmations": [],
    }
    jsonschema.validate(fixture, schema)
