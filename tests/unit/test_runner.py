import subprocess

import pytest

from huhac_media.domain.errors import MediaError
from huhac_media.tools.runner import CommandRunner


def test_timeout_is_stable_media_error(monkeypatch) -> None:
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(MediaError) as error:
        CommandRunner().run(["tool"], timeout=0.1)
    assert error.value.code == "TOOL_TIMEOUT"


def test_nonzero_exit_is_stable_media_error(monkeypatch) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 7, "", "broken"),
    )
    with pytest.raises(MediaError) as error:
        CommandRunner().run(["tool"])
    assert error.value.code == "TOOL_FAILED"
    assert error.value.diagnostics["returncode"] == 7
