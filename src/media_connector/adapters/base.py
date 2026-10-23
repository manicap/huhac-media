from __future__ import annotations

from typing import Protocol

from media_connector.models import AdapterCapabilities, ObjectPage


class SourceAdapter(Protocol):
    @property
    def adapter_kind(self) -> str: ...

    @property
    def source_id(self) -> str: ...

    @property
    def capabilities(self) -> AdapterCapabilities: ...

    def list_page(self, *, page_size: int, cursor: str | None) -> ObjectPage: ...
