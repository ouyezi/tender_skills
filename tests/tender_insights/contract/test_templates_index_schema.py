import jsonschema

from tender_insights.template.models import TemplatesIndexFile


def test_templates_index_schema_accepts_minimal_fixture() -> None:
    schema = TemplatesIndexFile.model_json_schema()
    fixture = {
        "schema_version": "1.0",
        "analyzed_at": "2026-06-16T00:00:00+00:00",
        "templates": [],
    }
    jsonschema.validate(fixture, schema)
