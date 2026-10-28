from __future__ import annotations

from dataclasses import dataclass, replace
import json
import os
from pathlib import Path
import re
import tempfile
import tomllib
from uuid import uuid4


class LauncherConfigurationError(ValueError):
    """A safe, user-facing launcher configuration error."""


_FINGERPRINT = re.compile(r"[0-9a-f]{64}")
_PROFILE_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
_V1_KEYS = {
    "workspace", "profile", "host", "port", "keyframe_fingerprint",
    "normalizer_configuration_fingerprint", "normalizer_input_set_fingerprint",
    "startup_timeout_seconds", "shutdown_timeout_seconds", "log_max_characters",
}
_PROFILE_KEYS = {
    "id", "name", "workspace", "profile", "port", "keyframe_fingerprint",
    "normalizer_configuration_fingerprint", "normalizer_input_set_fingerprint",
}
_ROOT_KEYS = {
    "schema_version", "active_profile_id", "startup_timeout_seconds",
    "shutdown_timeout_seconds", "log_max_characters", "media_desk_python",
    "studio_python", "profiles",
}


@dataclass(frozen=True)
class LauncherConfig:
    """Immutable configuration for one backend process."""

    workspace: Path
    profile: Path
    host: str
    port: int
    keyframe_fingerprint: str | None
    normalizer_configuration_fingerprint: str | None
    normalizer_input_set_fingerprint: str | None
    startup_timeout_seconds: float = 30.0
    shutdown_timeout_seconds: float = 8.0
    log_max_characters: int = 65_536

    @property
    def address(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def health_url(self) -> str:
        return f"{self.address}/health"


@dataclass(frozen=True)
class LauncherProfile:
    id: str
    name: str
    workspace: Path
    profile: Path
    port: int
    keyframe_fingerprint: str | None = None
    normalizer_configuration_fingerprint: str | None = None
    normalizer_input_set_fingerprint: str | None = None

    @property
    def normalizer_selection(self) -> tuple[str, str] | None:
        if self.normalizer_configuration_fingerprint is None:
            return None
        assert self.normalizer_input_set_fingerprint is not None
        return (
            self.normalizer_configuration_fingerprint,
            self.normalizer_input_set_fingerprint,
        )


@dataclass(frozen=True)
class LauncherSettings:
    profiles: tuple[LauncherProfile, ...]
    active_profile_id: str
    startup_timeout_seconds: float = 30.0
    shutdown_timeout_seconds: float = 8.0
    log_max_characters: int = 65_536
    migrated_from_v1: bool = False
    media_desk_python: Path | None = None
    studio_python: Path | None = None

    @property
    def active_profile(self) -> LauncherProfile:
        for profile in self.profiles:
            if profile.id == self.active_profile_id:
                return profile
        raise LauncherConfigurationError("Aktivní profil v konfiguraci neexistuje")

    def runtime(self, profile: LauncherProfile | None = None) -> LauncherConfig:
        selected = profile or self.active_profile
        return LauncherConfig(
            workspace=selected.workspace,
            profile=selected.profile,
            host="127.0.0.1",
            port=selected.port,
            keyframe_fingerprint=selected.keyframe_fingerprint,
            normalizer_configuration_fingerprint=(
                selected.normalizer_configuration_fingerprint
            ),
            normalizer_input_set_fingerprint=selected.normalizer_input_set_fingerprint,
            startup_timeout_seconds=self.startup_timeout_seconds,
            shutdown_timeout_seconds=self.shutdown_timeout_seconds,
            log_max_characters=self.log_max_characters,
        )


def _string(values: dict[str, object], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value.strip():
        raise LauncherConfigurationError(f"Hodnota {key} musí být neprázdný text")
    return value.strip()


def _absolute(values: dict[str, object], key: str) -> Path:
    value = Path(_string(values, key)).expanduser()
    if not value.is_absolute():
        raise LauncherConfigurationError(f"Hodnota {key} musí být absolutní cesta")
    return value


def _optional_absolute(values: dict[str, object], key: str) -> Path | None:
    if values.get(key) is None:
        return None
    return _absolute(values, key)


def _optional_fingerprint(values: dict[str, object], key: str) -> str | None:
    value = values.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or _FINGERPRINT.fullmatch(value) is None:
        raise LauncherConfigurationError(
            f"Hodnota {key} musí obsahovat přesně 64 malých hexadecimálních znaků"
        )
    return value


def _port(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise LauncherConfigurationError("Port musí být celé číslo")
    if not 1024 <= value <= 65535:
        raise LauncherConfigurationError("Port musí být v rozsahu 1024 až 65535")
    return value


def parse_port(value: str) -> int:
    if not value or not value.isdecimal():
        raise LauncherConfigurationError("Port musí být celé číslo")
    return _port(int(value))


def _number(values: dict[str, object], key: str, minimum: float, maximum: float) -> float:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LauncherConfigurationError(f"Hodnota {key} musí být číslo")
    result = float(value)
    if not minimum <= result <= maximum:
        raise LauncherConfigurationError(
            f"Hodnota {key} musí být v rozsahu {minimum:g} až {maximum:g}"
        )
    return result


def _limits(values: dict[str, object]) -> tuple[float, float, int]:
    startup = _number(values, "startup_timeout_seconds", 1, 300)
    shutdown = _number(values, "shutdown_timeout_seconds", 1, 60)
    log_limit = values.get("log_max_characters")
    if isinstance(log_limit, bool) or not isinstance(log_limit, int) or not 4096 <= log_limit <= 1_048_576:
        raise LauncherConfigurationError(
            "log_max_characters musí být celé číslo od 4096 do 1048576"
        )
    return startup, shutdown, log_limit


def _profile(values: object) -> LauncherProfile:
    if not isinstance(values, dict) or set(values) - _PROFILE_KEYS:
        raise LauncherConfigurationError("Profil obsahuje nepodporované položky")
    required = {"id", "name", "workspace", "profile", "port"}
    if not required <= set(values):
        raise LauncherConfigurationError("Profil neobsahuje všechny povinné položky")
    identifier = _string(values, "id")
    if _PROFILE_ID.fullmatch(identifier) is None:
        raise LauncherConfigurationError("ID profilu má neplatný formát")
    normalizer_config = _optional_fingerprint(values, "normalizer_configuration_fingerprint")
    normalizer_input = _optional_fingerprint(values, "normalizer_input_set_fingerprint")
    if (normalizer_config is None) != (normalizer_input is None):
        raise LauncherConfigurationError("Normalizer snapshot vyžaduje oba fingerprinty")
    return LauncherProfile(
        id=identifier,
        name=_string(values, "name"),
        workspace=_absolute(values, "workspace"),
        profile=_absolute(values, "profile"),
        port=_port(values.get("port")),
        keyframe_fingerprint=_optional_fingerprint(values, "keyframe_fingerprint"),
        normalizer_configuration_fingerprint=normalizer_config,
        normalizer_input_set_fingerprint=normalizer_input,
    )


def _read(path: Path) -> dict[str, object]:
    try:
        payload = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise LauncherConfigurationError(f"Konfigurace launcheru neexistuje: {path}") from exc
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise LauncherConfigurationError(f"Konfiguraci launcheru nelze načíst: {exc}") from exc
    if not isinstance(payload, dict):
        raise LauncherConfigurationError("Konfigurace musí být TOML tabulka")
    return payload


def load_launcher_settings(path: Path) -> LauncherSettings:
    payload = _read(path)
    if "launcher" in payload:
        if set(payload) != {"launcher"} or not isinstance(payload["launcher"], dict):
            raise LauncherConfigurationError("Neplatná konfigurace Launcheru v0.1")
        values = payload["launcher"]
        if set(values) != _V1_KEYS:
            raise LauncherConfigurationError("Konfigurace Launcheru v0.1 má nepodporované nebo chybějící položky")
        if _string(values, "host") != "127.0.0.1":
            raise LauncherConfigurationError("Launcher smí používat pouze host 127.0.0.1")
        startup, shutdown, log_limit = _limits(values)
        profile = _profile({
            "id": "testovaci",
            "name": "Testovací",
            "workspace": _string(values, "workspace"),
            "profile": _string(values, "profile"),
            "port": values.get("port"),
            "keyframe_fingerprint": values.get("keyframe_fingerprint"),
            "normalizer_configuration_fingerprint": values.get("normalizer_configuration_fingerprint"),
            "normalizer_input_set_fingerprint": values.get("normalizer_input_set_fingerprint"),
        })
        return LauncherSettings((profile,), profile.id, startup, shutdown, log_limit, True)

    if set(payload) - _ROOT_KEYS or payload.get("schema_version") != 2:
        raise LauncherConfigurationError("Nepodporovaná verze konfigurace launcheru")
    profiles_value = payload.get("profiles")
    if not isinstance(profiles_value, list) or not profiles_value:
        raise LauncherConfigurationError("Konfigurace musí obsahovat alespoň jeden profil")
    profiles = tuple(_profile(value) for value in profiles_value)
    identifiers = [profile.id for profile in profiles]
    if len(set(identifiers)) != len(identifiers):
        raise LauncherConfigurationError("ID profilů musí být jedinečná")
    active = _string(payload, "active_profile_id")
    if active not in identifiers:
        raise LauncherConfigurationError("Aktivní profil v konfiguraci neexistuje")
    startup, shutdown, log_limit = _limits(payload)
    return LauncherSettings(
        profiles,
        active,
        startup,
        shutdown,
        log_limit,
        media_desk_python=_optional_absolute(payload, "media_desk_python"),
        studio_python=_optional_absolute(payload, "studio_python"),
    )


def load_launcher_config(path: Path) -> LauncherConfig:
    """Compatibility API returning the active runtime configuration."""
    return load_launcher_settings(path).runtime()


def _render(settings: LauncherSettings) -> str:
    lines = [
        "schema_version = 2",
        f"active_profile_id = {json.dumps(settings.active_profile_id, ensure_ascii=False)}",
    ]
    for key, value in (
        ("media_desk_python", settings.media_desk_python),
        ("studio_python", settings.studio_python),
    ):
        if value is not None:
            lines.append(f"{key} = {json.dumps(str(value), ensure_ascii=False)}")
    lines.extend((
        f"startup_timeout_seconds = {settings.startup_timeout_seconds:g}",
        f"shutdown_timeout_seconds = {settings.shutdown_timeout_seconds:g}",
        f"log_max_characters = {settings.log_max_characters}",
    ))
    for profile in settings.profiles:
        lines.extend(("", "[[profiles]]"))
        for key, value in (
            ("id", profile.id), ("name", profile.name),
            ("workspace", str(profile.workspace)), ("profile", str(profile.profile)),
            ("port", profile.port), ("keyframe_fingerprint", profile.keyframe_fingerprint),
            ("normalizer_configuration_fingerprint", profile.normalizer_configuration_fingerprint),
            ("normalizer_input_set_fingerprint", profile.normalizer_input_set_fingerprint),
        ):
            if value is None:
                continue
            rendered = str(value) if isinstance(value, int) else json.dumps(value, ensure_ascii=False)
            lines.append(f"{key} = {rendered}")
    return "\n".join(lines) + "\n"


def save_launcher_settings(path: Path, settings: LauncherSettings) -> None:
    # Validate the exact representation before replacing the previous file.
    startup, shutdown, log_limit = _limits({
        "startup_timeout_seconds": settings.startup_timeout_seconds,
        "shutdown_timeout_seconds": settings.shutdown_timeout_seconds,
        "log_max_characters": settings.log_max_characters,
    })
    validated = LauncherSettings(
        tuple(_profile({
            "id": p.id, "name": p.name, "workspace": str(p.workspace),
            "profile": str(p.profile), "port": p.port,
            **({"keyframe_fingerprint": p.keyframe_fingerprint} if p.keyframe_fingerprint else {}),
            **({"normalizer_configuration_fingerprint": p.normalizer_configuration_fingerprint,
                "normalizer_input_set_fingerprint": p.normalizer_input_set_fingerprint}
               if p.normalizer_configuration_fingerprint else {}),
        }) for p in settings.profiles),
        settings.active_profile_id,
        startup,
        shutdown,
        log_limit,
        media_desk_python=(
            _optional_absolute(
                {"media_desk_python": str(settings.media_desk_python)},
                "media_desk_python",
            )
            if settings.media_desk_python is not None
            else None
        ),
        studio_python=(
            _optional_absolute(
                {"studio_python": str(settings.studio_python)},
                "studio_python",
            )
            if settings.studio_python is not None
            else None
        ),
    )
    identifiers = [profile.id for profile in validated.profiles]
    if len(set(identifiers)) != len(identifiers):
        raise LauncherConfigurationError("ID profilů musí být jedinečná")
    if not validated.profiles or validated.active_profile_id not in set(identifiers):
        raise LauncherConfigurationError("Nelze uložit konfiguraci bez platného aktivního profilu")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=target.parent,
                                         prefix=f".{target.name}.", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(_render(validated))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except OSError as exc:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise LauncherConfigurationError(f"Konfiguraci launcheru nelze uložit: {exc}") from exc


def default_launcher_config_path(
    environ: dict[str, str] | None = None,
    *,
    platform: str | None = None,
) -> Path:
    """Return the host-local user configuration path without creating it."""
    values = os.environ if environ is None else environ
    current_platform = os.name if platform is None else platform
    if current_platform == "nt":
        base = values.get("LOCALAPPDATA")
        if not base:
            raise LauncherConfigurationError("Proměnná LOCALAPPDATA není nastavena")
        return Path(base) / "HUHAC" / "Launcher" / "launcher.toml"
    configured = values.get("XDG_CONFIG_HOME")
    base = Path(configured).expanduser() if configured else Path.home() / ".config"
    return base / "huhac" / "launcher" / "launcher.toml"


def initialize_launcher_config(path: Path, example_path: Path) -> bool:
    """Atomically seed a missing local config from a validated distribution example."""
    target = Path(path)
    if target.exists():
        return False
    example = load_launcher_settings(Path(example_path))
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", newline="\n", dir=target.parent,
            prefix=f".{target.name}.", suffix=".tmp", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(_render(replace(example, migrated_from_v1=False)))
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, target)
        except FileExistsError:
            return False
        return True
    except OSError as exc:
        raise LauncherConfigurationError(
            f"Lokální konfiguraci launcheru nelze založit: {exc}"
        ) from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class LauncherStore:
    def __init__(self, path: Path, settings: LauncherSettings) -> None:
        self.path = Path(path)
        self.settings = settings

    @classmethod
    def open(cls, path: Path, *, migrate: bool = True) -> "LauncherStore":
        settings = load_launcher_settings(path)
        store = cls(path, settings)
        if migrate and settings.migrated_from_v1:
            store.settings = replace(settings, migrated_from_v1=False)
            save_launcher_settings(store.path, store.settings)
        return store

    def _save(self, settings: LauncherSettings) -> None:
        save_launcher_settings(self.path, settings)
        self.settings = settings

    def activate(self, profile_id: str) -> None:
        if profile_id not in {p.id for p in self.settings.profiles}:
            raise LauncherConfigurationError("Vybraný profil neexistuje")
        self._save(replace(self.settings, active_profile_id=profile_id))

    def add(self, profile: LauncherProfile) -> None:
        if profile.id in {p.id for p in self.settings.profiles}:
            raise LauncherConfigurationError("Profil se stejným ID již existuje")
        self._save(replace(self.settings, profiles=(*self.settings.profiles, profile), active_profile_id=profile.id))

    def update(self, profile: LauncherProfile) -> None:
        if profile.id not in {p.id for p in self.settings.profiles}:
            raise LauncherConfigurationError("Upravovaný profil neexistuje")
        self._save(replace(self.settings, profiles=tuple(profile if p.id == profile.id else p for p in self.settings.profiles)))

    def remove(self, profile_id: str) -> None:
        remaining = tuple(p for p in self.settings.profiles if p.id != profile_id)
        if len(remaining) == len(self.settings.profiles):
            raise LauncherConfigurationError("Odebíraný profil neexistuje")
        if not remaining:
            raise LauncherConfigurationError("Poslední profil nelze odebrat")
        active = self.settings.active_profile_id
        if active == profile_id:
            active = remaining[0].id
        self._save(replace(self.settings, profiles=remaining, active_profile_id=active))

    @staticmethod
    def new_id() -> str:
        return f"profil-{uuid4().hex[:12]}"


def open_launcher_store(
    project_root: Path,
    *,
    explicit_config: Path | None = None,
    example_config: Path | None = None,
    environ: dict[str, str] | None = None,
    platform: str | None = None,
) -> LauncherStore:
    """Open an explicit config or initialize the host-local config on first start."""
    root = Path(project_root).resolve()
    if explicit_config is not None:
        return LauncherStore.open(Path(explicit_config).expanduser().resolve())
    path = default_launcher_config_path(environ, platform=platform)
    example = example_config or root / "config" / "launcher.example.toml"
    initialize_launcher_config(path, example)
    return LauncherStore.open(path)


def project_python(project_root: Path) -> Path:
    root = Path(project_root)
    windows = root / ".venv" / "Scripts" / "python.exe"
    if windows.is_file():
        return windows
    return root / ".venv" / "bin" / "python"


def _linked_main_worktree_root(project_root: Path) -> Path | None:
    marker = Path(project_root).resolve() / ".git"
    if not marker.is_file():
        return None
    try:
        prefix, raw_path = marker.read_text(encoding="utf-8").strip().split(":", 1)
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    if prefix.casefold() != "gitdir":
        return None
    git_directory = Path(raw_path.strip())
    if not git_directory.is_absolute():
        git_directory = (marker.parent / git_directory).resolve()
    if git_directory.parent.name.casefold() != "worktrees":
        return None
    candidate = git_directory.parent.parent.parent
    if not (candidate / "pyproject.toml").is_file():
        return None
    if not (candidate / "src" / "media_desk").is_dir():
        return None
    return candidate


def application_python(
    project_root: Path,
    application: str,
    configured: Path | None = None,
) -> Path:
    if configured is not None:
        return Path(configured).expanduser()
    root = Path(project_root).resolve()
    if application == "media-desk":
        main_worktree = _linked_main_worktree_root(root)
        if main_worktree is not None:
            candidate = project_python(main_worktree)
            if candidate.is_file():
                return candidate
    return project_python(root)


def virtual_environment_for_python(python: Path) -> Path | None:
    interpreter = Path(python)
    if interpreter.parent.name.casefold() not in {"scripts", "bin"}:
        return None
    candidate = interpreter.parent.parent
    return candidate if (candidate / "pyvenv.cfg").is_file() else None


def process_python_for(interpreter: Path) -> Path:
    project = Path(interpreter)
    environment = virtual_environment_for_python(project)
    if environment is None or project.parent.name.casefold() != "scripts":
        return project
    configuration = environment / "pyvenv.cfg"
    try:
        values = dict(
            (key.strip(), value.strip())
            for line in configuration.read_text(encoding="utf-8").splitlines()
            if "=" in line
            for key, value in (line.split("=", 1),)
        )
    except (OSError, UnicodeDecodeError):
        return project
    executable = values.get("executable", "")
    candidate = Path(executable) if executable else project
    return candidate if candidate.is_absolute() else project


def process_python(project_root: Path) -> Path:
    return process_python_for(project_python(project_root))
