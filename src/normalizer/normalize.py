from __future__ import annotations

from datetime import datetime
import math
import re
from typing import Any, Callable

from normalizer.models import AssetInput


_OFFSET = re.compile(r"^[+-](?:0\d|1[0-3]):[0-5]\d$|^[+-]14:00$")

_COMMON_FIELDS = ("manufacturer", "camera_model", "software")
_IMAGE_FIELDS = (
    "width", "height", "orientation", "color_space", "lens",
    "focal_length_mm", "exposure_seconds", "aperture", "iso", "flash", "gps",
)
_VIDEO_FIELDS = (
    "container", "duration_seconds", "width", "height", "fps", "video_codec",
    "bitrate", "rotation", "audio_present", "audio_codec", "sample_rate", "channels",
)


class _Evidence:
    def __init__(self, asset: AssetInput):
        self.asset = asset
        self.field_sources: dict[str, list[dict[str, Any]]] = {}
        self.missing_fields: list[str] = []
        self.invalid_values: list[dict[str, Any]] = []
        self.warnings: list[dict[str, Any]] = []
        self.conflicts: list[dict[str, Any]] = []

    def add(
        self,
        target: str,
        source_pointer: str,
        observed_value: Any,
        *,
        document: str,
        selection: str,
        rule: str,
        layer: str = "source_fact",
    ) -> None:
        entry: dict[str, Any] = {
            "layer": layer,
            "source_document": document,
            "source_pointer": source_pointer,
            "observed_value": observed_value,
            "selection": selection,
            "rule": rule,
        }
        if document == self.asset.metadata_location and self.asset.metadata is not None:
            stage = self.asset.metadata.get("stages")
            metadata_stage = stage.get("metadata") if isinstance(stage, dict) else None
            if isinstance(metadata_stage, dict):
                version = metadata_stage.get("processor_version")
                fingerprint = metadata_stage.get("config_fingerprint")
                if isinstance(version, str):
                    entry["processor"] = {"name": "media-ingest", "version": version}
                if isinstance(fingerprint, str):
                    entry["configuration_fingerprint"] = fingerprint
        else:
            entry["processor"] = {
                "name": "media-ingest",
                "version": "workspace-contract-v1",
            }
        self.field_sources.setdefault(target, []).append(entry)

    def missing(self, target: str) -> None:
        if target not in self.missing_fields:
            self.missing_fields.append(target)

    def invalid(
        self, target: str, pointer: str, value: Any, reason: str, document: str
    ) -> None:
        item = {
            "target": target,
            "source_document": document,
            "source_pointer": pointer,
            "raw_value": value,
            "reason": reason,
        }
        self.invalid_values.append(item)
        self.warnings.append({"code": "INVALID_SOURCE_VALUE", **item})
        self.add(
            target,
            pointer,
            value,
            document=document,
            selection="rejected",
            rule="safe_scalars_v1",
        )


def _text(value: Any) -> tuple[str | None, str | None]:
    if value is None:
        return None, None
    if not isinstance(value, str):
        return None, "expected a string"
    clean = value.strip()
    if not clean:
        return None, "empty strings are not values"
    return clean, None


def _integer(
    value: Any, *, minimum: int | None = None, maximum: int | None = None
) -> tuple[int | None, str | None]:
    if value is None:
        return None, None
    if isinstance(value, bool):
        return None, "boolean is not an integer"
    parsed: int
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str) and re.fullmatch(r"[+-]?\d+", value.strip()):
        parsed = int(value.strip())
    else:
        return None, "expected an integer or an unambiguous integer string"
    if minimum is not None and parsed < minimum:
        return None, f"value must be at least {minimum}"
    if maximum is not None and parsed > maximum:
        return None, f"value must be at most {maximum}"
    return parsed, None


def _number(
    value: Any, *, minimum: float | None = None, maximum: float | None = None
) -> tuple[float | None, str | None]:
    if value is None:
        return None, None
    if isinstance(value, bool):
        return None, "boolean is not a number"
    parsed: float
    if isinstance(value, (int, float)):
        parsed = float(value)
    elif isinstance(value, str) and re.fullmatch(
        r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", value.strip()
    ):
        parsed = float(value.strip())
    else:
        return None, "expected a number or an unambiguous numeric string without units"
    if not math.isfinite(parsed):
        return None, "number must be finite"
    if minimum is not None and parsed < minimum:
        return None, f"value must be at least {minimum}"
    if maximum is not None and parsed > maximum:
        return None, f"value must be at most {maximum}"
    return parsed, None


def _boolean(value: Any) -> tuple[bool | None, str | None]:
    if value is None:
        return None, None
    if not isinstance(value, bool):
        return None, "expected a boolean"
    return value, None


def _datetime(value: Any) -> tuple[str | None, str | None]:
    text, error = _text(value)
    if error or text is None:
        return None, error
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None, "expected an ISO-8601 datetime"
    return text, None


def _timezone(value: Any) -> tuple[str | None, str | None]:
    if value is None:
        return None, None
    text, error = _text(value)
    if error or text is None:
        return None, error
    if not _OFFSET.fullmatch(text):
        return None, "expected an offset from -14:00 to +14:00"
    return text, None


