from __future__ import annotations

import hashlib
from pathlib import Path
import re

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
