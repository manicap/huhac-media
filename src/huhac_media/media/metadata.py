from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from huhac_media.domain.enums import MediaType
from huhac_media.domain.models import MetadataResult, ScannedFile
from huhac_media.media.capture_time import select_capture_datetime


class Probe(Protocol):
    def probe(self, path: Path) -> dict: ...


def _first(raw: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in raw and raw[key] not in (None, ""):
            return raw[key]
    return None


def _fps(value: Any) -> float | None:
    if not isinstance(value, str) or value in {"0/0", "N/A"}:
        return None
    try:
        numerator, denominator = value.split("/", 1)
        return float(numerator) / float(denominator)
    except (ValueError, ZeroDivisionError):
        return None


class MetadataExtractor:
    def __init__(self, exiftool: Probe, ffprobe: Probe | None = None):
        self.exiftool = exiftool
        self.ffprobe = ffprobe

    def extract(self, scanned: ScannedFile) -> MetadataResult:
        exif = self.exiftool.probe(scanned.absolute_path)
        ffdata = None
        if scanned.media_type == MediaType.VIDEO and self.ffprobe is not None:
            ffdata = self.ffprobe.probe(scanned.absolute_path)
        filesystem_mtime = datetime.fromtimestamp(
            scanned.filesystem_mtime_ns / 1_000_000_000, tz=timezone.utc
        ).isoformat()
        normalized = {
            "capture": select_capture_datetime(exif, ffdata, filesystem_mtime),
            "technical": self._technical(scanned.media_type, exif, ffdata),
        }
        return MetadataResult(normalized=normalized, raw_exiftool=exif, raw_ffprobe=ffdata)

    @staticmethod
    def _technical(media_type: MediaType, exif: dict, ffdata: dict | None) -> dict:
        common = {
            "manufacturer": _first(exif, "EXIF:Make", "QuickTime:Make"),
            "camera_model": _first(exif, "EXIF:Model", "QuickTime:Model"),
            "software": _first(exif, "EXIF:Software", "QuickTime:Software"),
        }
        if media_type == MediaType.IMAGE:
            gps_lat = _first(exif, "Composite:GPSLatitude", "EXIF:GPSLatitude")
            gps_lon = _first(exif, "Composite:GPSLongitude", "EXIF:GPSLongitude")
            return common | {
                "width": _first(exif, "File:ImageWidth", "EXIF:ExifImageWidth"),
                "height": _first(exif, "File:ImageHeight", "EXIF:ExifImageHeight"),
                "orientation": _first(exif, "EXIF:Orientation"),
                "color_space": _first(exif, "EXIF:ColorSpace"),
                "lens": _first(exif, "EXIF:LensModel", "Composite:LensID"),
                "focal_length_mm": _first(exif, "EXIF:FocalLength"),
                "exposure_seconds": _first(exif, "EXIF:ExposureTime"),
                "aperture": _first(exif, "EXIF:FNumber"),
                "iso": _first(exif, "EXIF:ISO"),
                "flash": _first(exif, "EXIF:Flash"),
                "gps": {"latitude": gps_lat, "longitude": gps_lon}
                if gps_lat is not None and gps_lon is not None
                else None,
            }
        streams = (ffdata or {}).get("streams", [])
        video = next((stream for stream in streams if stream.get("codec_type") == "video"), {})
        audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
        format_data = (ffdata or {}).get("format", {})
        return common | {
            "container": format_data.get("format_name"),
            "duration_seconds": _number(format_data.get("duration")),
            "width": video.get("width"),
            "height": video.get("height"),
            "fps": _fps(video.get("avg_frame_rate") or video.get("r_frame_rate")),
            "video_codec": video.get("codec_name"),
            "bitrate": _integer(format_data.get("bit_rate")),
            "rotation": (video.get("tags") or {}).get("rotate"),
            "audio_present": audio is not None,
            "audio_codec": audio.get("codec_name") if audio else None,
            "sample_rate": _integer(audio.get("sample_rate")) if audio else None,
            "channels": audio.get("channels") if audio else None,
        }


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _integer(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