def _gps(value: Any) -> tuple[dict[str, float] | None, str | None]:
    if value is None:
        return None, None
    if not isinstance(value, dict) or set(value) != {"latitude", "longitude"}:
        return None, "expected latitude and longitude"
    latitude, lat_error = _number(value["latitude"], minimum=-90, maximum=90)
    longitude, lon_error = _number(value["longitude"], minimum=-180, maximum=180)
    if lat_error or lon_error or latitude is None or longitude is None:
        return None, lat_error or lon_error or "both coordinates are required"
    return {"latitude": latitude, "longitude": longitude}, None


def _convert_field(
    evidence: _Evidence,
    technical: dict[str, Any],
    field: str,
    target: str,
    converter: Callable[[Any], tuple[Any, str | None]],
) -> Any:
    value = technical.get(field)
    pointer = f"/technical/{field}"
    document = evidence.asset.metadata_location or "metadata:missing"
    converted, error = converter(value)
    if error is not None:
        evidence.invalid(target, pointer, value, error, document)
        return None
    if converted is None:
        evidence.missing(target)
        return None
    evidence.add(
        target,
        pointer,
        value,
        document=document,
        selection="selected",
        rule="safe_scalars_v1",
    )
    return converted


def _identity(asset: AssetInput, evidence: _Evidence) -> dict[str, Any]:
    catalog = asset.catalog
    for field in (
        "asset_id", "sha256", "media_type", "size_bytes", "availability", "sources"
    ):
        evidence.add(
            f"/identity/{field}",
            f"{asset.catalog_pointer}/{field}",
            catalog[field],
            document=asset.catalog_location,
            selection="selected",
            rule="catalog_authoritative",
        )

    detected = asset.metadata.get("detected") if asset.metadata else None
    detected = detected if isinstance(detected, dict) else {}
    selected: dict[str, str | None] = {}
    for field in ("format", "mime_type"):
        target = f"/identity/{field}"
        catalog_value = catalog.get(field)
        detected_value = detected.get(field)
        detected_text, detected_error = _text(detected_value)
        if detected_error is not None:
            evidence.invalid(
                target,
                f"/detected/{field}",
                detected_value,
                detected_error,
                asset.metadata_location or "metadata:missing",
            )
        catalog_text, _ = _text(catalog_value)
        if detected_text is not None:
            selected[field] = detected_text
            evidence.add(
                target,
                f"/detected/{field}",
                detected_value,
                document=asset.metadata_location or "metadata:missing",
                selection="selected",
                rule="detected_over_catalog",
            )
            if catalog_text is not None:
                evidence.add(
                    target,
                    f"{asset.catalog_pointer}/{field}",
                    catalog_value,
                    document=asset.catalog_location,
                    selection="candidate",
                    rule="detected_over_catalog",
                )
                if detected_text.casefold() != catalog_text.casefold():
                    evidence.conflicts.append(
                        {
                            "code": "DETECTED_REFINES_CATALOG",
                            "target": target,
                            "candidates": [catalog_text, detected_text],
                            "resolution": "selected",
                            "policy": "detected_over_catalog",
                        }
                    )
        else:
            selected[field] = catalog_text
            if catalog_text is None:
                evidence.missing(target)
            else:
                evidence.add(
                    target,
                    f"{asset.catalog_pointer}/{field}",
                    catalog_value,
                    document=asset.catalog_location,
                    selection="selected",
                    rule="catalog_fallback",
                )
    return {
        "asset_id": asset.asset_id,
        "sha256": asset.sha256,
        "media_type": catalog["media_type"],
        "size_bytes": catalog["size_bytes"],
        "format": selected["format"],
        "mime_type": selected["mime_type"],
        "availability": catalog["availability"],
        "sources": catalog["sources"],
    }


