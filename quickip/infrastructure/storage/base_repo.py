"""Base JSON repository with atomic writes.

All feature repositories should inherit from BaseJsonRepository
to get consistent file I/O, error handling, and atomic saves.
"""

import json
import logging
import os
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)


class BaseJsonRepository:
    """Persist a JSON array to a file with atomic write (write→rename).

    Subclasses call ``_load_raw()`` / ``_save_raw()`` and handle
    serialisation/deserialisation themselves.
    """

    def __init__(self, file_path: Path) -> None:
        self._path = file_path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    # ── Protected helpers ─────────────────────────────────────────

    def _load_raw(self) -> List[dict]:
        """Load JSON array from file.

        Returns an empty list on missing file, empty file, or corrupt JSON.
        """
        if not self._path.exists():
            return []
        try:
            text = self._path.read_text(encoding="utf-8").strip()
            if not text:
                return []
            data = json.loads(text)
            if not isinstance(data, list):
                logger.warning(f"Expected JSON array in {self._path}, got {type(data).__name__}")
                return []
            return data
        except json.JSONDecodeError as exc:
            logger.error(f"Corrupt JSON in {self._path}: {exc}")
            return []
        except Exception as exc:
            logger.error(f"Failed to read {self._path}: {exc}")
            return []

    def _save_raw(self, data: List[dict]) -> None:
        """Atomically write *data* as a JSON array.

        Writes to ``<file>.tmp`` then renames to the target path so that
        a crash mid-write never corrupts the existing file.
        """
        tmp = self._path.with_suffix(".tmp")
        try:
            tmp.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(tmp, self._path)
        except Exception as exc:
            logger.error(f"Failed to save {self._path}: {exc}")
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
            raise
