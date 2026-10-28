from __future__ import annotations

from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time

import pytest

from huhac_launcher.config import (
    LauncherConfig,
    LauncherConfigurationError,
    load_launcher_config,
)
from huhac_launcher.controller import (
    BackendController,
    LauncherApplication,
    LauncherState,
    http_readiness,
    studio_http_readiness,
)
from huhac_launcher.gui import LauncherWindow


FINGERPRINT = "a" * 64


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def monotonic(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += seconds


class FakeProcess:
    def __init__(
        self,
        *,
        returncode: int | None = None,
        stdout: bytes = b"",
        stderr: bytes = b"",
        ignore_terminate: bool = False,
    ) -> None:
        self.returncode = returncode
        self.stdout = BytesIO(stdout)
        self.stderr = BytesIO(stderr)
        self.ignore_terminate = ignore_terminate
        self.terminate_calls = 0
        self.kill_calls = 0
        self._finished = threading.Event()
        if returncode is not None:
            self._finished.set()

    def poll(self) -> int | None:
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        if timeout is None:
            self._finished.wait()
        elif not self._finished.wait(0):
            raise subprocess.TimeoutExpired("fake", timeout)
        assert self.returncode is not None
        return self.returncode

    def terminate(self) -> None:
        self.terminate_calls += 1
        if not self.ignore_terminate:
            self.exit(0)

    def kill(self) -> None:
        self.kill_calls += 1
        self.exit(-9)

    def exit(self, code: int) -> None:
        self.returncode = code
        self._finished.set()


class ProcessFactory:
    def __init__(self, process: FakeProcess) -> None:
        self.process = process
        self.calls: list[tuple[list[str], dict[str, object]]] = []

    def __call__(self, command: list[str], **kwargs: object) -> FakeProcess:
        self.calls.append((command, kwargs))
        return self.process


def _runtime(tmp_path: Path) -> tuple[Path, LauncherConfig]:
    root = tmp_path / "repo"
    python = root / ".venv" / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.write_bytes(b"python")
    base_python = tmp_path / "base-python.exe"
    base_python.write_bytes(b"python")
    (root / ".venv" / "pyvenv.cfg").write_text(
        f"executable = {base_python}\n", encoding="utf-8"
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "workspace.json").write_text("{}", encoding="utf-8")
    profile = tmp_path / "profile"
    profile.mkdir()
    config = LauncherConfig(
        workspace=workspace,
        profile=profile,
        host="127.0.0.1",
        port=8878,
        keyframe_fingerprint=FINGERPRINT,
        normalizer_configuration_fingerprint="b" * 64,
        normalizer_input_set_fingerprint="c" * 64,
        startup_timeout_seconds=1.0,
        shutdown_timeout_seconds=1.0,
        log_max_characters=4096,
    )
    return root, config


def _controller(
    tmp_path: Path,
    process: FakeProcess | None = None,
    *,
    ready=True,
    port_free=True,
) -> tuple[BackendController, ProcessFactory, FakeProcess, FakeClock]:
    root, config = _runtime(tmp_path)
    child = process or FakeProcess()
    factory = ProcessFactory(child)
    clock = FakeClock()
    readiness = (lambda _url: (True, "")) if ready else (lambda _url: (False, "čeká"))
    controller = BackendController(
        config,
        root,
        process_factory=factory,
        readiness_probe=readiness,
        port_checker=lambda _host, _port: port_free,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
        runtime_validator=lambda _config: "workspace-test",
    )
    return controller, factory, child, clock


def _studio_controller(
    tmp_path: Path,
    process: FakeProcess | None = None,
    *,
    ready: bool = True,
    port_free: bool = True,
) -> tuple[BackendController, ProcessFactory, FakeProcess, FakeClock, list[str]]:
    root, config = _runtime(tmp_path)
    frontend = root / "studio" / "dist"
    frontend.mkdir(parents=True)
    (frontend / "index.html").write_text("<html></html>", encoding="utf-8")
    child = process or FakeProcess()
    factory = ProcessFactory(child)
    clock = FakeClock()
    readiness_urls: list[str] = []

    def readiness(url: str) -> tuple[bool, str]:
        readiness_urls.append(url)
        return (True, "") if ready else (False, "čeká")

    controller = BackendController(
        config,
        root,
        application=LauncherApplication.STUDIO,
        process_factory=factory,
        readiness_probe=readiness,
        port_checker=lambda _host, _port: port_free,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
        runtime_validator=lambda _config: "workspace-test",
    )
    return controller, factory, child, clock, readiness_urls


def _wait_for(predicate, timeout: float = 1.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("condition was not reached")


def test_successful_start_uses_list_command_and_health(tmp_path: Path) -> None:
    controller, factory, _process, _clock = _controller(tmp_path)

    result = controller.start()

    assert result.ok
    assert controller.state is LauncherState.RUNNING
    command, kwargs = factory.calls[0]
    assert command[0] == str(tmp_path / "base-python.exe")
    assert command[1:] == ["-m", "media_desk", "--host", "127.0.0.1", "--port", "8878"]
    assert kwargs["shell"] is False


def test_browser_url_identifies_application_and_each_launch(tmp_path: Path) -> None:
    controller, _factory, _process, _clock = _controller(tmp_path)

    assert controller.start().ok
    first_url = controller.browser_url
    assert "launcher_app=media-desk" in first_url
    assert "launcher_run=" in first_url
    assert controller.stop().ok

    controller._process_factory = ProcessFactory(FakeProcess())
    assert controller.start().ok
    assert controller.browser_url != first_url
    controller.stop()


def test_studio_start_uses_profile_workspace_build_and_session_readiness(tmp_path: Path) -> None:
    controller, factory, _process, _clock, readiness_urls = _studio_controller(tmp_path)

    result = controller.start()

    assert result.ok
    command, kwargs = factory.calls[0]
    assert command == [
        str(tmp_path / "base-python.exe"),
        "-m",
        "huhac_studio.cli",
        "--workspace",
        str(controller.config.workspace),
        "--host",
        "127.0.0.1",
        "--port",
        "8878",
        "--frontend",
        str(controller.frontend_dir),
    ]
    assert readiness_urls == ["http://127.0.0.1:8878/api/studio/session"]
    assert kwargs["shell"] is False
    controller.stop()


def test_studio_missing_frontend_build_fails_before_spawn(tmp_path: Path) -> None:
    controller, factory, _process, _clock, _readiness_urls = _studio_controller(tmp_path)
    (controller.frontend_dir / "index.html").unlink()

    result = controller.start()

    assert not result.ok
    assert "Build Studia chybí" in result.message
    assert "npm run build" in result.message
    assert not factory.calls


def test_studio_foreign_port_is_never_adopted_or_stopped(tmp_path: Path) -> None:
    controller, factory, process, _clock, _readiness_urls = _studio_controller(
        tmp_path,
        port_free=False,
    )

    result = controller.start()

    assert not result.ok
    assert not factory.calls
    assert process.terminate_calls == process.kill_calls == 0
    assert controller.stop().ok
    assert process.terminate_calls == process.kill_calls == 0


def test_studio_environment_preserves_host_data_root_and_removes_media_overrides(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "host-roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "host-local"))
    monkeypatch.setenv("MEDIA_DESK_WORKSPACE", "foreign-workspace")
    monkeypatch.setenv("MEDIA_DESK_KEYFRAME_FINGERPRINT", FINGERPRINT)
    controller, factory, _process, _clock, _readiness_urls = _studio_controller(tmp_path)

    assert controller.start().ok

    environment = factory.calls[0][1]["env"]
    assert isinstance(environment, dict)
    assert environment["APPDATA"] == str(tmp_path / "host-roaming")
    assert environment["LOCALAPPDATA"] == str(tmp_path / "host-local")
    assert not any(key.startswith("MEDIA_DESK_") for key in environment)
    controller.stop()


def test_studio_profile_restart_uses_new_workspace(tmp_path: Path) -> None:
    first, first_factory, _process, _clock, _urls = _studio_controller(tmp_path / "first")
    assert first.start().ok
    assert first.stop().ok

    second, second_factory, _process, _clock, _urls = _studio_controller(tmp_path / "second")
    second_workspace = second.config.workspace
    assert second.start().ok
    assert second.stop().ok

    assert first_factory.calls[0][0][4] != second_factory.calls[0][0][4]
    assert second_factory.calls[0][0][4] == str(second_workspace)


def test_studio_readiness_requires_exact_online_workspace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Response:
        status = 200

        def __init__(self, workspace_id: str) -> None:
            self.workspace_id = workspace_id

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _maximum: int) -> bytes:
            return json.dumps({
                "runtime_id": "runtime-one",
                "mode": "online",
                "active_workspace_id": self.workspace_id,
            }).encode("utf-8")

    monkeypatch.setattr(
        "huhac_launcher.controller.urlopen",
        lambda _request, timeout: Response("workspace-one"),
    )
    assert studio_http_readiness("http://127.0.0.1/session", "workspace-one")[0]
    ready, message = studio_http_readiness(
        "http://127.0.0.1/session",
        "workspace-two",
    )
    assert not ready
    assert "jinému workspace" in message


def test_readiness_rejects_other_application_payload_on_http_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Response:
        status = 200

        def __init__(self, payload: dict[str, object]) -> None:
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _maximum: int) -> bytes:
            return json.dumps(self.payload).encode("utf-8")

    studio_payload = {
        "runtime_id": "runtime-one",
        "mode": "online",
        "active_workspace_id": "workspace-one",
    }
    media_payload = {"status": "ok", "workspace_id": "workspace-one"}

    monkeypatch.setattr(
        "huhac_launcher.controller.urlopen",
        lambda _request, timeout: Response(studio_payload),
    )
    assert not http_readiness("http://127.0.0.1/health")[0]

    monkeypatch.setattr(
        "huhac_launcher.controller.urlopen",
        lambda _request, timeout: Response(media_payload),
    )
    assert not studio_http_readiness(
        "http://127.0.0.1/api/studio/session",
        "workspace-one",
    )[0]


def test_successful_stop_terminates_only_owned_process(tmp_path: Path) -> None:
    controller, _factory, process, _clock = _controller(tmp_path)
    assert controller.start().ok

    result = controller.stop()

    assert result.ok
    assert process.terminate_calls == 1
    assert process.kill_calls == 0
    assert controller.state is LauncherState.OFF


def test_repeated_start_does_not_create_duplicate(tmp_path: Path) -> None:
    controller, factory, _process, _clock = _controller(tmp_path)
    assert controller.start().ok

    result = controller.start()

    assert result.ok
    assert len(factory.calls) == 1
    controller.stop()


def test_stop_while_off_is_noop(tmp_path: Path) -> None:
    controller, factory, process, _clock = _controller(tmp_path)

    assert controller.stop().ok
    assert process.terminate_calls == 0
    assert not factory.calls


def test_foreign_process_on_port_is_never_started_or_killed(tmp_path: Path) -> None:
    controller, factory, process, _clock = _controller(tmp_path, port_free=False)

    result = controller.start()

    assert not result.ok
    assert "jiný proces" in result.message
    assert not factory.calls
    assert process.terminate_calls == process.kill_calls == 0
    assert controller.stop().ok
    assert process.terminate_calls == process.kill_calls == 0


def test_missing_workspace_fails_before_spawn(tmp_path: Path) -> None:
    controller, factory, _process, _clock = _controller(tmp_path)
    for child in controller.config.workspace.iterdir():
        child.unlink()
    controller.config.workspace.rmdir()

    result = controller.start()

    assert not result.ok
    assert "Workspace neexistuje" in result.message
    assert not factory.calls


def test_missing_interpreter_fails_before_spawn(tmp_path: Path) -> None:
    controller, factory, _process, _clock = _controller(tmp_path)
    controller.python.unlink()

    result = controller.start()

    assert not result.ok
    assert "Python neexistuje" in result.message
    assert not factory.calls


def test_invalid_fingerprint_is_rejected_by_config_loader(tmp_path: Path) -> None:
    path = tmp_path / "launcher.toml"
    path.write_text(
        """[launcher]
workspace = 'C:\\workspace'
profile = 'C:\\profile'
host = "127.0.0.1"
port = 8878
keyframe_fingerprint = "INVALID"
normalizer_configuration_fingerprint = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
normalizer_input_set_fingerprint = "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
startup_timeout_seconds = 30
shutdown_timeout_seconds = 8
log_max_characters = 65536
""",
        encoding="utf-8",
    )

    with pytest.raises(LauncherConfigurationError, match="64 malých"):
        load_launcher_config(path)


def test_backend_immediate_failure_is_reported(tmp_path: Path) -> None:
    controller, _factory, _process, _clock = _controller(
        tmp_path, FakeProcess(returncode=7, stderr=b"startup failed\n")
    )

    result = controller.start()

    assert not result.ok
    assert "kód 7" in result.message
    assert controller.state is LauncherState.ERROR


def test_readiness_timeout_stops_owned_failed_start(tmp_path: Path) -> None:
    controller, _factory, process, _clock = _controller(tmp_path, ready=False)

    result = controller.start()

    assert not result.ok
    assert "časovém limitu" in result.message
    assert process.terminate_calls == 1
    assert controller.state is LauncherState.ERROR
    assert not controller.owns_process


def test_spontaneous_backend_exit_updates_state(tmp_path: Path) -> None:
    controller, _factory, process, _clock = _controller(tmp_path)
    assert controller.start().ok

    process.exit(9)

    _wait_for(lambda: controller.state is LauncherState.ERROR)
    assert "neočekávaně skončil" in controller.error
    assert not controller.owns_process


def test_restarted_launcher_does_not_adopt_existing_service(tmp_path: Path) -> None:
    controller, factory, foreign, _clock = _controller(tmp_path, port_free=False)

    assert not controller.start().ok
    assert controller.stop().ok
    assert not factory.calls
    assert foreign.terminate_calls == foreign.kill_calls == 0


def test_close_stops_backend_and_can_force_only_owned_process(tmp_path: Path) -> None:
    stubborn = FakeProcess(ignore_terminate=True)
    controller, _factory, _process, _clock = _controller(tmp_path, stubborn)
    assert controller.start().ok

    result = controller.close(lambda _message: True)

    assert result.ok
    assert stubborn.terminate_calls == 1
    assert stubborn.kill_calls == 1
    assert controller.state is LauncherState.OFF


def test_child_environment_is_isolated_and_complete(tmp_path: Path) -> None:
    controller, factory, _process, _clock = _controller(tmp_path)
    before = dict(os.environ)

    assert controller.start().ok

    environment = factory.calls[0][1]["env"]
    assert isinstance(environment, dict)
    assert environment["APPDATA"] == str(controller.config.profile)
    assert environment["MEDIA_DESK_WORKSPACE"] == str(controller.config.workspace)
    assert environment["MEDIA_DESK_KEYFRAME_FINGERPRINT"] == FINGERPRINT
    assert environment["MEDIA_DESK_NORMALIZER_CONFIGURATION_FINGERPRINT"] == "b" * 64
    assert environment["MEDIA_DESK_NORMALIZER_INPUT_SET_FINGERPRINT"] == "c" * 64
    assert dict(os.environ) == before
    controller.stop()


def test_media_desk_can_use_a_separate_virtual_environment(tmp_path: Path) -> None:
    root, config = _runtime(tmp_path)
    media_environment = tmp_path / "media-environment"
    media_python = media_environment / "Scripts" / "python.exe"
    media_python.parent.mkdir(parents=True)
    media_python.write_bytes(b"python")
    media_base = tmp_path / "media-base-python.exe"
    media_base.write_bytes(b"python")
    (media_environment / "pyvenv.cfg").write_text(
        f"executable = {media_base}\n",
        encoding="utf-8",
    )
    process = FakeProcess()
    factory = ProcessFactory(process)
    controller = BackendController(
        config,
        root,
        application_python_path=media_python,
        process_factory=factory,
        readiness_probe=lambda _url: (True, ""),
        port_checker=lambda _host, _port: True,
        runtime_validator=lambda _config: "workspace-test",
    )

    assert controller.start().ok

    command, kwargs = factory.calls[0]
    environment = kwargs["env"]
    assert command[0] == str(media_base)
    assert isinstance(environment, dict)
    assert environment["VIRTUAL_ENV"] == str(media_environment)
    assert str(media_environment / "Lib" / "site-packages") in environment["PYTHONPATH"]
    assert str(root / ".venv" / "Lib" / "site-packages") not in environment["PYTHONPATH"]
    controller.stop()


def test_large_logs_are_drained_bounded_and_redacted(tmp_path: Path) -> None:
    output = b"x" * 200_000 + b"\npassword=do-not-keep\n"
    controller, _factory, _process, _clock = _controller(
        tmp_path, FakeProcess(stdout=output, stderr=output)
    )
    assert controller.start().ok

    _wait_for(lambda: "REDACTED" in controller.log_tail())
    tail = controller.log_tail(10_000)
    assert len(tail) <= 4_096
    assert "do-not-keep" not in tail
    assert "[REDACTED]" in tail
    controller.stop()


def test_workspace_and_profile_files_are_not_modified(tmp_path: Path) -> None:
    controller, _factory, _process, _clock = _controller(tmp_path)
    workspace_file = controller.config.workspace / "workspace.json"
    profile_file = controller.config.profile / "data.json"
    profile_file.write_text('{"revision": 4}', encoding="utf-8")
    before = {
        workspace_file: (workspace_file.read_bytes(), workspace_file.stat().st_mtime_ns),
        profile_file: (profile_file.read_bytes(), profile_file.stat().st_mtime_ns),
    }

    assert controller.start().ok
    assert controller.stop().ok

    after = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in before}
    assert after == before


