"""Tests for strand_rater.py pure functions."""
import pytest

from lib.strand_rater import _fix_schema_for_anthropic


class TestFixSchemaForAnthropic:
    def test_adds_additional_properties_to_object(self):
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        result = _fix_schema_for_anthropic(schema)
        assert result["additionalProperties"] is False
        assert result["properties"]["name"]["type"] == "string"

    def test_preserves_existing_additional_properties(self):
        schema = {"type": "object", "additionalProperties": True}
        result = _fix_schema_for_anthropic(schema)
        assert result["additionalProperties"] is True

    def test_nested_objects(self):
        schema = {
            "type": "object",
            "properties": {
                "nested": {
                    "type": "object",
                    "properties": {"value": {"type": "number"}},
                }
            },
        }
        result = _fix_schema_for_anthropic(schema)
        assert result["additionalProperties"] is False
        assert result["properties"]["nested"]["additionalProperties"] is False

    def test_array_of_objects(self):
        schema = {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {"type": "object", "properties": {"id": {"type": "integer"}}},
                }
            },
        }
        result = _fix_schema_for_anthropic(schema)
        assert result["additionalProperties"] is False
        assert result["properties"]["items"]["items"]["additionalProperties"] is False

    def test_non_object_types_unchanged(self):
        schema = {"type": "string"}
        result = _fix_schema_for_anthropic(schema)
        assert result == {"type": "string"}

    def test_does_not_mutate_original(self):
        original = {"type": "object", "properties": {"x": {"type": "number"}}}
        _ = _fix_schema_for_anthropic(original)
        assert "additionalProperties" not in original

    def test_deeply_nested_structure(self):
        schema = {
            "type": "object",
            "properties": {
                "level1": {
                    "type": "object",
                    "properties": {
                        "level2": {
                            "type": "object",
                            "properties": {"level3": {"type": "string"}},
                        }
                    },
                }
            },
        }
        result = _fix_schema_for_anthropic(schema)
        assert result["additionalProperties"] is False
        assert result["properties"]["level1"]["additionalProperties"] is False
        assert result["properties"]["level1"]["properties"]["level2"]["additionalProperties"] is False

    def test_empty_schema(self):
        result = _fix_schema_for_anthropic({})
        assert result == {}

    def test_mixed_types_in_array(self):
        schema = {
            "type": "object",
            "properties": {
                "mixed": {
                    "type": "array",
                    "items": [
                        {"type": "object", "properties": {"a": {"type": "string"}}},
                        {"type": "string"},
                    ],
                }
            },
        }
        result = _fix_schema_for_anthropic(schema)
        assert result["additionalProperties"] is False
        assert result["properties"]["mixed"]["items"][0]["additionalProperties"] is False

