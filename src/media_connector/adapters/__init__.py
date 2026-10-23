"""Source adapters owned by Media Connector."""

from media_connector.adapters.base import SourceAdapter
from media_connector.adapters.local import LocalFilesystemAdapter

__all__ = ["LocalFilesystemAdapter", "SourceAdapter"]
