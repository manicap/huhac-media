from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import threading

import pytest

from huhac_launcher.config import (
    LauncherConfig,
    LauncherConfigurationError,
    LauncherProfile,
    LauncherSettings,
    LauncherStore,
    application_python,
    default_launcher_config_path,
    initialize_launcher_config,
    load_launcher_settings,
    open_launcher_store,
    parse_port,
    save_launcher_settings,
)
from huhac_launcher.controller import BackendController, LauncherApplication, LauncherState
from huhac_launcher.gui import LauncherWindow
from huhac_launcher.snapshots import scan_normalizer_snapshots, validate_profile_selection
from media_desk.contract import ContractError
from normalizer.service import analyze_workspace


FP_A = "a" * 64
FP_B = "b" * 64
FP_C = "c" * 64


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _workspace(tmp_path: Path, name: str = "workspace", workspace_id: str = "workspace-one") -> Path:
    root = tmp_path / name
    originals = tmp_path / f"{name}-originals"
    originals.mkdir()
    _write_json(root / "workspace.json", {
        "schema_version": 1, "workspace_contract_version": 1,
        "workspace_id": workspace_id, "asset_catalog": "metadata/catalog.json",
    })
    _write_json(root / "metadata" / "catalog.json", {
        "workspace_contract_version": 1, "workspace_id": workspace_id,
        "generated_at": "2026-10-27T12:00:00Z", "generated_by_run_id": "test",
        "source_root": str(originals.resolve()), "assets": [],
    })
    return root


def _profile(tmp_path: Path, *, identifier: str = "one", workspace: Path | None = None,
             port: int = 8878, normalizer: tuple[str, str] | None = None) -> LauncherProfile:
    profile_root = tmp_path / f"profile-{identifier}"
    profile_root.mkdir(exist_ok=True)
    return LauncherProfile(
        identifier, identifier.title(), workspace or _workspace(tmp_path), profile_root, port,
        normalizer_configuration_fingerprint=normalizer[0] if normalizer else None,
        normalizer_input_set_fingerprint=normalizer[1] if normalizer else None,
    )


def _settings(*profiles: LauncherProfile, active: str | None = None) -> LauncherSettings:
    return LauncherSettings(tuple(profiles), active or profiles[0].id)


def _v1(path: Path, workspace: Path, profile: Path) -> None:
    path.write_text(f'''[launcher]
workspace = {json.dumps(str(workspace))}
profile = {json.dumps(str(profile))}
host = "127.0.0.1"
port = 8878
keyframe_fingerprint = "{FP_A}"
normalizer_configuration_fingerprint = "{FP_B}"
normalizer_input_set_fingerprint = "{FP_C}"
startup_timeout_seconds = 30
shutdown_timeout_seconds = 8
log_max_characters = 65536
''', encoding="utf-8")


