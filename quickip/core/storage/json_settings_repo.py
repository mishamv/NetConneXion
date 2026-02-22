"""Core settings repository — JSON-backed key-value store.

This is the single shared settings store used by the entire application.
Feature-level code wraps it via typed accessor classes (e.g.
``quickip.features.settings.repository.SettingsRepository``).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from quickip.core.paths import get_settings_file

logger = logging.getLogger(__name__)

_DEFAULTS: Dict[str, Any] = {
    "ui_theme":           "light",
    "language":           "ru",
    "minimize_to_tray":   True,
    "show_notifications": True,
    "check_updates":      True,
    "log_level":          "INFO",
    "last_profile_id":    None,
    "window_geometry":    None,
}


class JsonSettingsRepository:
    """Persist application settings in a JSON file.

    Provides ``get`` / ``set`` / ``save`` so it can be wrapped by
    feature-level typed accessors without coupling features to this class.
    """

    def __init__(self, file_path: Optional[Path] = None) -> None:
        self._path = file_path or get_settings_file()
        self._data: Dict[str, Any] = dict(_DEFAULTS)
        self._load()

    # ── Public API ────────────────────────────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, _DEFAULTS.get(key, default))

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def get_all(self) -> Dict[str, Any]:
        return dict(self._data)

    def save(self) -> None:
        """Persist current settings to disk."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            tmp.replace(self._path)
            logger.debug("Settings saved to %s", self._path)
        except OSError as exc:
            logger.error("Settings save failed: %s", exc)

    def reset_to_defaults(self) -> None:
        self._data = dict(_DEFAULTS)
        self.save()

    # ── Convenience accessors ─────────────────────────────────────

    def get_bool(self, key: str, default: bool = False) -> bool:
        v = self.get(key, default)
        return bool(v) if not isinstance(v, bool) else v

    def get_int(self, key: str, default: int = 0) -> int:
        v = self.get(key, default)
        return int(v) if isinstance(v, (int, float)) else default

    def get_str(self, key: str, default: str = "") -> str:
        v = self.get(key, default)
        return str(v) if v is not None else default

    # ── Internal ──────────────────────────────────────────────────

    def _load(self) -> None:
        if not self._path.exists():
            self.save()  # write defaults on first run
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            self._data.update(loaded)
            logger.debug("Settings loaded from %s", self._path)
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("Settings load failed (%s), using defaults", exc)
