from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import threading
import time
from typing import BinaryIO, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

from huhac_launcher.config import (
    LauncherConfig,
    application_python,
    process_python_for,
    virtual_environment_for_python,
)


class LauncherState(str, Enum):
    OFF = "off"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


class LauncherApplication(str, Enum):
    MEDIA_DESK = "media-desk"
    STUDIO = "studio"

    @property
    def title(self) -> str:
        if self is LauncherApplication.STUDIO:
            return "HUHÁČ Studio"
        return "Media Desk"


@dataclass(frozen=True)
class ActionResult:
    ok: bool
    message: str = ""
    needs_force: bool = False


_SENSITIVE = re.compile(
    r"(?i)(password|passwd|token|secret|authorization)(\s*[:=]\s*)([^\s]+)"
)


class BoundedLog:
    """Thread-safe, redacted in-memory tail used for short failure diagnostics."""

    def __init__(self, maximum_characters: int) -> None:
        self.maximum_characters = maximum_characters
        self._chunks: deque[str] = deque()
        self._length = 0
        self._lock = threading.Lock()

    def append(self, stream_name: str, data: bytes) -> None:
        text = data.decode("utf-8", errors="replace")
        text = _SENSITIVE.sub(r"\1\2[REDACTED]", text)
        value = f"[{stream_name}] {text}"
        if len(value) > self.maximum_characters:
            value = value[-self.maximum_characters :]
        with self._lock:
            self._chunks.append(value)
            self._length += len(value)
            while self._length > self.maximum_characters and self._chunks:
                removed = self._chunks.popleft()
                self._length -= len(removed)

    def tail(self, maximum: int = 1_000) -> str:
        with self._lock:
            return "".join(self._chunks)[-maximum:]

    def summary(self) -> str:
        lines = [line.strip() for line in self.tail().splitlines() if line.strip()]
        return lines[-1][:300] if lines else ""


def port_is_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            probe.bind((host, port))
        except OSError:
            return False
    return True


