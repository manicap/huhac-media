from __future__ import annotations

import copy
import json
import re
from typing import Any


VISION_FIELDS = {
    "scene",
    "people",
    "activities",
    "objects",
    "environment",
    "visual_attributes",
    "tags",
    "description",
}
LIST_FIELDS = ("activities", "objects", "environment", "visual_attributes", "tags")

VISION_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": sorted(VISION_FIELDS),
    "properties": {
        "scene": {"type": "string"},
        "people": {
            "type": "object",
            "additionalProperties": False,
            "required": ["approx_count", "crowd"],
            "properties": {
                "approx_count": {"type": ["integer", "null"], "minimum": 0},
                "crowd": {"type": "boolean"},
            },
        },
        "activities": {"type": "array", "items": {"type": "string"}},
        "objects": {"type": "array", "items": {"type": "string"}},
        "environment": {"type": "array", "items": {"type": "string"}},
        "visual_attributes": {"type": "array", "items": {"type": "string"}},
        "tags": {"type": "array", "items": {"type": "string"}},
        "description": {"type": "string"},
    },
}


def validate_vision_result(value: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, dict):
        return ["$: expected object"]
    missing = VISION_FIELDS - value.keys()
    extra = value.keys() - VISION_FIELDS
    for key in sorted(missing):
        errors.append(f"$.{key}: missing required field")
    for key in sorted(extra):
        errors.append(f"$.{key}: unexpected field")
    for key in ("scene", "description"):
        if key in value and not isinstance(value[key], str):
            errors.append(f"$.{key}: expected string")
    people = value.get("people")
    if not isinstance(people, dict):
        if "people" in value:
            errors.append("$.people: expected object")
    else:
        people_keys = set(people)
        for key in sorted({"approx_count", "crowd"} - people_keys):
            errors.append(f"$.people.{key}: missing required field")
        for key in sorted(people_keys - {"approx_count", "crowd"}):
            errors.append(f"$.people.{key}: unexpected field")
        count = people.get("approx_count")
        if count is not None and (isinstance(count, bool) or not isinstance(count, int)):
            errors.append("$.people.approx_count: expected non-negative integer or null")
        elif isinstance(count, int) and count < 0:
            errors.append("$.people.approx_count: expected non-negative integer or null")
        if "crowd" in people and not isinstance(people["crowd"], bool):
            errors.append("$.people.crowd: expected boolean")
    for key in LIST_FIELDS:
        items = value.get(key)
        if not isinstance(items, list):
            if key in value:
                errors.append(f"$.{key}: expected array")
            continue
        for index, item in enumerate(items):
            if not isinstance(item, str):
                errors.append(f"$.{key}[{index}]: expected string")
    return errors


def technically_normalize(value: Any) -> Any:
    normalized = copy.deepcopy(value)
    if not isinstance(normalized, dict):
        return normalized
    for key in ("scene", "description"):
        if isinstance(normalized.get(key), str):
            normalized[key] = normalized[key].strip()
    people = normalized.get("people")
    if isinstance(people, dict):
        count = people.get("approx_count")
        if isinstance(count, str) and re.fullmatch(r"\s*\d+\s*", count):
            people["approx_count"] = int(count.strip())
        crowd = people.get("crowd")
        if isinstance(crowd, str) and crowd.strip().casefold() in {"true", "false"}:
            people["crowd"] = crowd.strip().casefold() == "true"
    for key in LIST_FIELDS:
        items = normalized.get(key)
        if not isinstance(items, list):
            continue
        clean: list[Any] = []
        seen: set[str] = set()
        for item in items:
            if not isinstance(item, str):
                clean.append(item)
                continue
            item = item.strip()
            if not item or item in seen:
                continue
            seen.add(item)
            clean.append(item)
        normalized[key] = clean
    return normalized


def parse_and_normalize(raw_response: str) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        parsed = json.loads(raw_response)
    except json.JSONDecodeError as exc:
        return None, [f"$: invalid JSON: {exc.msg} at line {exc.lineno} column {exc.colno}"]
    normalized = technically_normalize(parsed)
    errors = validate_vision_result(normalized)
    return (normalized if not errors else None), errors
