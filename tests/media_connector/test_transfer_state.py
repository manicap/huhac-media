from __future__ import annotations

from pathlib import Path

import pytest

from media_connector.errors import ConnectorError
from media_connector.transfer_state import TransferRepository


def test_state_is_bound_to_workspace(tmp_path: Path) -> None:
    first = TransferRepository(tmp_path, "12345678-1234-5678-1234-567812345678")
    first.close()
    with pytest.raises(ConnectorError) as caught:
        TransferRepository(tmp_path, "87654321-4321-8765-4321-876543218765")
    assert caught.value.code == "STATE_LIBRARY_MISMATCH"

