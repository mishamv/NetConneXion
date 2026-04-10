import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

from quickip.domain.interfaces import II18nService


class I18nService(II18nService):
    """
    Simple JSON-based i18n service.

    Fixes vs previous version:
    - normalizes locales_dir (absolute path)
    - fallback search for data/locales relative to project root
    - clears translations before reload
    - logs successful load with key count
    """

    def __init__(self, locales_dir: str, default_locale: str = "en"):
        self.logger = logging.getLogger(__name__)

        self.locales_dir = self._normalize_locales_dir(locales_dir)
        self.current_locale = default_locale
        self.translations: Dict[str, str] = {}

        self._load_translations()

    def _normalize_locales_dir(self, locales_dir: str) -> str:
        # Make absolute + normalized path
        try:
            p = Path(locales_dir).expanduser()
            if not p.is_absolute():
                p = (Path.cwd() / p).resolve()
            else:
                p = p.resolve()
            return str(p)
        except Exception:
            # Fallback to raw string if something weird happens
            return locales_dir

    def _candidate_paths(self, locale: str) -> list[Path]:
        """
        Returns candidate locale JSON paths to try, in priority order.
        """
        candidates: list[Path] = []

        # 1) Provided locales_dir
        candidates.append(Path(self.locales_dir) / f"{locale}.json")

        # 2) Fallback: try to locate project root and data/locales next to it
        # quickip/infrastructure/services/i18n_service.py -> parents[3] ~ project root
        try:
            root = Path(__file__).resolve().parents[3]
            candidates.append(root / "data" / "locales" / f"{locale}.json")
        except Exception:
            pass

        return candidates

    def _load_translations(self) -> None:
        # Clear old translations first (important when switching locales)
        self.translations = {}

        loaded_from: Optional[Path] = None
        for file_path in self._candidate_paths(self.current_locale):
            if file_path.exists():
                loaded_from = file_path
                break

        if loaded_from is None:
            # Log the first (primary) expected path for clarity
            primary = self._candidate_paths(self.current_locale)[0]
            self.logger.error(f"Locale file not found: {primary}")
            return

        try:
            with loaded_from.open("r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, dict):
                    raise ValueError("Locale JSON must be an object/dict of key->text")
                # Ensure values are strings (non-strings converted to str to avoid crashes)
                self.translations = {str(k): str(v) for k, v in data.items()}

            self.logger.info(
                f"Loaded locale '{self.current_locale}', keys={len(self.translations)} from {loaded_from}"
            )
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to load translations (bad JSON) from {loaded_from}: {e}")
        except Exception as e:
            self.logger.error(f"Failed to load translations from {loaded_from}: {e}")

    def get(self, key: str, **kwargs: Any) -> str:
        text = self.translations.get(key, key)
        if kwargs:
            try:
                return text.format(**kwargs)
            except (KeyError, ValueError):
                return text
        return text

    def set_locale(self, locale: str) -> None:
        if locale != self.current_locale:
            self.current_locale = locale
            self._load_translations()

    def get_current_locale(self) -> str:
        return self.current_locale
