from __future__ import annotations

import json

from vision.schema import parse_and_normalize, technically_normalize, validate_vision_result

from conftest import canonical_result


def test_valid_model_json_is_accepted():
    expected = canonical_result()
    result, errors = parse_and_normalize(json.dumps(expected))
    assert result == expected
    assert errors == []


def test_safe_string_integer_boolean_and_array_normalization():
    raw = canonical_result(
        scene="  room  ",
        people={"approx_count": "8", "crowd": " false "},
        objects=[" chair ", "chair", "", "table"],
    )
    result, errors = parse_and_normalize(json.dumps(raw))
    assert errors == []
    assert result["scene"] == "room"
    assert result["people"] == {"approx_count": 8, "crowd": False}
    assert result["objects"] == ["chair", "table"]


def test_semantic_conversion_is_not_performed():
    value = canonical_result(people={"approx_count": "several", "crowd": False})
    normalized = technically_normalize(value)
    assert normalized["people"]["approx_count"] == "several"
    assert validate_vision_result(normalized) == [
        "$.people.approx_count: expected non-negative integer or null"
    ]


def test_malformed_json_is_rejected_with_diagnostic():
    result, errors = parse_and_normalize("{not-json")
    assert result is None
    assert "invalid JSON" in errors[0]


def test_schema_invalid_people_shape_and_extra_fields_are_rejected():
    value = canonical_result(people=["person"])
    value["guess"] = "not allowed"
    result, errors = parse_and_normalize(json.dumps(value))
    assert result is None
    assert "$.people: expected object" in errors
    assert "$.guess: unexpected field" in errors


def test_negative_and_boolean_counts_are_not_integers():
    for count in (-1, True):
        errors = validate_vision_result(canonical_result(people={"approx_count": count, "crowd": False}))
        assert errors == ["$.people.approx_count: expected non-negative integer or null"]
