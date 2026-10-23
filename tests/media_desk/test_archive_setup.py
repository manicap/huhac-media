from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
from uuid import uuid4

from fastapi.testclient import TestClient

from media_desk.archive_setup import ArchiveSetupClient
from media_desk.config import ConfigurationError, Settings, load_settings, save_profile_workspace
from media_desk.web import create_app


def _payload(operation_id: str) -> dict:
    return {
        "schema_version": 1,
        "operation_id": operation_id,
        "state": "preflight_ok",
        "workspace_id": None,
        "storage_path": "C:\\Media",
        "workspace_path": "C:\\Workspace",
        "created": {
            "storage_directory": False,
            "workspace_directory": False,
            "workspace_manifest": False,
            "empty_catalog": False,
            "sqlite": False,
        },
        "warnings": [],
        "error": None,
        "restart_required": False,
    }


def test_subprocess_boundary_uses_fixed_argument_list_without_shell() -> None:
    operation_id = str(uuid4())
    calls: list[tuple[list[str], dict]] = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, json.dumps(_payload(operation_id)), "")

    result = ArchiveSetupClient(executable="python-fixed", runner=runner).preflight(
        "C:\\Media path", "C:\\Workspace path"
    )
    command, options = calls[0]
    assert result.operation_id == operation_id
    assert command == [
        "python-fixed", "-m", "huhac_media", "init", "--storage", "C:\\Media path",
        "--workspace", "C:\\Workspace path", "--preflight", "--json",
    ]
    assert options["shell"] is False


def _csrf(client: TestClient) -> str:
    page = client.get("/settings")
    match = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
    assert match
    return match.group(1)


def _hidden(page: str, name: str) -> str:
    match = re.search(rf'name="{name}" value="([^"]+)"', page)
    assert match
    return match.group(1)


def test_real_cli_web_flow_postvalidates_then_saves_profile(tmp_path: Path) -> None:
    profile = tmp_path / "profile" / "config.toml"
    settings = Settings(
        workspace=None,
        host="127.0.0.1",
        profile_config_path=profile,
        workspace_source="default",
    )
    client = TestClient(create_app(settings=settings), base_url="http://127.0.0.1")
    token = _csrf(client)
    storage = tmp_path / "media"
    workspace = tmp_path / "workspace"
    headers = {"Origin": "http://127.0.0.1"}
    preflight = client.post(
        "/settings/archive/preflight",
        data={"csrf_token": token, "storage": str(storage), "workspace": str(workspace)},
        headers=headers,
    )
    assert preflight.status_code == 200
    assert "preflight_ok" in preflight.text
    assert not storage.exists() and not workspace.exists() and not profile.exists()
    operation_id = _hidden(preflight.text, "operation_id")
    nonce = _hidden(preflight.text, "confirmation_nonce")
    initialized = client.post(
        "/settings/archive/initialize",
        data={
            "csrf_token": token,
            "storage": str(storage.resolve()),
            "workspace": str(workspace.resolve()),
            "operation_id": operation_id,
            "confirmation_nonce": nonce,
        },
        headers=headers,
    )
    assert initialized.status_code == 200
    assert "restartujte Media Desk" in initialized.text
    assert (workspace / "workspace.json").is_file()
    assert json.loads((workspace / "metadata" / "catalog.json").read_text(encoding="utf-8"))["assets"] == []
    loaded = load_settings(
        workspace=None, host=None, port=None, keyframe_fingerprint=None,
        config_path=None, config_dir=profile.parent, environ={},
    )
    assert loaded.workspace == workspace.resolve()
    restarted = TestClient(create_app(settings=loaded), base_url="http://127.0.0.1")
    assert restarted.get("/health").json()["workspace_id"]
    assert restarted.get("/api/assets").json()["total"] == 0
    for endpoint in ("/", "/library", "/calendar", "/relations"):
        assert restarted.get(endpoint).status_code == 200

    reused = client.post(
        "/settings/archive/initialize",
        data={
            "csrf_token": token, "storage": str(storage.resolve()),
            "workspace": str(workspace.resolve()), "operation_id": operation_id,
            "confirmation_nonce": nonce,
        },
        headers=headers,
    )
    assert "Potvrzení vypršelo" in reused.text


def test_archive_setup_uses_existing_settings_security_boundary(tmp_path: Path) -> None:
    profile = tmp_path / "config.toml"
    settings = Settings(
        workspace=None,
        host="127.0.0.1",
        profile_config_path=profile,
        workspace_source="default",
    )
    client = TestClient(create_app(settings=settings), base_url="http://127.0.0.1")
    token = _csrf(client)
    response = client.post(
        "/settings/archive/preflight",
        data={"csrf_token": token, "storage": str(tmp_path / "media"), "workspace": str(tmp_path / "workspace")},
        headers={"Origin": "http://evil.invalid"},
    )
    assert response.status_code == 403
    assert not profile.exists()


def test_config_save_failure_preserves_profile_and_ready_archive(
    tmp_path: Path, monkeypatch
) -> None:
    profile = tmp_path / "profile" / "config.toml"
    save_profile_workspace(profile, tmp_path / "old-workspace")
    original_profile = profile.read_bytes()
    settings = Settings(
        workspace=None, host="127.0.0.1", profile_config_path=profile, workspace_source="default"
    )
    client = TestClient(create_app(settings=settings), base_url="http://127.0.0.1")
    token = _csrf(client)
    storage = tmp_path / "media"
    workspace = tmp_path / "workspace"
    headers = {"Origin": "http://127.0.0.1"}
    preflight = client.post(
        "/settings/archive/preflight",
        data={"csrf_token": token, "storage": str(storage), "workspace": str(workspace)},
        headers=headers,
    )
    operation_id = _hidden(preflight.text, "operation_id")
    nonce = _hidden(preflight.text, "confirmation_nonce")
    monkeypatch.setattr(
        "media_desk.web.save_profile_workspace",
        lambda *_: (_ for _ in ()).throw(ConfigurationError("read only profile")),
    )
    response = client.post(
        "/settings/archive/initialize",
        data={
            "csrf_token": token, "storage": str(storage.resolve()),
            "workspace": str(workspace.resolve()), "operation_id": operation_id,
            "confirmation_nonce": nonce,
        },
        headers=headers,
    )
    assert "Archiv je připraven" in response.text
    assert (workspace / "workspace.json").is_file()
    assert profile.read_bytes() == original_profile
