from __future__ import annotations

import pytest

from scripts.provision_agent import (
    ValidationError,
    validate_structured_output,
    validate_text_output,
)

OUTLINE_OUTPUT_SCHEMA = [
    {"name": "outline_refined", "type": "object", "required": True},
    {"name": "node_mappings", "type": "array", "required": True, "itemType": "object"},
    {"name": "change_summary", "type": "string", "required": True},
]


def test_validate_structured_output_passes_with_all_fields():
    payload = {
        "outline_refined": {"schema_version": "1.0", "nodes": []},
        "node_mappings": [],
        "change_summary": "ok",
    }
    validate_structured_output(payload, OUTLINE_OUTPUT_SCHEMA)


def test_validate_structured_output_raises_on_missing_field():
    with pytest.raises(ValidationError, match="change_summary"):
        validate_structured_output(
            {"outline_refined": {}, "node_mappings": []},
            OUTLINE_OUTPUT_SCHEMA,
        )


def test_validate_text_output_requires_non_empty_string():
    validate_text_output("hello")
    with pytest.raises(ValidationError):
        validate_text_output("")
    with pytest.raises(ValidationError):
        validate_text_output(None)


def test_parse_json_object_from_markdown_fence():
    from scripts.provision_agent import parse_json_object

    raw = '```json\n{"risk_items": [], "pending_confirmations": []}\n```'
    assert parse_json_object(raw) == {"risk_items": [], "pending_confirmations": []}
