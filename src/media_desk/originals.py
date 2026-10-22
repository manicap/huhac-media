from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
from typing import Any, Literal

from media_desk.config import ORIGINALS_MAPPING_VERIFICATION, OriginalsMapping


MappingState = Literal[
    "unconfigured",
    "valid_sampled",
    "unavailable",
    "binding_mismatch",
    "storage_mismatch",
    "no_verifiable_assets",
    "invalid",
]

_SHA256 = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class MappingValidation:
    state: MappingState
    message: str
    workspace_id: str = ""
    source_root: str = ""
    requested_root: Path | None = None
    resolved_root: Path | None = None
    eligible_assets: int = 0
    accessible_assets: int = 0
    sampled_assets: int = 0
    matched_assets: int = 0
    mapping: OriginalsMapping | None = None

    @property
    def valid(self) -> bool:
        return self.state == "valid_sampled" and self.mapping is not None


@dataclass(frozen=True)
class _Candidate:
    sha256: str
    media_type: str
    size_bytes: int
    path: Path


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read {label}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid {label}: expected an object")
    return payload


def _safe_catalog(workspace: Path) -> tuple[str, str, list[dict[str, Any]]]:
    root = workspace.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Workspace is not a directory")
    manifest = _read_json(root / "workspace.json", "workspace manifest")
    if manifest.get("workspace_contract_version") != 1:
        raise ValueError("Unsupported workspace contract version")
    workspace_id = manifest.get("workspace_id")
    location = manifest.get("asset_catalog")
    if not isinstance(workspace_id, str) or not workspace_id:
        raise ValueError("Invalid workspace_id")
    if not isinstance(location, str) or "\\" in location:
        raise ValueError("Invalid asset catalog path")
    pure = PurePosixPath(location)
    if pure.is_absolute() or ".." in pure.parts:
        raise ValueError("Asset catalog path escapes workspace")
    catalog_path = root.joinpath(*pure.parts).resolve(strict=True)
    if root not in catalog_path.parents or not catalog_path.is_file():
        raise ValueError("Asset catalog path escapes workspace")
    catalog = _read_json(catalog_path, "asset catalog")
    if catalog.get("workspace_contract_version") != 1 or catalog.get("workspace_id") != workspace_id:
        raise ValueError("Asset catalog identity does not match workspace")
    source_root = catalog.get("source_root")
    if not isinstance(source_root, str) or not source_root or not (
        PurePosixPath(source_root).is_absolute() or PureWindowsPath(source_root).is_absolute()
    ):
        raise ValueError("Invalid asset catalog source_root")
    entries = catalog.get("assets")
    if not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries):
        raise ValueError("Invalid asset catalog assets")
    return workspace_id, source_root, entries


def _relative_paths(entry: dict[str, Any]) -> tuple[str, ...]:
    sources = entry.get("sources")
    if not isinstance(sources, list):
        return ()
    paths: set[str] = set()
    for source in sources:
        if not isinstance(source, dict) or source.get("status") != "active":
            continue
        relative = source.get("relative_path")
        if not isinstance(relative, str) or not relative or "\\" in relative:
            continue
        pure = PurePosixPath(relative)
        if pure.is_absolute() or ".." in pure.parts:
            continue
        paths.add(relative)
    return tuple(sorted(paths))


