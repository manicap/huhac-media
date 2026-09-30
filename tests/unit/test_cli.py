from huhac_media.cli import main
from huhac_media.exit_codes import ExitCode


def test_ingest_requires_input() -> None:
    assert main(["ingest", "--dry-run"]) == ExitCode.USAGE_OR_CONFIG


def test_non_interactive_alias_is_accepted(tmp_path) -> None:
    result = main(["ingest", "--input", str(tmp_path), "--non-interactive"])
    assert result == ExitCode.FATAL

