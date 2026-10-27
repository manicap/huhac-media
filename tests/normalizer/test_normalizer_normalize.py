from __future__ import annotations

from normalizer.contract import load_workspace
from normalizer.normalize import normalize_asset
from normalizer.schema import validate_normalized_asset


def test_normalizes_image_source_facts_temporal_and_provenance(workspace_factory):
    asset = next(
        item
        for item in load_workspace(workspace_factory()).assets
        if item.catalog["media_type"] == "image"
    )
    result = normalize_asset(asset)
    assert validate_normalized_asset(result) == []
    assert result["identity"]["asset_id"] == asset.asset_id
    assert isinstance(result["technical"]["image"], dict)
    assert result["technical"]["image"]["width"] == 6000
    assert result["technical"]["image"]["height"] == 4000
    assert result["technical"]["image"]["focal_length_mm"] == 35.0
    assert result["technical"]["image"]["gps"] == {
        "latitude": 50.1,
        "longitude": 14.4,
    }
    assert result["temporal"]["capture"]["quality"] == "source_timestamp"
    sources = result["provenance"]["field_sources"]["/technical/image/width"]
    assert sources[0]["source_pointer"] == "/technical/width"
    assert sources[0]["processor"] == {"name": "media-ingest", "version": "metadata-v2"}
    identity_source = result["provenance"]["field_sources"]["/identity/asset_id"][0]
    assert identity_source["source_document"] == "metadata/catalog.json"
    assert identity_source["source_pointer"].startswith("/assets/")
    assert result["semantic"]["status"] == "not_analyzed"
    assert result["people"]["status"] == "not_analyzed"


def test_normalizes_video_and_unavailable_source(workspace_factory):
    root = workspace_factory(
        [{"name": "video", "media_type": "video", "availability": "unavailable"}]
    )
    result = normalize_asset(load_workspace(root).assets[0])
    assert result["technical"]["image"] is None
    assert result["technical"]["video"]["duration_seconds"] == 12.5
    assert result["technical"]["video"]["rotation"] == 90
    assert result["completeness"]["source_available"] is False
    assert result["completeness"]["analyses"]["video_keyframes"]["status"] == "not_analyzed"


def test_video_without_audio_does_not_report_audio_fields_missing(workspace_factory):
    technical = {
        "manufacturer": None,
        "camera_model": None,
        "software": None,
        "container": "mp4",
        "duration_seconds": 1,
        "width": 1920,
        "height": 1080,
        "fps": 25,
        "video_codec": "h264",
        "bitrate": 1,
        "rotation": 0,
        "audio_present": False,
        "audio_codec": None,
        "sample_rate": None,
        "channels": None,
    }
    root = workspace_factory([{"name": "silent", "media_type": "video", "technical": technical}])
    result = normalize_asset(load_workspace(root).assets[0])
    missing = result["completeness"]["missing_fields"]
    assert "/technical/video/audio_codec" not in missing
    assert "/technical/video/sample_rate" not in missing
    assert "/technical/video/channels" not in missing


def test_safe_conversions_reject_units_ranges_and_ambiguous_orientation(workspace_factory):
    root = workspace_factory(
        [{
            "name": "unsafe",
            "technical": {
                "manufacturer": 42,
                "camera_model": "Camera",
                "software": None,
                "width": "6000 px",
                "height": -1,
                "orientation": "Horizontal (normal)",
                "color_space": "sRGB",
                "lens": None,
                "focal_length_mm": "35 mm",
                "exposure_seconds": "1/125",
                "aperture": float("inf"),
                "iso": True,
                "flash": None,
                "gps": {"latitude": 91, "longitude": 14},
            },
        }]
    )
    image = normalize_asset(load_workspace(root).assets[0])
    technical = image["technical"]["image"]
    assert technical["width"] is None
    assert technical["orientation"] is None
    assert technical["focal_length_mm"] is None
    assert technical["exposure_seconds"] is None
    assert technical["gps"] is None
    invalid = image["completeness"]["invalid_values"]
    assert {item["target"] for item in invalid} >= {
        "/technical/common/manufacturer",
        "/technical/image/width",
        "/technical/image/orientation",
        "/technical/image/focal_length_mm",
    }
    rejected = image["provenance"]["field_sources"]["/technical/image/width"][0]
    assert rejected["observed_value"] == "6000 px"
    assert rejected["selection"] == "rejected"


def test_capture_missing_invalid_and_filesystem_fallback_are_distinct(workspace_factory):
    fallback = workspace_factory(
        [{"name": "fallback", "capture": {"datetime": "2026-10-26T12:00:00+00:00", "source": "filesystem:mtime", "timezone_offset": "+00:00", "filesystem_fallback": True}}]
    )
    fallback_result = normalize_asset(load_workspace(fallback).assets[0])
    assert fallback_result["temporal"]["capture"]["quality"] == "filesystem_fallback"

    invalid = workspace_factory(
        [{"name": "invalid", "capture": {"datetime": "not-a-date", "source": None, "timezone_offset": "+99:00", "filesystem_fallback": "false"}}]
    )
    invalid_result = normalize_asset(load_workspace(invalid).assets[0])
    assert invalid_result["temporal"]["capture"]["quality"] == "missing"
    assert "/temporal/capture/datetime" not in invalid_result["completeness"]["missing_fields"]
    assert {item["target"] for item in invalid_result["completeness"]["invalid_values"]} >= {
        "/temporal/capture/datetime",
        "/temporal/capture/timezone_offset",
        "/temporal/capture/filesystem_fallback",
    }


def test_missing_metadata_is_not_a_fake_empty_success(workspace_factory):
    root = workspace_factory([{"name": "missing", "metadata": None}])
    result = normalize_asset(load_workspace(root).assets[0])
    assert "/metadata" in result["completeness"]["missing_fields"]
    assert result["completeness"]["warnings"][0]["code"] == "MISSING_METADATA_DOCUMENT"
    assert result["temporal"]["capture"]["quality"] == "missing"
