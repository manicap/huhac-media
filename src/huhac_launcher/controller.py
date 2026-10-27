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
import threading
import time
from typing import BinaryIO, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from huhac_launcher.config import LauncherConfig, process_python, project_python


class LauncherState(str, Enum):
    OFF = "off"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


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


class BackendController:
    """Own exactly one child process; never adopt or kill a process by port/name."""

    def __init__(
        self,
        config: LauncherConfig,
        project_root: Path,
        *,
        process_factory: Callable[..., subprocess.Popen[bytes]] = subprocess.Popen,
        readiness_probe: Callable[[str], tuple[bool, str]] = http_readiness,
        port_checker: Callable[[str, int], bool] = port_is_available,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        runtime_validator: Callable[[LauncherConfig], object] | None = None,
    ) -> None:
        self.config = config
        self.project_root = Path(project_root).resolve()
        self.python = project_python(self.project_root)
        self.process_python = process_python(self.project_root)
        self._process_factory = process_factory
        self._readiness_probe = readiness_probe
        self._port_checker = port_checker
        self._monotonic = monotonic
        self._sleep = sleep
        if runtime_validator is None:
            from huhac_launcher.snapshots import validate_runtime

            runtime_validator = validate_runtime
        self._runtime_validator = runtime_validator
        self._lock = threading.RLock()
        self._process: subprocess.Popen[bytes] | None = None
        self._state = LauncherState.OFF
        self._error = ""
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
        if not self.config.profile.is_dir():
            return f"Izolovaný profil neexistuje: {self.config.profile}"
        try:
            self._runtime_validator(self.config)
        except Exception as exc:
            return f"Neplatný profil nebo workspace: {exc}"
        return None

    def _environment(self) -> dict[str, str]:
        environment = os.environ.copy()
        environment.update({
            "APPDATA": str(self.config.profile),
            "LOCALAPPDATA": str(self.config.profile),
            "MEDIA_DESK_WORKSPACE": str(self.config.workspace),
        })
        optional = {
            "MEDIA_DESK_KEYFRAME_FINGERPRINT": self.config.keyframe_fingerprint,
            "MEDIA_DESK_NORMALIZER_CONFIGURATION_FINGERPRINT": self.config.normalizer_configuration_fingerprint,
            "MEDIA_DESK_NORMALIZER_INPUT_SET_FINGERPRINT": self.config.normalizer_input_set_fingerprint,
        }
        for key, value in optional.items():
            if value is None:
                environment.pop(key, None)
            else:
                environment[key] = value
        virtual_environment = self.project_root / ".venv"
        scripts = virtual_environment / "Scripts"
        site_packages = virtual_environment / "Lib" / "site-packages"
        python_paths = [str(self.project_root / "src"), str(site_packages)]
        if environment.get("PYTHONPATH"):
            python_paths.append(environment["PYTHONPATH"])
        environment["VIRTUAL_ENV"] = str(virtual_environment)
        environment["PATH"] = os.pathsep.join(
            [str(scripts), environment.get("PATH", "")]
        ).rstrip(os.pathsep)
        environment["PYTHONPATH"] = os.pathsep.join(python_paths)
        environment["PYTHONNOUSERSITE"] = "1"
        return environment

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
                return ActionResult(True, "Media Desk už běží")
            self._process = None
            self._state = LauncherState.STARTING
            self._error = ""

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

        command = [
            str(self.process_python),
            "-m",
            "media_desk",
            "--host",
            self.config.host,
            "--port",
            str(self.config.port),
        ]
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
            error = f"Media Desk nelze spustit: {exc}"
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
                    f"Media Desk skončil během startu (kód {code})"
                )
                with self._lock:
                    if self._process is process:
                        self._process = None
                self._set_state(LauncherState.ERROR, error)
                return ActionResult(False, error)
            ready, last_readiness_error = self._readiness_probe(self.config.health_url)
            if ready:
                self._set_state(LauncherState.RUNNING)
                threading.Thread(
                    target=self._monitor,
                    args=(process,),
                    name="huhac-launcher-monitor",
                    daemon=True,
                ).start()
                return ActionResult(True, "Media Desk je spuštěný")
            self._sleep(0.1)

        self._stop_failed_start(process)
        with self._lock:
            if self._process is process:
                self._process = None
        suffix = f" ({last_readiness_error})" if last_readiness_error else ""
        error = f"Media Desk nenahlásil připravenost v časovém limitu{suffix}"
        self._set_state(LauncherState.ERROR, error)
        return ActionResult(False, error)

    def _monitor(self, process: subprocess.Popen[bytes]) -> None:
        code = process.wait()
        with self._lock:
            if self._process is not process:
                return
            self._process = None
            if self._state == LauncherState.STOPPING:
                self._state = LauncherState.OFF
                self._error = ""
                return
            if self._state == LauncherState.RUNNING:
                self._state = LauncherState.ERROR
                self._error = self._failure_detail(
                    f"Media Desk neočekávaně skončil (kód {code})"
                )

    def stop(self) -> ActionResult:
        with self._lock:
            process = self._process
            if process is None:
                self._state = LauncherState.OFF
                self._error = ""
                return ActionResult(True, "Media Desk je vypnutý")
            if process.poll() is not None:
                self._process = None
                self._state = LauncherState.OFF
                self._error = ""
                return ActionResult(True, "Media Desk je vypnutý")
            self._state = LauncherState.STOPPING
            self._error = ""

        try:
            process.terminate()
            process.wait(timeout=self.config.shutdown_timeout_seconds)
        except subprocess.TimeoutExpired:
            error = "Media Desk nereaguje na bezpečné ukončení"
            self._set_state(LauncherState.ERROR, error)
            return ActionResult(False, error, needs_force=True)
        except OSError as exc:
            error = f"Media Desk nelze zastavit: {exc}"
            self._set_state(LauncherState.ERROR, error)
            return ActionResult(False, error)

        with self._lock:
            if self._process is process:
                self._process = None
            self._state = LauncherState.OFF
            self._error = ""
        return ActionResult(True, "Media Desk byl zastaven")

    def force_stop(self) -> ActionResult:
        with self._lock:
            process = self._process
            if process is None or process.poll() is not None:
                self._process = None
                self._state = LauncherState.OFF
                self._error = ""
                return ActionResult(True, "Media Desk je vypnutý")
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
            self._state = LauncherState.OFF
            self._error = ""
        return ActionResult(True, "Media Desk byl vynuceně zastaven")

    def close(self, force_decider: Callable[[str], bool]) -> ActionResult:
        """Stop the owned child for window-close; never inspect or act on a foreign PID."""
        result = self.stop()
        if not result.needs_force:
            return result
        if not force_decider(result.message):
            return result
        return self.force_stop()
