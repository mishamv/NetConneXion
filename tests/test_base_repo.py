"""Tests for quickip.infrastructure.storage.base_repo.BaseJsonRepository.

Covers: atomic write (write→rename pattern), corrupt JSON recovery,
backup creation, missing file, empty file, and non-array JSON.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from quickip.infrastructure.storage.base_repo import BaseJsonRepository


class _Repo(BaseJsonRepository):
    """Minimal concrete subclass for test driving the base class."""

    def save(self, data: list[dict]) -> None:
        self._save_raw(data)

    def load(self) -> list[dict]:
        return self._load_raw()


class TestBaseJsonRepositoryLoad(unittest.TestCase):

    def setUp(self):
        self._dir = tempfile.mkdtemp()
        self._path = Path(self._dir) / "data.json"
        self.repo = _Repo(self._path)

    # ── load: happy paths ─────────────────────────────────────────

    def test_missing_file_returns_empty(self):
        self.assertFalse(self._path.exists())
        self.assertEqual(self.repo.load(), [])

    def test_empty_file_returns_empty(self):
        self._path.write_text("", encoding="utf-8")
        self.assertEqual(self.repo.load(), [])

    def test_whitespace_only_file_returns_empty(self):
        self._path.write_text("   \n  ", encoding="utf-8")
        self.assertEqual(self.repo.load(), [])

    def test_valid_array_returned(self):
        data = [{"id": "1", "name": "Test"}]
        self._path.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(self.repo.load(), data)

    def test_valid_empty_array_returned(self):
        self._path.write_text("[]", encoding="utf-8")
        self.assertEqual(self.repo.load(), [])

    # ── load: error recovery ──────────────────────────────────────

    def test_corrupt_json_returns_empty(self):
        self._path.write_text("{broken json[", encoding="utf-8")
        self.assertEqual(self.repo.load(), [])

    def test_json_object_not_array_returns_empty(self):
        self._path.write_text('{"key": "val"}', encoding="utf-8")
        self.assertEqual(self.repo.load(), [])

    def test_json_string_not_array_returns_empty(self):
        self._path.write_text('"just a string"', encoding="utf-8")
        self.assertEqual(self.repo.load(), [])

    def test_json_null_returns_empty(self):
        self._path.write_text("null", encoding="utf-8")
        self.assertEqual(self.repo.load(), [])


class TestBaseJsonRepositorySave(unittest.TestCase):

    def setUp(self):
        self._dir = tempfile.mkdtemp()
        self._path = Path(self._dir) / "subdir" / "data.json"
        self.repo = _Repo(self._path)

    # ── save: basic ───────────────────────────────────────────────

    def test_save_creates_file(self):
        self.repo.save([{"id": "1"}])
        self.assertTrue(self._path.exists())

    def test_save_creates_parent_dirs(self):
        self.assertTrue(self._path.parent.exists())

    def test_save_persists_data(self):
        data = [{"id": "1", "name": "Alice"}, {"id": "2", "name": "Bob"}]
        self.repo.save(data)
        loaded = json.loads(self._path.read_text(encoding="utf-8"))
        self.assertEqual(loaded, data)

    def test_save_roundtrip(self):
        data = [{"id": "x", "val": 42, "nested": {"a": 1}}]
        self.repo.save(data)
        self.assertEqual(self.repo.load(), data)

    def test_save_overwrites_previous(self):
        self.repo.save([{"id": "old"}])
        self.repo.save([{"id": "new"}])
        self.assertEqual(self.repo.load(), [{"id": "new"}])

    def test_save_empty_list(self):
        self.repo.save([])
        self.assertEqual(self.repo.load(), [])

    # ── save: atomic write ────────────────────────────────────────

    def test_no_tmp_file_after_save(self):
        """Temp file must be renamed away after a successful save."""
        self.repo.save([{"id": "1"}])
        tmp = self._path.with_suffix(".tmp")
        self.assertFalse(tmp.exists(), ".tmp file should not remain after save")

    def test_backup_created_on_second_save(self):
        """A .bak file must appear after the second save (first write creates target)."""
        self.repo.save([{"id": "v1"}])
        self.repo.save([{"id": "v2"}])
        bak = self._path.with_suffix(".bak")
        self.assertTrue(bak.exists(), ".bak file should exist after second save")

    def test_backup_contains_previous_data(self):
        first = [{"id": "v1", "important": True}]
        self.repo.save(first)
        self.repo.save([{"id": "v2"}])
        bak = self._path.with_suffix(".bak")
        bak_data = json.loads(bak.read_text(encoding="utf-8"))
        self.assertEqual(bak_data, first)

    def test_unicode_preserved(self):
        data = [{"name": "Привет, мир", "emoji": "☃"}]
        self.repo.save(data)
        self.assertEqual(self.repo.load(), data)

    # ── save: corrupt then recover ────────────────────────────────

    def test_save_after_corrupt_file(self):
        """Even if the existing file is corrupt, save should succeed."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text("{bad json", encoding="utf-8")
        fresh = [{"id": "fresh"}]
        self.repo.save(fresh)
        self.assertEqual(self.repo.load(), fresh)


if __name__ == "__main__":
    unittest.main()
