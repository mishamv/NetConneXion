"""Tools feature repository — persists user preferences for the tools page."""

from __future__ import annotations

import logging
from pathlib import Path

from quickip.core.paths import get_tools_settings_file
from quickip.core.storage.base_repo import BaseJsonRepository

logger = logging.getLogger(__name__)

_DEFAULTS = {
    "scan_interval": 2,      # seconds between connection-monitor polls
    "dns_cache_ttl": 600,    # seconds before reverse-DNS cache expires
}


class ToolsRepository(BaseJsonRepository):
    """Key-value store for tools settings, backed by tools_settings.json.

    Stored as a single-element JSON list so BaseJsonRepository's atomic
    write can be reused: [{"scan_interval": 2, "dns_cache_ttl": 600}].
    """

    def __init__(self, file_path: Path | None = None) -> None:
        super().__init__(file_path or get_tools_settings_file())
        rows = self._load_raw()
        self._data: dict = dict(_DEFAULTS)
        if rows and isinstance(rows[0], dict):
            self._data.update(rows[0])

    def get(self, key: str, default=None):
        return self._data.get(key, _DEFAULTS.get(key, default))

    def set(self, key: str, value) -> None:
        self._data[key] = value
        self._save_raw([self._data])

    def get_all(self) -> dict:
        return dict(self._data)
