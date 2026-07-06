from __future__ import annotations

from agent_platform.json_coerce import coerce_structured_output, parse_json_object


def test_parse_json_object_from_plain_json():
    assert parse_json_object('{"a": 1}') == {"a": 1}


def test_parse_json_object_from_markdown_fence():
    text = 'Here is JSON:\n```json\n{"b": 2}\n```'
    assert parse_json_object(text) == {"b": 2}


def test_parse_json_object_returns_none_for_invalid():
    assert parse_json_object("not json") is None


def test_coerce_structured_output_prefers_structured_output_key():
    resp = {"structuredOutput": {"x": 1}, "output": '{"y": 2}'}
    assert coerce_structured_output(resp) == {"x": 1}


def test_coerce_structured_output_parses_output_string():
    resp = {"output": '{"z": 3}'}
    assert coerce_structured_output(resp) == {"z": 3}
