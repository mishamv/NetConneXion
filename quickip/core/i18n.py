"""JSON-based internationalisation service."""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from quickip.core.interfaces import II18nService


logger = logging.getLogger(__name__)


class I18nService(II18nService):
    """Simple JSON-based i18n service.

    Loads ``<locale>.json`` from *locales_dir*.
    Falls back to ``data/locales/<locale>.json`` next to the project root.
    """

    def __init__(self, locales_dir: str, default_locale: str = "en") -> None:
        self.locales_dir = self._normalize(locales_dir)
        self.current_locale = default_locale
        self.translations: Dict[str, str] = {}
        self._load_translations()

    # ── Internals ────────────────────────────────────────────────

    @staticmethod
    def _normalize(locales_dir: str) -> str:
        try:
            p = Path(locales_dir).expanduser()
            return str(p.resolve() if p.is_absolute() else (Path.cwd() / p).resolve())
        except Exception:
            return locales_dir

    def _candidate_paths(self, locale: str) -> list[Path]:
        """Return candidate JSON paths in priority order."""
        candidates: list[Path] = [Path(self.locales_dir) / f"{locale}.json"]
        try:
            # quickip/core/i18n.py → parents[1] = quickip/ → parents[2] = project root
            root = Path(__file__).resolve().parents[2]
            candidates.append(root / "data" / "locales" / f"{locale}.json")
        except Exception:
            pass
        return candidates

    def _load_translations(self) -> None:
        self.translations = {}
        loaded_from: Optional[Path] = None
        for path in self._candidate_paths(self.current_locale):
            if path.exists():
                loaded_from = path
                break

        if loaded_from is None:
            primary = self._candidate_paths(self.current_locale)[0]
            logger.error(f"Locale file not found: {primary}")
            return

        try:
            with loaded_from.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, dict):
                raise ValueError("Locale JSON must be a key→text dict")
            self.translations = {str(k): str(v) for k, v in data.items()}
            logger.info(
                f"Loaded locale '{self.current_locale}' "
                f"({len(self.translations)} keys) from {loaded_from}"
            )
        except json.JSONDecodeError as exc:
            logger.error(f"Bad JSON in locale file {loaded_from}: {exc}")
        except Exception as exc:
            logger.error(f"Failed to load locale from {loaded_from}: {exc}")

    # ── Public API ────────────────────────────────────────────────

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
