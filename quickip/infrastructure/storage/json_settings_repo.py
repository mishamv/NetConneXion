"""JSON-based settings repository implementation."""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from quickip.domain.interfaces import SettingsRepository
from quickip.shared.paths import get_settings_file


logger = logging.getLogger(__name__)


class JsonSettingsRepository(SettingsRepository):
    """JSON file-based settings storage."""

    DEFAULT_SETTINGS = {
        "dark_mode": False,
        "minimize_to_tray": True,
        "auto_switch_enabled": False,
        "show_notifications": True,
        "check_updates": True,
        "log_level": "INFO",
        "last_profile_id": None,
        "window_geometry": None,
    }

    def __init__(self, file_path: Optional[Path] = None):
        """
        Initialize repository.
        
        Args:
            file_path: Path to settings.json (None = use default)
        """
        self.file_path = file_path or get_settings_file()
        self._settings: Dict[str, Any] = self.DEFAULT_SETTINGS.copy()
        self._load()

    def _load(self) -> None:
        """Load settings from JSON file."""
        if not self.file_path.exists():
            logger.info(f"Settings file not found: {self.file_path}, using defaults")
            self._settings = self.DEFAULT_SETTINGS.copy()
            self._save()  # Create file with defaults
            return

        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Merge with defaults (in case new settings were added)
            self._settings = self.DEFAULT_SETTINGS.copy()
            self._settings.update(data)

            logger.debug(f"Loaded settings from {self.file_path}")

        except Exception as e:
            logger.error(f"Error loading settings: {e}, using defaults", exc_info=True)
            self._settings = self.DEFAULT_SETTINGS.copy()

    def _save(self) -> None:
        """Save settings to JSON file."""
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)

            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(self._settings, f, ensure_ascii=False, indent=2)

            logger.debug("Saved settings")

        except Exception as e:
            logger.error(f"Error saving settings: {e}", exc_info=True)

    def get(self, key: str, default: Any = None) -> Any:
        """Get setting value."""
        return self._settings.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set setting value."""
        old_value = self._settings.get(key)
        self._settings[key] = value
        
        logger.debug(f"Setting changed: {key} = {value} (was {old_value})")

    def get_all(self) -> Dict[str, Any]:
        """Get all settings."""
        return self._settings.copy()

    def save(self) -> None:
        """Persist settings to storage."""
        self._save()

    def reset_to_defaults(self) -> None:
        """Reset all settings to defaults."""
        self._settings = self.DEFAULT_SETTINGS.copy()
        self._save()
        logger.info("Reset all settings to defaults")

    def get_bool(self, key: str, default: bool = False) -> bool:
        """Get boolean setting."""
        value = self.get(key, default)
        if isinstance(value, bool):
            return value
        return default

    def get_int(self, key: str, default: int = 0) -> int:
        """Get integer setting."""
        value = self.get(key, default)
        if isinstance(value, int):
            return value
        return default

    def get_str(self, key: str, default: str = "") -> str:
        """Get string setting."""
        value = self.get(key, default)
        if isinstance(value, str):
            return value
        return default
