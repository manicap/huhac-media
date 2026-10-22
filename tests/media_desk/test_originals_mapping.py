from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from media_desk.config import ORIGINALS_MAPPING_VERIFICATION, OriginalsMapping
from media_desk.originals import (
    bind_mapping,
    resolve_mapped_original,
    validate_mapping_candidate,
)


def _publish_hashable(builder, specs: list[tuple[int, str, bytes]]) -> Path:
    for index, media_type, content in specs:
        entry = builder.add_asset(index, media_type, original=False)
        digest = hashlib.sha256(content).hexdigest()
        entry["asset_id"] = f"sha256:{digest}"
        entry["sha256"] = digest
        entry["size_bytes"] = len(content)
        target = builder.originals.joinpath(*entry["sources"][0]["relative_path"].split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    return builder.publish()


def test_validates_deterministic_sample_and_builds_exact_binding(workspace_builder) -> None:
    specs = [
        (index, "video" if index % 3 == 0 else "image", bytes([index]) * (index + 10))
        for index in range(1, 25)
    ]
    workspace = _publish_hashable(workspace_builder, specs)

    result = validate_mapping_candidate(workspace, workspace_builder.originals)

    assert result.valid
    assert result.sampled_assets == 16
    assert result.matched_assets == 16
    assert result.eligible_assets == 24
    assert result.mapping == OriginalsMapping(
        workspace_builder.workspace_id,
        str(workspace_builder.originals.resolve()),
        workspace_builder.originals.resolve(),
        ORIGINALS_MAPPING_VERIFICATION,
        16,
        24,
    )
    assert "nejde o úplnou kontrolu integrity" in result.message


def test_small_library_hashes_every_accessible_asset(workspace_builder, monkeypatch) -> None:
    workspace = _publish_hashable(
        workspace_builder,
        [(1, "image", b"first"), (2, "video", b"second")],
    )
    calls: list[Path] = []

    def counted(path: Path) -> str:
        calls.append(path)
        return hashlib.sha256(path.read_bytes()).hexdigest()

    monkeypatch.setattr("media_desk.originals._sha256_file", counted)
    result = validate_mapping_candidate(workspace, workspace_builder.originals)

    assert result.valid
    assert result.sampled_assets == 2
    assert len(calls) == 2


def test_hash_mismatch_rejects_mapping(workspace_builder) -> None:
    workspace = _publish_hashable(workspace_builder, [(1, "image", b"expected")])
    target = next(path for path in workspace_builder.originals.rglob("*") if path.is_file())
    target.write_bytes(b"tampered")
    catalog_path = workspace / "metadata/catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["assets"][0]["size_bytes"] = len(b"tampered")
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")

    result = validate_mapping_candidate(workspace, workspace_builder.originals)

    assert result.state == "storage_mismatch"
    assert result.mapping is None


def test_missing_root_and_no_candidates_are_not_valid(workspace_builder, tmp_path: Path) -> None:
    workspace_builder.add_asset(1, original=False)
    workspace = workspace_builder.publish()

    missing = validate_mapping_candidate(workspace, tmp_path / "missing")
    empty = tmp_path / "empty"
    empty.mkdir()
    no_candidates = validate_mapping_candidate(workspace, empty)

    assert missing.state == "unavailable"
    assert no_candidates.state == "no_verifiable_assets"
    assert missing.mapping is None and no_candidates.mapping is None


def test_binding_is_exact_and_startup_does_not_hash(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "originals"
    root.mkdir()
    mapping = OriginalsMapping(
        "workspace-test",
        r"D:\Media",
        root,
        ORIGINALS_MAPPING_VERIFICATION,
        4,
        10,
    )
    monkeypatch.setattr(
        "media_desk.originals._sha256_file",
        lambda _path: pytest.fail("startup binding must not hash"),
    )

    valid = bind_mapping(workspace_id="workspace-test", source_root=r"D:\Media", configured=mapping)
    mismatch = bind_mapping(workspace_id="other", source_root=r"D:\Media", configured=mapping)

    assert valid.valid
    assert valid.resolved_root == root.resolve()
    assert mismatch.state == "binding_mismatch"


def test_unavailable_binding_keeps_configured_mapping(tmp_path: Path) -> None:
    mapping = OriginalsMapping(
        "workspace-test",
        "/old/root",
        tmp_path / "offline",
        ORIGINALS_MAPPING_VERIFICATION,
        1,
        1,
    )

    result = bind_mapping(workspace_id="workspace-test", source_root="/old/root", configured=mapping)

    assert result.state == "unavailable"
    assert result.requested_root == mapping.local_root
    assert result.mapping is None


def test_resolver_rejects_traversal_backslash_and_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    inside = root / "folder/media.jpg"
    inside.parent.mkdir()
    inside.write_bytes(b"inside")

    assert resolve_mapped_original(root, ("../secret", r"folder\media.jpg", "folder/media.jpg")) == inside

    outside = tmp_path / "outside.jpg"
    outside.write_bytes(b"outside")
    link = root / "escape.jpg"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("Symlink creation is unavailable on this Windows host")
    assert resolve_mapped_original(root, ("escape.jpg",)) is None