def test_gui_worker_does_not_block_caller() -> None:
    window = LauncherWindow.__new__(LauncherWindow)
    window._worker = None
    release = threading.Event()
    completed = threading.Event()

    class Root:
        @staticmethod
        def after(_delay: int, callback) -> None:
            callback()

    window.root = Root()

    def action():
        release.wait(1)
        return object()

    started = time.monotonic()
    window._run(action, lambda _result: completed.set())
    elapsed = time.monotonic() - started

    assert elapsed < 0.1
    assert not completed.is_set()
    release.set()
    assert completed.wait(1)


def test_invalid_loopback_host_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "launcher.toml"
    path.write_text(
        """[launcher]
workspace = 'C:\\workspace'
profile = 'C:\\profile'
host = "0.0.0.0"
port = 8878
keyframe_fingerprint = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
normalizer_configuration_fingerprint = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
normalizer_input_set_fingerprint = "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
startup_timeout_seconds = 30
shutdown_timeout_seconds = 8
log_max_characters = 65536
""",
        encoding="utf-8",
    )

    with pytest.raises(LauncherConfigurationError, match="127.0.0.1"):
        load_launcher_config(path)


@pytest.mark.skipif(os.name != "nt", reason="Windows batch quoting regression")
def test_cmd_keeps_quoted_special_paths_and_config_as_separate_arguments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A literal double quote is illegal in a Windows path. Cover spaces, Unicode
    # special characters and an apostrophe while CMD adds double quotes to arguments.
    project_root = tmp_path / "HUHĂÄŚ â€“ zvlĂˇĹˇtnĂ­ 'quoted' path"
    scripts = project_root / ".venv" / "Scripts"
    package = project_root / "capture" / "huhac_launcher"
    scripts.mkdir(parents=True)
    package.mkdir(parents=True)
    shutil.copy2(Path("HUHAC-Launcher.cmd"), project_root / "HUHAC-Launcher.cmd")

    source_pythonw = Path(sys.executable).with_name("pythonw.exe")
    if not source_pythonw.is_file():
        pytest.skip("pythonw.exe is not available")
    shutil.copy2(source_pythonw, scripts / "pythonw.exe")
    source_venv = Path(sys.prefix) / "pyvenv.cfg"
    if not source_venv.is_file():
        source_venv = Path(sys.executable).parents[1] / "pyvenv.cfg"
    shutil.copy2(source_venv, project_root / ".venv" / "pyvenv.cfg")

    output = project_root / "captured argv.json"
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "__main__.py").write_text(
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "Path(os.environ['HUHAC_CAPTURE_ARGV']).write_text("
        "json.dumps(sys.argv), encoding='utf-8')\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PYTHONPATH", str(project_root / "capture"))
    monkeypatch.setenv("HUHAC_CAPTURE_ARGV", str(output))

    completed = subprocess.run(
        ["cmd.exe", "/d", "/c", "HUHAC-Launcher.cmd"],
        cwd=project_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    _wait_for(output.is_file, timeout=5)

    assert json.loads(output.read_text(encoding="utf-8")) == [
        str(package / "__main__.py"),
        "--project-root",
        str(project_root),
    ]