def _technical(asset: AssetInput, evidence: _Evidence) -> dict[str, Any]:
    raw = asset.metadata.get("technical") if asset.metadata else None
    technical = raw if isinstance(raw, dict) else {}
    if raw is not None and not isinstance(raw, dict):
        evidence.invalid(
            "/technical", "/technical", raw, "expected an object",
            asset.metadata_location or "metadata:missing",
        )
    text_converter = _text
    common = {
        field: _convert_field(
            evidence, technical, field, f"/technical/common/{field}", text_converter
        )
        for field in _COMMON_FIELDS
    }
    if asset.catalog["media_type"] == "image":
        converters: dict[str, Callable[[Any], tuple[Any, str | None]]] = {
            "width": lambda value: _integer(value, minimum=1),
            "height": lambda value: _integer(value, minimum=1),
            "orientation": lambda value: _integer(value, minimum=1, maximum=8),
            "color_space": _text,
            "lens": _text,
            "focal_length_mm": lambda value: _number(value, minimum=0),
            "exposure_seconds": lambda value: _number(value, minimum=0),
            "aperture": lambda value: _number(value, minimum=0),
            "iso": lambda value: _integer(value, minimum=0),
            "flash": _text,
            "gps": _gps,
        }
        image = {
            field: _convert_field(
                evidence, technical, field, f"/technical/image/{field}", converters[field]
            )
            for field in _IMAGE_FIELDS
        }
        return {"common": common, "image": image, "video": None}
    converters = {
        "container": _text,
        "duration_seconds": lambda value: _number(value, minimum=0),
        "width": lambda value: _integer(value, minimum=1),
        "height": lambda value: _integer(value, minimum=1),
        "fps": lambda value: _number(value, minimum=0),
        "video_codec": _text,
        "bitrate": lambda value: _integer(value, minimum=0),
        "rotation": lambda value: _integer(value, minimum=-360, maximum=360),
        "audio_present": _boolean,
        "audio_codec": _text,
        "sample_rate": lambda value: _integer(value, minimum=1),
        "channels": lambda value: _integer(value, minimum=1),
    }
    video: dict[str, Any] = {}
    for field in _VIDEO_FIELDS:
        if field in {"audio_codec", "sample_rate", "channels"}:
            continue
        video[field] = _convert_field(
            evidence, technical, field, f"/technical/video/{field}", converters[field]
        )
    for field in ("audio_codec", "sample_rate", "channels"):
        if video["audio_present"] is False:
            video[field] = None
        else:
            video[field] = _convert_field(
                evidence, technical, field, f"/technical/video/{field}", converters[field]
            )
    return {"common": common, "image": None, "video": video}


def _temporal(asset: AssetInput, evidence: _Evidence) -> dict[str, Any]:
    raw = asset.metadata.get("capture") if asset.metadata else None
    capture = raw if isinstance(raw, dict) else {}
    document = asset.metadata_location or "metadata:missing"
    if raw is not None and not isinstance(raw, dict):
        evidence.invalid("/temporal/capture", "/capture", raw, "expected an object", document)
    values: dict[str, Any] = {}
    converters: dict[str, Callable[[Any], tuple[Any, str | None]]] = {
        "datetime": _datetime,
        "source": _text,
        "timezone_offset": _timezone,
        "filesystem_fallback": _boolean,
    }
    for field, converter in converters.items():
        target = f"/temporal/capture/{field}"
        value = capture.get(field)
        converted, error = converter(value)
        if error is not None:
            evidence.invalid(target, f"/capture/{field}", value, error, document)
        elif converted is None:
            evidence.missing(target)
        else:
            evidence.add(
                target, f"/capture/{field}", value, document=document,
                selection="selected", rule="ingest_capture_selection",
            )
        values[field] = converted
    if values["filesystem_fallback"] is None:
        values["filesystem_fallback"] = False
    if values["datetime"] is None:
        quality = "missing"
    elif values["filesystem_fallback"]:
        quality = "filesystem_fallback"
    else:
        quality = "source_timestamp"
    evidence.add(
        "/temporal/capture/quality",
        "/capture/filesystem_fallback",
        values["filesystem_fallback"],
        document=document,
        selection="derived",
        rule="capture_quality_v1",
        layer="deterministic_interpretation",
    )
    return {"capture": {**values, "quality": quality}, "session_candidates": []}


def normalize_asset(asset: AssetInput) -> dict[str, Any]:
    evidence = _Evidence(asset)
    identity = _identity(asset, evidence)
    technical = _technical(asset, evidence)
    temporal = _temporal(asset, evidence)
    for issue in asset.issues:
        evidence.warnings.append(
            {
                "code": issue.code,
                "target": "/metadata",
                "source_document": issue.location,
                "reason": issue.message,
            }
        )
        evidence.missing("/metadata")
    analyses = {
        "session_grouper": {"status": "not_analyzed"},
        "video_keyframes": {
            "status": "not_analyzed" if identity["media_type"] == "video" else "not_applicable"
        },
        "vision": {"status": "not_analyzed"},
        "faces": {"status": "not_analyzed"},
        "quality": {"status": "not_analyzed"},
    }
    return {
        "identity": identity,
        "technical": technical,
        "temporal": temporal,
        "semantic": {
            "status": "not_analyzed",
            "observations": [],
            "facets": {
                "activities": [], "objects": [], "environment": [],
                "visual_attributes": [], "tags": [],
            },
        },
        "people": {
            "status": "not_analyzed",
            "detected_face_count": None,
            "face_observations": [],
            "anonymous_cluster_refs": [],
            "vision_people_observations": [],
        },
        "event": {
            "status": "not_analyzed",
            "machine_candidates": [],
            "user_assertion_available": False,
        },
        "quality": {"technical_assessment": None, "status": "not_analyzed"},
        "provenance": {
            "field_sources": {
                key: value for key, value in sorted(evidence.field_sources.items())
            }
        },
        "completeness": {
            "source_available": identity["availability"] == "available",
            "analyses": analyses,
            "missing_fields": sorted(evidence.missing_fields),
            "invalid_values": sorted(
                evidence.invalid_values,
                key=lambda item: (item["target"], item["source_pointer"]),
            ),
            "conflicts": sorted(evidence.conflicts, key=lambda item: item["target"]),
            "warnings": sorted(
                evidence.warnings,
                key=lambda item: (item["code"], item.get("target", "")),
            ),
        },
    }
