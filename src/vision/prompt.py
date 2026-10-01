from __future__ import annotations

import json

from vision.schema import VISION_JSON_SCHEMA


BASE_PROMPT = """Analyze only the visually supported content of this image.
Return exactly one JSON object matching the supplied schema.

Be objective and conservative. When uncertain, use a more general description
instead of guessing. Do not identify people, a venue, a band, or an event. Do
not infer a location. Do not transcribe or guess visible text. You may record
the existence of a poster, sign, text, logo, or chalkboard without claiming
what it says. Do not assess image quality, social-media suitability, or any
domain-specific value. Use ordinary descriptive phrases; do not invent a
controlled vocabulary or ontology."""


def initial_prompt() -> str:
    return f"{BASE_PROMPT}\n\nRequired JSON schema:\n{json.dumps(VISION_JSON_SCHEMA, sort_keys=True)}"


def repair_prompt(previous_response: str, errors: list[str]) -> str:
    return (
        "Repair the previous response so it matches the required JSON schema. "
        "Only correct structure and data types. Do not add facts that were not "
        "present in the previous response. Return JSON only.\n\n"
        f"Validation errors:\n{json.dumps(errors, ensure_ascii=False)}\n\n"
        f"Required JSON schema:\n{json.dumps(VISION_JSON_SCHEMA, sort_keys=True)}\n\n"
        f"Previous response:\n{previous_response}"
    )
