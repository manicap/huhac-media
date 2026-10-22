from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

import pytest
from fastapi.testclient import TestClient

from media_desk.config import Settings, load_settings, save_profile_workspace
from media_desk.web import create_app


def _state(root: Path) -> dict[str, tuple[int, int, str]]:
    return {
        str(path.relative_to(root)): (
            path.stat().st_size,
            path.stat().st_mtime_ns,
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in root.rglob("*")
        if path.is_file()
    }


def _profile_settings(config: Path, workspace: Path | None = None, *, host: str = "127.0.0.1") -> Settings:
    return Settings(
        workspace=workspace,
        host=host,
        profile_config_path=config,
        workspace_source="profile" if workspace is not None else "default",
    )


def _client(app) -> TestClient:
    return TestClient(app, base_url="http://127.0.0.1")


def _csrf(client: TestClient) -> str:
    page = client.get("/settings")
    match = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
    token = match.group(1) if match else client.cookies.get("media_desk_csrf")
    assert page.status_code == 200 and token
    return token


def _post(client: TestClient, endpoint: str, token: str, workspace: str, **extra):
    return client.post(
        endpoint,
        data={"csrf_token": token, "workspace": workspace, **extra},
        headers={"Origin": "http://127.0.0.1"},
    )


def _mapping_post(
    client: TestClient,
    endpoint: str,
    token: str,
    local_root: str | None = None,
    **extra,
):
    data = {"csrf_token": token, **extra}
    if local_root is not None:
        data["local_root"] = local_root
    return client.post(endpoint, data=data, headers={"Origin": "http://127.0.0.1"})


def _original_url(client: TestClient, sha256: str) -> str:
    response = client.get(f"/api/assets/{sha256}")
    assert response.status_code == 200
    url = response.json()["original_url"]
    assert url
    return url


def _publish_mappable_workspace(
    workspace_builder, *, source_root: str
) -> tuple[Path, Path, str]:
    content = b"verified-original-content"
    entry = workspace_builder.add_asset(1, original=False)
    digest = hashlib.sha256(content).hexdigest()
    entry["asset_id"] = f"sha256:{digest}"
    entry["sha256"] = digest
    entry["size_bytes"] = len(content)
    original = workspace_builder.originals.joinpath(*entry["sources"][0]["relative_path"].split("/"))
    original.parent.mkdir(parents=True, exist_ok=True)
    original.write_bytes(content)
    root = workspace_builder.publish()
    catalog_path = root / "metadata/catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["source_root"] = source_root
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    return root, original, digest


def test_fresh_profile_serves_setup_settings_and_nonready_health(tmp_path: Path) -> None:
    client = _client(create_app(settings=_profile_settings(tmp_path / "profile/config.toml")))

    setup = client.get("/")
    settings = client.get("/settings")
    library = client.get("/library")
    health = client.get("/health")

    assert setup.status_code == 200
    assert "Připojit existující workspace" in setup.text
    assert settings.status_code == 200
    assert "Ověřit cestu" in settings.text
    assert library.status_code == 503
    assert 'href="/settings"' in library.text
    assert health.status_code == 503
    assert health.json()["status"] == "running"
    assert health.json()["ready"] is False


def test_validate_save_and_restart_use_profile_without_workspace_writes(
    workspace_builder, tmp_path: Path
) -> None:
    workspace_builder.add_asset(1, original=False)
    root = workspace_builder.publish()
    before = _state(root)
    profile = tmp_path / "profile/config.toml"
    client = _client(create_app(settings=_profile_settings(profile)))
    token = _csrf(client)

    checked = _post(client, "/settings/validate", token, str(root))
    assert checked.status_code == 200
    assert "Připojeno" in checked.text
    assert "Uložit změny" in checked.text
    assert not profile.exists()

    saved = _post(client, "/settings/save", token, str(root))
    assert saved.status_code == 200
    assert "Pro její aktivaci restartujte Media Desk" in saved.text
    assert profile.exists()
    assert _state(root) == before

    restarted_settings = load_settings(
        workspace=None,
        host=None,
        port=None,
        keyframe_fingerprint=None,
        config_path=None,
        config_dir=profile.parent,
        environ={},
    )
    restarted = _client(create_app(settings=restarted_settings))
    assert restarted.get("/library").status_code == 200
    assert restarted.get("/health").json() == {"status": "ok", "workspace_id": "workspace-test"}


def test_invalid_path_does_not_replace_existing_profile(workspace_builder, tmp_path: Path) -> None:
    root = workspace_builder.publish()
    profile = tmp_path / "profile/config.toml"
    save_profile_workspace(profile, root)
    original = profile.read_bytes()
    client = _client(create_app(settings=_profile_settings(profile, root)))
    token = _csrf(client)

    response = _post(client, "/settings/save", token, str(tmp_path / "missing"))

    assert response.status_code == 200
    assert "Nedostupné" in response.text
    assert profile.read_bytes() == original


def test_higher_priority_workspace_is_read_only_in_settings(workspace_builder, tmp_path: Path) -> None:
    root = workspace_builder.publish()
    config = tmp_path / "profile/config.toml"
    settings = Settings(
        workspace=root,
        profile_config_path=config,
        workspace_source="cli",
    )
    client = _client(create_app(settings=settings))
    token = _csrf(client)

    page = client.get("/settings")
    attempted = _post(client, "/settings/save", token, str(root))

    assert "Aktivní cestu určuje CLI" in page.text
    assert "profil nelze upravit" in attempted.text
    assert not config.exists()


def test_settings_posts_reject_foreign_origin_host_lan_and_unexpected_fields(
    workspace_builder, tmp_path: Path
) -> None:
    root = workspace_builder.publish()
    config = tmp_path / "profile/config.toml"
    client = _client(create_app(settings=_profile_settings(config)))
    token = _csrf(client)

    foreign_origin = client.post(
        "/settings/save",
        data={"csrf_token": token, "workspace": str(root)},
        headers={"Origin": "http://evil.invalid"},
    )
    foreign_host = client.post(
        "/settings/save",
        data={"csrf_token": token, "workspace": str(root)},
        headers={"Origin": "http://evil.invalid", "Host": "evil.invalid"},
    )
    unexpected = _post(client, "/settings/save", token, str(root), target="anything")
    control_character = _post(client, "/settings/save", token, "bad\npath")
    too_long = _post(client, "/settings/save", token, "x" * 4097)
    lan_client = _client(create_app(settings=_profile_settings(config, host="0.0.0.0")))
    lan_token = _csrf(lan_client)
    lan = _post(lan_client, "/settings/save", lan_token, str(root))

    assert foreign_origin.status_code == 403
    assert foreign_host.status_code == 403
    assert unexpected.status_code == 400
    assert "řídicí znaky" in control_character.text
    assert "1 až 4096 znaků" in too_long.text
    assert lan.status_code == 403
    assert not config.exists()


@pytest.mark.parametrize("source_root", [r"D:\Archive\Huhac", "/srv/archive/huhac"])
def test_originals_mapping_validate_save_restart_and_clear(
    workspace_builder, tmp_path: Path, source_root: str
) -> None:
    root, _original, digest = _publish_mappable_workspace(
        workspace_builder, source_root=source_root
    )
    before = _state(root)
    profile = tmp_path / "profile/config.toml"
    save_profile_workspace(profile, root)
    client = _client(create_app(settings=_profile_settings(profile, root)))
    token = _csrf(client)

    checked = _mapping_post(
        client,
        "/settings/originals/validate",
        token,
        str(workspace_builder.originals),
    )
    assert checked.status_code == 200
    assert "valid_sampled" in checked.text
    assert "Vzorkov" in checked.text and "integrity archivu" in checked.text
    assert "[media_desk.originals_mapping]" not in profile.read_text(encoding="utf-8")

    saved = _mapping_post(
        client,
        "/settings/originals/save",
        token,
        str(workspace_builder.originals),
    )
    assert saved.status_code == 200
    assert "[media_desk.originals_mapping]" in profile.read_text(encoding="utf-8")
    assert _state(root) == before

    restarted_settings = load_settings(
        workspace=None,
        host=None,
        port=None,
        keyframe_fingerprint=None,
        config_path=None,
        config_dir=profile.parent,
        environ={},
    )
    restarted = _client(create_app(settings=restarted_settings))
    assert restarted.get(_original_url(restarted, digest)).content == b"verified-original-content"
    assert "valid_sampled" in restarted.get("/settings").text

    clear_token = _csrf(restarted)
    cleared = _mapping_post(restarted, "/settings/originals/clear", clear_token)
    assert cleared.status_code == 200
    assert "[media_desk.originals_mapping]" not in profile.read_text(encoding="utf-8")
    assert load_settings(
        workspace=None,
        host=None,
        port=None,
        keyframe_fingerprint=None,
        config_path=None,
        config_dir=profile.parent,
        environ={},
    ).originals_mapping is None


def test_failed_mapping_save_preserves_existing_profile(workspace_builder, tmp_path: Path) -> None:
    root, original, _digest = _publish_mappable_workspace(
        workspace_builder, source_root=r"D:\Archive\Huhac"
    )
    profile = tmp_path / "profile/config.toml"
    save_profile_workspace(profile, root)
    client = _client(create_app(settings=_profile_settings(profile, root)))
    token = _csrf(client)
    valid = _mapping_post(
        client, "/settings/originals/save", token, str(workspace_builder.originals)
    )
    assert valid.status_code == 200
    original_profile = profile.read_bytes()

    original.write_bytes(b"same-length-invalid-hash!!")
    catalog_path = root / "metadata/catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["assets"][0]["size_bytes"] = original.stat().st_size
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    rejected = _mapping_post(
        client, "/settings/originals/save", token, str(workspace_builder.originals)
    )

    assert rejected.status_code == 200
    assert "storage_mismatch" in rejected.text
    assert profile.read_bytes() == original_profile


def test_original_artifact_rechecks_symlink_confinement_on_every_access(
    workspace_builder, tmp_path: Path
) -> None:
    root, original, digest = _publish_mappable_workspace(
        workspace_builder, source_root="/srv/archive/huhac"
    )
    profile = tmp_path / "profile/config.toml"
    save_profile_workspace(profile, root)
    initial = _client(create_app(settings=_profile_settings(profile, root)))
    token = _csrf(initial)
    _mapping_post(initial, "/settings/originals/save", token, str(workspace_builder.originals))
    settings = load_settings(
        workspace=None,
        host=None,
        port=None,
        keyframe_fingerprint=None,
        config_path=None,
        config_dir=profile.parent,
        environ={},
    )
    client = _client(create_app(settings=settings))
    original_url = _original_url(client, digest)
    assert client.get(original_url).status_code == 200

    outside = tmp_path / "outside.jpg"
    outside.write_bytes(b"outside")
    original.unlink()
    try:
        original.symlink_to(outside)
    except OSError:
        pytest.skip("Symlink creation is unavailable on this Windows host")

    assert client.get(original_url).status_code == 404


def test_originals_mapping_posts_use_settings_security_boundary(
    workspace_builder, tmp_path: Path
) -> None:
    root, _original, _digest = _publish_mappable_workspace(
        workspace_builder, source_root="/srv/archive/huhac"
    )
    profile = tmp_path / "profile/config.toml"
    client = _client(create_app(settings=_profile_settings(profile, root)))
    token = _csrf(client)

    foreign = client.post(
        "/settings/originals/save",
        data={"csrf_token": token, "local_root": str(workspace_builder.originals)},
        headers={"Origin": "http://evil.invalid"},
    )
    unexpected = _mapping_post(
        client,
        "/settings/originals/save",
        token,
        str(workspace_builder.originals),
        target="anything",
    )
    lan = _client(create_app(settings=_profile_settings(profile, root, host="0.0.0.0")))
    lan_token = _csrf(lan)
    denied_lan = _mapping_post(
        lan,
        "/settings/originals/save",
        lan_token,
        str(workspace_builder.originals),
    )

    assert foreign.status_code == 403
    assert unexpected.status_code == 400
    assert denied_lan.status_code == 403
    assert not profile.exists()