def test_v01_is_migrated_once_without_touching_user_data(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    profile_root = tmp_path / "existing-profile"
    user_data = profile_root / "HUHAC" / "MediaDesk" / "library-data" / "workspace-one.json"
    _write_json(user_data, {"revision": 7})
    before = user_data.read_bytes(), user_data.stat().st_mtime_ns
    config = tmp_path / "launcher.toml"
    _v1(config, workspace, profile_root)

    store = LauncherStore.open(config)

    assert store.settings.active_profile.name == "Testovací"
    assert store.settings.active_profile.normalizer_selection == (FP_B, FP_C)
    assert store.settings.active_profile.keyframe_fingerprint == FP_A
    assert "schema_version = 2" in config.read_text(encoding="utf-8")
    assert (user_data.read_bytes(), user_data.stat().st_mtime_ns) == before
    assert not load_launcher_settings(config).migrated_from_v1


def test_default_config_path_is_host_local() -> None:
    assert default_launcher_config_path(
        {"LOCALAPPDATA": r"C:\Users\Tester\AppData\Local"}, platform="nt"
    ) == Path(r"C:\Users\Tester\AppData\Local\HUHAC\Launcher\launcher.toml")
    assert default_launcher_config_path(
        {"XDG_CONFIG_HOME": "/tmp/config"}, platform="posix"
    ) == Path("/tmp/config/huhac/launcher/launcher.toml")


def test_clean_checkout_seeds_local_config_once_without_overwrite(tmp_path: Path) -> None:
    project_root = tmp_path / "checkout"
    example = project_root / "config" / "launcher.example.toml"
    profile = _profile(tmp_path, identifier="example")
    save_launcher_settings(example, _settings(profile))
    local_root = tmp_path / "local"
    environ = {"LOCALAPPDATA": str(local_root)}

    store = open_launcher_store(project_root, environ=environ, platform="nt")
    local_config = local_root / "HUHAC" / "Launcher" / "launcher.toml"
    assert store.path == local_config
    assert store.settings.profiles == (profile,)

    original = local_config.read_bytes()
    changed_example = replace(profile, name="Changed distribution example")
    save_launcher_settings(example, _settings(changed_example))
    assert not initialize_launcher_config(local_config, example)
    assert local_config.read_bytes() == original


def test_explicit_config_does_not_require_distribution_example(tmp_path: Path) -> None:
    explicit = tmp_path / "custom.toml"
    profile = _profile(tmp_path, identifier="custom")
    save_launcher_settings(explicit, _settings(profile))

    store = open_launcher_store(
        tmp_path / "checkout",
        explicit_config=explicit,
        example_config=tmp_path / "missing.toml",
    )

    assert store.path == explicit.resolve()
    assert store.settings.active_profile.id == "custom"


def test_invalid_distribution_example_does_not_create_local_config(tmp_path: Path) -> None:
    example = tmp_path / "invalid.toml"
    example.write_text("schema_version = [", encoding="utf-8")
    target = tmp_path / "local" / "launcher.toml"

    with pytest.raises(LauncherConfigurationError):
        initialize_launcher_config(target, example)

    assert not target.exists()


def test_profile_add_update_switch_remove_and_reload(tmp_path: Path) -> None:
    first = _profile(tmp_path, identifier="first")
    config = tmp_path / "launcher.toml"
    save_launcher_settings(config, _settings(first))
    store = LauncherStore.open(config)
    second = _profile(tmp_path, identifier="second", workspace=_workspace(tmp_path, "two", "workspace-two"), port=9001)

    store.add(second)
    assert store.settings.active_profile_id == "second"
    store.update(replace(second, name="Druhá knihovna", port=9002))
    store.activate("first")
    store.remove("second")

    loaded = LauncherStore.open(config).settings
    assert [item.id for item in loaded.profiles] == ["first"]
    assert loaded.active_profile_id == "first"
    assert first.workspace.is_dir() and second.workspace.is_dir()
    assert first.profile.is_dir() and second.profile.is_dir()


def test_profiles_keep_separate_user_data_roots_and_runtime_values(tmp_path: Path) -> None:
    one = _profile(tmp_path, identifier="one", port=8101)
    two = _profile(tmp_path, identifier="two", workspace=_workspace(tmp_path, "two", "workspace-two"), port=8102)
    settings = _settings(one, two)
    assert settings.runtime(one).profile != settings.runtime(two).profile
    assert settings.runtime(one).workspace != settings.runtime(two).workspace
    assert settings.runtime(one).port == 8101
    assert settings.runtime(two).port == 8102


def test_optional_application_pythons_round_trip_without_changing_profiles(
    tmp_path: Path,
) -> None:
    profile = _profile(tmp_path)
    media_python = (tmp_path / "media-env" / "Scripts" / "python.exe").resolve()
    studio_python = (tmp_path / "studio-env" / "Scripts" / "python.exe").resolve()
    settings = replace(
        _settings(profile),
        media_desk_python=media_python,
        studio_python=studio_python,
    )
    path = tmp_path / "launcher.toml"

    save_launcher_settings(path, settings)
    loaded = load_launcher_settings(path)

    assert loaded.profiles == (profile,)
    assert loaded.media_desk_python == media_python
    assert loaded.studio_python == studio_python


def test_old_schema_two_config_defaults_application_pythons_to_detection(
    tmp_path: Path,
) -> None:
    profile = _profile(tmp_path)
    path = tmp_path / "launcher.toml"
    save_launcher_settings(path, _settings(profile))

    loaded = load_launcher_settings(path)

    assert loaded.media_desk_python is None
    assert loaded.studio_python is None


def test_media_desk_python_is_detected_from_linked_main_worktree(tmp_path: Path) -> None:
    main = tmp_path / "huhac-media"
    studio = tmp_path / "huhac-studio-dev"
    git_directory = main / ".git" / "worktrees" / "huhac-studio-dev"
    git_directory.mkdir(parents=True)
    studio.mkdir()
    (studio / ".git").write_text(f"gitdir: {git_directory}\n", encoding="utf-8")
    (main / "pyproject.toml").write_text("[project]\nname='huhac'\n", encoding="utf-8")
    (main / "src" / "media_desk").mkdir(parents=True)
    media_python = main / ".venv" / "Scripts" / "python.exe"
    media_python.parent.mkdir(parents=True)
    media_python.write_bytes(b"python")
    studio_python = studio / ".venv" / "Scripts" / "python.exe"
    studio_python.parent.mkdir(parents=True)
    studio_python.write_bytes(b"python")

    assert application_python(studio, "media-desk") == media_python
    assert application_python(studio, "studio") == studio_python


def test_configured_application_python_overrides_safe_detection(tmp_path: Path) -> None:
    configured = (tmp_path / "custom" / "Scripts" / "python.exe").resolve()

    assert application_python(tmp_path, "media-desk", configured) == configured


def test_corrupt_toml_is_rejected_without_rewrite(tmp_path: Path) -> None:
    path = tmp_path / "launcher.toml"
    path.write_text("schema_version = [", encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(LauncherConfigurationError, match="nelze načíst"):
        LauncherStore.open(path)
    assert path.read_bytes() == before


@pytest.mark.parametrize("value, expected", [("1023", False), ("1024", True), ("65535", True), ("65536", False), ("abc", False), ("", False)])
def test_port_boundaries(value: str, expected: bool) -> None:
    if expected:
        assert parse_port(value) == int(value)
    else:
        with pytest.raises(LauncherConfigurationError):
            parse_port(value)


def test_runtime_url_tracks_profile_port(tmp_path: Path) -> None:
    runtime = _settings(_profile(tmp_path, port=49152)).runtime()
    assert runtime.address == "http://127.0.0.1:49152"
    assert runtime.health_url == "http://127.0.0.1:49152/health"


def test_valid_normalizer_snapshot_is_listed_and_selectable(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    result = analyze_workspace(workspace)
    workspace_id, choices = scan_normalizer_snapshots(workspace)
    assert workspace_id == "workspace-one"
    assert len(choices) == 1 and choices[0].valid
    profile = _profile(tmp_path, workspace=workspace, normalizer=choices[0].key)
    assert validate_profile_selection(profile) == workspace_id


def test_missing_invalid_stale_and_foreign_snapshots_are_not_valid(tmp_path: Path) -> None:
    first = _workspace(tmp_path, "first", "workspace-one")
    result = analyze_workspace(first)
    key = (result.prepared.configuration_fingerprint, result.prepared.input_set_fingerprint)
    missing = _profile(tmp_path, identifier="missing", workspace=first, normalizer=(FP_A, FP_B))
    with pytest.raises(ContractError, match="nelze aktivovat"):
        validate_profile_selection(missing)

    # Reuse the public snapshot under another valid workspace: identity must fail.
    second = _workspace(tmp_path, "second", "workspace-two")
    target = second / "analysis" / "normalizer" / "normalizer-v1" / key[0] / key[1]
    import shutil
    shutil.copytree(result.prepared.output_path, target)
    _workspace_id, foreign = scan_normalizer_snapshots(second)
    assert foreign[0].state == "stale"

    # Changing the active catalog after publication makes the original stale too.
    catalog = json.loads((first / "metadata" / "catalog.json").read_text(encoding="utf-8"))
    catalog["assets"] = [{"invalid": True}]
    _write_json(first / "metadata" / "catalog.json", catalog)
    with pytest.raises(ContractError):
        validate_profile_selection(_profile(tmp_path, identifier="stale", workspace=first, normalizer=key))


def test_invalid_snapshot_and_partial_ambiguous_selection_are_rejected(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    result = analyze_workspace(workspace)
    manifest_path = result.prepared.output_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["status"] = "failed"
    _write_json(manifest_path, manifest)
    _workspace_id, choices = scan_normalizer_snapshots(workspace)
    assert len(choices) == 1 and choices[0].state == "invalid" and not choices[0].valid

    profile = _profile(tmp_path, identifier="partial", workspace=workspace)
    settings = _settings(replace(profile, normalizer_configuration_fingerprint=FP_A))
    path = tmp_path / "partial.toml"
    # The writer refuses a configuration-only selection, which would otherwise
    # leave the input snapshot ambiguous.
    with pytest.raises(LauncherConfigurationError, match="oba fingerprinty"):
        save_launcher_settings(path, settings)


def test_no_normalizer_removes_inherited_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = _workspace(tmp_path)
    profile = _profile(tmp_path, workspace=workspace)
    runtime = _settings(profile).runtime()
    root = tmp_path / "repo"
    python = root / ".venv" / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.write_bytes(b"python")
    (root / ".venv" / "pyvenv.cfg").write_text(f"executable = {python}\n", encoding="utf-8")
    monkeypatch.setenv("MEDIA_DESK_NORMALIZER_CONFIGURATION_FINGERPRINT", FP_A)
    monkeypatch.setenv("MEDIA_DESK_NORMALIZER_INPUT_SET_FINGERPRINT", FP_B)
    controller = BackendController(runtime, root, runtime_validator=lambda _config: None)
    environment = controller._environment()
    assert "MEDIA_DESK_NORMALIZER_CONFIGURATION_FINGERPRINT" not in environment
    assert "MEDIA_DESK_NORMALIZER_INPUT_SET_FINGERPRINT" not in environment
    assert environment["APPDATA"] == str(profile.profile)
    assert environment["LOCALAPPDATA"] == str(profile.profile)


def test_profile_fingerprints_change_together(tmp_path: Path) -> None:
    first = replace(_profile(tmp_path, identifier="one"), keyframe_fingerprint=FP_A,
                    normalizer_configuration_fingerprint=FP_B,
                    normalizer_input_set_fingerprint=FP_C)
    second = _profile(tmp_path, identifier="two", workspace=_workspace(tmp_path, "two", "workspace-two"))
    settings = _settings(first, second)
    assert settings.runtime(first).normalizer_configuration_fingerprint == FP_B
    assert settings.runtime(second).normalizer_configuration_fingerprint is None
    assert settings.runtime(second).keyframe_fingerprint is None


def test_incompatible_keyframe_fingerprint_is_rejected(tmp_path: Path) -> None:
    profile = replace(_profile(tmp_path), keyframe_fingerprint=FP_A)
    with pytest.raises(ContractError, match="Keyframes fingerprint"):
        validate_profile_selection(profile)


def test_running_window_locks_profile_snapshot_and_port() -> None:
    window = LauncherWindow.__new__(LauncherWindow)
    window._worker = None
    class Controller:
        owns_process = True
        state = LauncherState.RUNNING
    window.controller = Controller()
    assert window._locked()


def test_window_reconfigures_controller_for_selected_application(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    window = LauncherWindow.__new__(LauncherWindow)

    class Variable:
        value = LauncherApplication.STUDIO.title

        @classmethod
        def get(cls) -> str:
            return cls.value

    class Controller:
        owns_process = False

    class Store:
        settings = _settings(profile)

    window.application_var = Variable()
    window.controller = Controller()
    window.store = Store()
    window.project_root = tmp_path

    window._set_controller(profile)

    assert window.controller.application is LauncherApplication.STUDIO
    assert window.controller._command()[1:3] == ["-m", "huhac_studio.cli"]

    Variable.value = LauncherApplication.MEDIA_DESK.title
    window._set_controller(profile)

    assert window.controller.application is LauncherApplication.MEDIA_DESK
    assert window.controller._command()[1:3] == ["-m", "media_desk"]


def test_snapshot_scan_starts_in_background(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    window = LauncherWindow.__new__(LauncherWindow)
    class Combo:
        def configure(self, **_kwargs): pass
    class Variable:
        def set(self, _value): pass
    class Root:
        def after(self, _delay, _callback): pass
    window.snapshot_combo = Combo()
    window.snapshot_var = Variable()
    window.root = Root()
    release = threading.Event()
    entered = threading.Event()
    def blocked_scan(_path):
        entered.set()
        release.wait(2)
        return "workspace-one", ()
    monkeypatch.setattr("huhac_launcher.gui.scan_normalizer_snapshots", blocked_scan)
    window._scan_snapshots(profile)
    assert entered.wait(1)
    assert window._snapshot_worker.is_alive()
    release.set()
    window._snapshot_worker.join(1)


def test_open_ui_uses_only_owned_running_loopback_url() -> None:
    opened: list[str] = []
    window = LauncherWindow.__new__(LauncherWindow)
    class Controller:
        state = LauncherState.RUNNING
        owns_process = True
        browser_url = "http://127.0.0.1:9123/?launcher_app=media-desk&launcher_run=one"
    window.controller = Controller()
    window.browser_opener = opened.append
    window._open_ui()
    assert opened == [
        "http://127.0.0.1:9123/?launcher_app=media-desk&launcher_run=one"
    ]
