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


def test_templates_index_schema_v11_accepts_llm_fields() -> None:
    fixture = {
        "schema_version": "1.1",
        "analyzed_at": "2026-06-26T00:00:00+00:00",
        "plan_ref": "templates/plan.json",
        "shard_count": 2,
        "templates": [{
            "id": "tpl-001",
            "type": "authorization",
            "type_label": "授权书",
            "title": "授权书",
            "section_path": ["第四章"],
            "file": "templates/authorization-001.md",
            "char_start": 100,
            "char_end": 200,
            "confidence": 0.9,
            "extraction_method": "llm",
            "shard_id": "shard-001",
        }],
    }
    jsonschema.validate(fixture, TemplatesIndexFile.model_json_schema())