def resolve_mapped_original(local_root: Path, relative_paths: tuple[str, ...]) -> Path | None:
    try:
        root = Path(local_root).resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if not root.is_dir():
        return None
    for relative in sorted(set(relative_paths)):
        if not relative or "\\" in relative:
            continue
        pure = PurePosixPath(relative)
        if pure.is_absolute() or ".." in pure.parts:
            continue
        try:
            candidate = root.joinpath(*pure.parts).resolve(strict=True)
        except (OSError, RuntimeError):
            continue
        if root in candidate.parents and candidate.is_file():
            return candidate
    return None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _evenly_spaced(items: list[_Candidate], count: int) -> list[_Candidate]:
    if count <= 0:
        return []
    if count >= len(items):
        return items
    if count == 1:
        return [items[len(items) // 2]]
    indices = [(index * (len(items) - 1)) // (count - 1) for index in range(count)]
    return [items[index] for index in indices]


def _sample(candidates: list[_Candidate], limit: int) -> list[_Candidate]:
    limit = max(1, limit)
    if len(candidates) <= limit:
        return sorted(candidates, key=lambda item: (item.media_type, item.size_bytes, item.sha256))
    images = sorted(
        (item for item in candidates if item.media_type == "image"),
        key=lambda item: (item.size_bytes, item.sha256),
    )
    videos = sorted(
        (item for item in candidates if item.media_type == "video"),
        key=lambda item: (item.size_bytes, item.sha256),
    )
    if not images or not videos:
        return _evenly_spaced(images or videos, limit)
    image_count = min(len(images), limit // 2)
    video_count = min(len(videos), limit // 2)
    remaining = limit - image_count - video_count
    image_extra = min(remaining, len(images) - image_count)
    image_count += image_extra
    remaining -= image_extra
    video_count += min(remaining, len(videos) - video_count)
    return _evenly_spaced(images, image_count) + _evenly_spaced(videos, video_count)


def bind_mapping(
    *,
    workspace_id: str,
    source_root: str,
    configured: OriginalsMapping | None,
) -> MappingValidation:
    if configured is None:
        return MappingValidation("unconfigured", "Lokální mapování originálů není nastaveno.")
    if configured.workspace_id != workspace_id or configured.source_root != source_root:
        return MappingValidation(
            "binding_mismatch",
            "Uložené mapování nepatří k tomuto workspace nebo source_root.",
            workspace_id,
            source_root,
            configured.local_root,
            eligible_assets=configured.eligible_assets,
            sampled_assets=configured.verified_assets,
        )
    try:
        resolved = configured.local_root.resolve(strict=True)
    except (OSError, RuntimeError):
        return MappingValidation(
            "unavailable",
            "Uložený kořen originálů nyní není dostupný; mapování zůstává uloženo.",
            workspace_id,
            source_root,
            configured.local_root,
            eligible_assets=configured.eligible_assets,
            sampled_assets=configured.verified_assets,
        )
    if not resolved.is_dir():
        return MappingValidation(
            "unavailable",
            "Uložený kořen originálů není adresář; mapování zůstává uloženo.",
            workspace_id,
            source_root,
            configured.local_root,
            resolved,
            eligible_assets=configured.eligible_assets,
            sampled_assets=configured.verified_assets,
        )
    return MappingValidation(
        "valid_sampled",
        "Uložené mapování je navázané a kořen je dostupný; SHA-256 vzorek se při startu neopakuje.",
        workspace_id,
        source_root,
        configured.local_root,
        resolved,
        eligible_assets=configured.eligible_assets,
        sampled_assets=configured.verified_assets,
        matched_assets=configured.verified_assets,
        mapping=OriginalsMapping(
            configured.workspace_id,
            configured.source_root,
            resolved,
            configured.verification,
            configured.verified_assets,
            configured.eligible_assets,
        ),
    )


def validate_mapping_candidate(
    workspace: Path,
    local_root: Path,
    *,
    sample_limit: int = 16,
) -> MappingValidation:
    requested = Path(local_root)
    try:
        workspace_id, source_root, entries = _safe_catalog(Path(workspace))
    except (OSError, RuntimeError, ValueError) as exc:
        return MappingValidation("invalid", f"Workspace nelze ověřit: {exc}", requested_root=requested)
    try:
        root = requested.expanduser().resolve(strict=True)
    except (OSError, RuntimeError):
        return MappingValidation(
            "unavailable",
            "Zadaný kořen originálů není dostupný.",
            workspace_id,
            source_root,
            requested,
        )
    if not root.is_dir():
        return MappingValidation(
            "unavailable",
            "Zadaný kořen originálů není adresář.",
            workspace_id,
            source_root,
            requested,
            root,
        )

    eligible = 0
    candidates: list[_Candidate] = []
    for entry in entries:
        if entry.get("availability") != "available":
            continue
        relative_paths = _relative_paths(entry)
        if not relative_paths:
            continue
        eligible += 1
        sha256 = entry.get("sha256")
        media_type = entry.get("media_type")
        size_bytes = entry.get("size_bytes")
        if (
            not isinstance(sha256, str)
            or not _SHA256.fullmatch(sha256)
            or media_type not in {"image", "video"}
            or isinstance(size_bytes, bool)
            or not isinstance(size_bytes, int)
            or size_bytes < 0
        ):
            return MappingValidation(
                "invalid",
                "Katalog obsahuje neplatnou identitu nebo velikost assetu.",
                workspace_id,
                source_root,
                requested,
                root,
                eligible,
                len(candidates),
            )
        path = resolve_mapped_original(root, relative_paths)
        if path is None:
            continue
        try:
            actual_size = path.stat().st_size
        except OSError:
            continue
        if actual_size != size_bytes:
            return MappingValidation(
                "storage_mismatch",
                "Velikost dostupného originálu neodpovídá katalogu; mapování nebylo uloženo.",
                workspace_id,
                source_root,
                requested,
                root,
                eligible,
                len(candidates) + 1,
            )
        candidates.append(_Candidate(sha256, media_type, size_bytes, path))

    if not candidates:
        return MappingValidation(
            "no_verifiable_assets",
            "V kořeni nebyl nalezen žádný dostupný asset vhodný pro SHA-256 vzorek.",
            workspace_id,
            source_root,
            requested,
            root,
            eligible,
        )

    selected = _sample(candidates, min(16, max(1, sample_limit)))
    matched = 0
    for candidate in selected:
        try:
            digest = _sha256_file(candidate.path)
        except OSError:
            return MappingValidation(
                "unavailable",
                "Vybraný soubor přestal být během kontroly dostupný.",
                workspace_id,
                source_root,
                requested,
                root,
                eligible,
                len(candidates),
                len(selected),
                matched,
            )
        if digest != candidate.sha256:
            return MappingValidation(
                "storage_mismatch",
                "SHA-256 vzorku neodpovídá katalogu; mapování nebylo uloženo.",
                workspace_id,
                source_root,
                requested,
                root,
                eligible,
                len(candidates),
                len(selected),
                matched,
            )
        matched += 1

    mapping = OriginalsMapping(
        workspace_id,
        source_root,
        root,
        ORIGINALS_MAPPING_VERIFICATION,
        matched,
        eligible,
    )
    return MappingValidation(
        "valid_sampled",
        f"Vzorková SHA-256 kontrola ověřila {matched} z {eligible} způsobilých assetů; nejde o úplnou kontrolu integrity archivu.",
        workspace_id,
        source_root,
        requested,
        root,
        eligible,
        len(candidates),
        len(selected),
        matched,
        mapping,
    )