def http_readiness(url: str, timeout: float = 0.75) -> tuple[bool, str]:
    request = Request(url, headers={"User-Agent": "HUHAC-Launcher/0.2"})
    try:
        with urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                return False, f"HTTP {response.status}"
            payload = json.loads(response.read(16_384).decode("utf-8"))
    except HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except (OSError, URLError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return False, str(exc)
    if (
        not isinstance(payload, dict)
        or payload.get("status") != "ok"
        or not isinstance(payload.get("workspace_id"), str)
        or not payload["workspace_id"]
    ):
        return False, "Endpoint /health zatím není ready"
    return True, ""


def studio_http_readiness(
    url: str,
    expected_workspace_id: str,
    timeout: float = 0.75,
) -> tuple[bool, str]:
    request = Request(url, headers={"User-Agent": "HUHAC-Launcher/0.2"})
    try:
        with urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                return False, f"HTTP {response.status}"
            payload = json.loads(response.read(16_384).decode("utf-8"))
    except HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except (OSError, URLError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return False, str(exc)
    if (
        not isinstance(payload, dict)
        or not isinstance(payload.get("runtime_id"), str)
        or not payload["runtime_id"]
    ):
        return False, "Studio session zatím není ready"
    if payload.get("mode") != "online":
        return False, "Studio session není online"
    if payload.get("active_workspace_id") != expected_workspace_id:
        return False, "Studio session patří jinému workspace"
    return True, ""


class BackendController:
    """Own exactly one child process; never adopt or kill a process by port/name."""

    def __init__(
        self,
        config: LauncherConfig,
        project_root: Path,
        *,
        application: LauncherApplication = LauncherApplication.MEDIA_DESK,
        application_python_path: Path | None = None,
        process_factory: Callable[..., subprocess.Popen[bytes]] = subprocess.Popen,
        readiness_probe: Callable[[str], tuple[bool, str]] | None = None,
        port_checker: Callable[[str, int], bool] = port_is_available,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        runtime_validator: Callable[[LauncherConfig], object] | None = None,
    ) -> None:
        self.config = config
        self.project_root = Path(project_root).resolve()
        self.application = application
        self.python = application_python(
            self.project_root,
            application.value,
            application_python_path,
        )
        self.virtual_environment = virtual_environment_for_python(self.python)
        self.process_python = process_python_for(self.python)
        self._process_factory = process_factory
        self._readiness_probe = readiness_probe
        self._port_checker = port_checker
        self._monotonic = monotonic
        self._sleep = sleep
        if runtime_validator is None:
            if application is LauncherApplication.MEDIA_DESK:
                from huhac_launcher.snapshots import validate_runtime

                runtime_validator = validate_runtime
            else:
                from media_desk.contract import load_workspace

                runtime_validator = lambda runtime: load_workspace(runtime.workspace).workspace_id
        self._runtime_validator = runtime_validator
        self._expected_workspace_id = ""
        self._lock = threading.RLock()
        self._process: subprocess.Popen[bytes] | None = None
        self._state = LauncherState.OFF
        self._error = ""
        self._launch_id = ""
        self._logs = BoundedLog(config.log_max_characters)

    @property
    def state(self) -> LauncherState:
        with self._lock:
            return self._state

    @property
    def error(self) -> str:
        with self._lock:
            return self._error

    @property
    def owns_process(self) -> bool:
        with self._lock:
            return self._process is not None and self._process.poll() is None

    def log_tail(self, maximum: int = 1_000) -> str:
        return self._logs.tail(maximum)

    @property
    def readiness_url(self) -> str:
        if self.application is LauncherApplication.STUDIO:
            return f"{self.config.address}/api/studio/session"
        return self.config.health_url

    @property
    def browser_url(self) -> str:
        """Return an app/run-qualified URL so a browser cannot reuse stale UI."""
        with self._lock:
            launch_id = self._launch_id
        query = urlencode({
            "launcher_app": self.application.value,
            "launcher_run": launch_id,
        })
        return f"{self.config.address}/?{query}"

    @property
    def frontend_dir(self) -> Path:
        return self.project_root / "studio" / "dist"

    def _set_state(self, state: LauncherState, error: str = "") -> None:
        with self._lock:
            self._state = state
            self._error = error

    def _validate_runtime(self) -> str | None:
        if self.config.host != "127.0.0.1":
            return "Launcher smí spouštět backend pouze na 127.0.0.1"
        if not 1024 <= self.config.port <= 65535:
            return "Port musí být v rozsahu 1024 až 65535"
        if not self.python.is_file():
            return f"Projektový Python neexistuje: {self.python}"
        if not self.process_python.is_file():
            return f"Interpreter projektového prostředí neexistuje: {self.process_python}"
        if not self.config.workspace.is_dir():
            return f"Workspace neexistuje: {self.config.workspace}"
        if not (self.config.workspace / "workspace.json").is_file():
            return f"Workspace nemá workspace.json: {self.config.workspace}"
        if self.application is LauncherApplication.MEDIA_DESK and not self.config.profile.is_dir():
            return f"Izolovaný profil neexistuje: {self.config.profile}"
        if (
            self.application is LauncherApplication.STUDIO
            and not (self.frontend_dir / "index.html").is_file()
        ):
            return (
                f"Build Studia chybí: {self.frontend_dir}. "
                "V adresáři studio spusťte npm run build."
            )
        try:
            workspace_id = self._runtime_validator(self.config)
        except Exception as exc:
            return f"Neplatný profil nebo workspace: {exc}"
        if self.application is LauncherApplication.STUDIO:
            if not isinstance(workspace_id, str) or not workspace_id:
                return "Studio nedokázalo ověřit identitu workspace"
            self._expected_workspace_id = workspace_id
        return None

    def _environment(self) -> dict[str, str]:
        environment = os.environ.copy()
        optional = {
            "MEDIA_DESK_WORKSPACE": str(self.config.workspace),
            "MEDIA_DESK_KEYFRAME_FINGERPRINT": self.config.keyframe_fingerprint,
            "MEDIA_DESK_NORMALIZER_CONFIGURATION_FINGERPRINT": self.config.normalizer_configuration_fingerprint,
            "MEDIA_DESK_NORMALIZER_INPUT_SET_FINGERPRINT": self.config.normalizer_input_set_fingerprint,
        }
        if self.application is LauncherApplication.MEDIA_DESK:
            environment["APPDATA"] = str(self.config.profile)
            environment["LOCALAPPDATA"] = str(self.config.profile)
        else:
            # Studio owns one host-local project database. It must not inherit the
            # selected Media Desk profile or any Media Desk runtime overrides.
            for key in tuple(environment):
                if key.startswith("MEDIA_DESK_"):
                    environment.pop(key, None)
            optional = {key: None for key in optional}
        for key, value in optional.items():
            if value is None:
                environment.pop(key, None)
            else:
                environment[key] = value
        python_paths = [str(self.project_root / "src")]
        virtual_environment = self.virtual_environment
        if virtual_environment is not None:
            scripts = (
                virtual_environment / "Scripts"
                if os.name == "nt"
                else virtual_environment / "bin"
            )
            site_packages = virtual_environment / "Lib" / "site-packages"
            if os.name != "nt":
                version = f"python{sys.version_info.major}.{sys.version_info.minor}"
                site_packages = virtual_environment / "lib" / version / "site-packages"
            python_paths.append(str(site_packages))
            environment["VIRTUAL_ENV"] = str(virtual_environment)
            environment["PATH"] = os.pathsep.join(
                [str(scripts), environment.get("PATH", "")]
            ).rstrip(os.pathsep)
        else:
            environment.pop("VIRTUAL_ENV", None)
        if environment.get("PYTHONPATH"):
            python_paths.append(environment["PYTHONPATH"])
        environment["PYTHONPATH"] = os.pathsep.join(python_paths)
        environment["PYTHONNOUSERSITE"] = "1"
        return environment

    def _command(self) -> list[str]:
        if self.application is LauncherApplication.STUDIO:
            return [
                str(self.process_python),
                "-m",
                "huhac_studio.cli",
                "--workspace",
                str(self.config.workspace),
                "--host",
                self.config.host,
                "--port",
                str(self.config.port),
                "--frontend",
                str(self.frontend_dir),
            ]
        return [
            str(self.process_python),
            "-m",
            "media_desk",
            "--host",
            self.config.host,
            "--port",
            str(self.config.port),
        ]

    def _ready(self) -> tuple[bool, str]:
        if self._readiness_probe is not None:
            return self._readiness_probe(self.readiness_url)
        if self.application is LauncherApplication.STUDIO:
            return studio_http_readiness(
                self.readiness_url,
                self._expected_workspace_id,
            )
        return http_readiness(self.readiness_url)

    def _creation_flags(self) -> int:
        if os.name != "nt":
            return 0
        return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def _drain(self, stream: BinaryIO | None, name: str) -> None:
        if stream is None:
            return
        try:
            while chunk := stream.read(4096):
                self._logs.append(name, chunk)
        except (OSError, ValueError):
            return
        finally:
            try:
                stream.close()
            except OSError:
                pass

    def _start_log_drains(self, process: subprocess.Popen[bytes]) -> None:
        for stream, name in ((process.stdout, "stdout"), (process.stderr, "stderr")):
            threading.Thread(
                target=self._drain,
                args=(stream, name),
                name=f"huhac-launcher-{name}",
                daemon=True,
            ).start()

    def _failure_detail(self, prefix: str) -> str:
        summary = self._logs.summary()
        return f"{prefix}: {summary}" if summary else prefix

    def _stop_failed_start(self, process: subprocess.Popen[bytes]) -> None:
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=self.config.shutdown_timeout_seconds)
        except subprocess.TimeoutExpired:
            process.kill()
            try:
                process.wait(timeout=self.config.shutdown_timeout_seconds)
            except subprocess.TimeoutExpired:
                pass

    def start(self) -> ActionResult:
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                return ActionResult(True, f"{self.application.title} už běží")
            self._process = None
            self._state = LauncherState.STARTING
            self._error = ""
            self._launch_id = ""

        error = self._validate_runtime()
        if error:
            self._set_state(LauncherState.ERROR, error)
            return ActionResult(False, error)
        if not self._port_checker(self.config.host, self.config.port):
            error = (
                f"Port {self.config.port} používá jiný proces. "
                "Launcher jej nebude ukončovat."
            )
            self._set_state(LauncherState.ERROR, error)
            return ActionResult(False, error)

        command = self._command()
        try:
            process = self._process_factory(
                command,
                cwd=str(self.project_root),
                env=self._environment(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                creationflags=self._creation_flags(),
            )
        except OSError as exc:
            error = f"{self.application.title} nelze spustit: {exc}"
            self._set_state(LauncherState.ERROR, error)
            return ActionResult(False, error)

        with self._lock:
            self._process = process
        self._start_log_drains(process)
        deadline = self._monotonic() + self.config.startup_timeout_seconds
        last_readiness_error = ""
        while self._monotonic() < deadline:
            code = process.poll()
            if code is not None:
                error = self._failure_detail(
                    f"{self.application.title} skončilo během startu (kód {code})"
                )
                with self._lock:
                    if self._process is process:
                        self._process = None
                        self._launch_id = ""
                self._set_state(LauncherState.ERROR, error)
                return ActionResult(False, error)
            ready, last_readiness_error = self._ready()
            if ready:
                with self._lock:
                    self._launch_id = uuid4().hex
                self._set_state(LauncherState.RUNNING)
                threading.Thread(
                    target=self._monitor,
                    args=(process,),
                    name="huhac-launcher-monitor",
                    daemon=True,
                ).start()
                return ActionResult(True, f"{self.application.title} je spuštěné")
            self._sleep(0.1)

        self._stop_failed_start(process)
        with self._lock:
            if self._process is process:
                self._process = None
                self._launch_id = ""
        suffix = f" ({last_readiness_error})" if last_readiness_error else ""
        error = f"{self.application.title} nenahlásilo připravenost v časovém limitu{suffix}"
        self._set_state(LauncherState.ERROR, error)
        return ActionResult(False, error)

    def _monitor(self, process: subprocess.Popen[bytes]) -> None:
        code = process.wait()
        with self._lock:
            if self._process is not process:
                return
            self._process = None
            self._launch_id = ""
            if self._state == LauncherState.STOPPING:
                self._state = LauncherState.OFF
                self._error = ""
                return
            if self._state == LauncherState.RUNNING:
                self._state = LauncherState.ERROR
                self._error = self._failure_detail(
                    f"{self.application.title} neočekávaně skončilo (kód {code})"
                )

    def stop(self) -> ActionResult:
        with self._lock:
            process = self._process
            if process is None:
                self._state = LauncherState.OFF
                self._error = ""
                self._launch_id = ""
                return ActionResult(True, f"{self.application.title} je vypnuté")
            if process.poll() is not None:
                self._process = None
                self._state = LauncherState.OFF
                self._error = ""
                self._launch_id = ""
                return ActionResult(True, f"{self.application.title} je vypnuté")
            self._state = LauncherState.STOPPING
            self._error = ""

        try:
            process.terminate()
            process.wait(timeout=self.config.shutdown_timeout_seconds)
        except subprocess.TimeoutExpired:
            error = f"{self.application.title} nereaguje na bezpečné ukončení"
            self._set_state(LauncherState.ERROR, error)
            return ActionResult(False, error, needs_force=True)
        except OSError as exc:
            error = f"{self.application.title} nelze zastavit: {exc}"
            self._set_state(LauncherState.ERROR, error)
            return ActionResult(False, error)

        with self._lock:
            if self._process is process:
                self._process = None
            self._launch_id = ""
            self._state = LauncherState.OFF
            self._error = ""
        return ActionResult(True, f"{self.application.title} bylo zastaveno")

    def force_stop(self) -> ActionResult:
        with self._lock:
            process = self._process
            if process is None or process.poll() is not None:
                self._process = None
                self._state = LauncherState.OFF
                self._error = ""
                self._launch_id = ""
                return ActionResult(True, f"{self.application.title} je vypnuté")
            self._state = LauncherState.STOPPING
            self._error = ""
        try:
            process.kill()
            process.wait(timeout=self.config.shutdown_timeout_seconds)
        except (OSError, subprocess.TimeoutExpired) as exc:
            error = f"Vlastněný proces se nepodařilo vynuceně ukončit: {exc}"
            self._set_state(LauncherState.ERROR, error)
            return ActionResult(False, error)
        with self._lock:
            if self._process is process:
                self._process = None
            self._launch_id = ""
            self._state = LauncherState.OFF
            self._error = ""
        return ActionResult(True, f"{self.application.title} bylo vynuceně zastaveno")

    def close(self, force_decider: Callable[[str], bool]) -> ActionResult:
        """Stop the owned child for window-close; never inspect or act on a foreign PID."""
        result = self.stop()
        if not result.needs_force:
            return result
        if not force_decider(result.message):
            return result
        return self.force_stop()
