"""History repository — JSON file storage with atomic writes."""

from __future__ import annotations

import logging
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from quickip.domain.interfaces import HistoryRepository as _HistoryRepositoryABC
from quickip.domain.models import ProfileHistoryEntry, HistoryStats, AdapterConfig
from quickip.infrastructure.storage.base_repo import BaseJsonRepository

logger = logging.getLogger(__name__)

_MAX_ENTRIES = 1000


class HistoryRepository(BaseJsonRepository, _HistoryRepositoryABC):
    """JSON file-backed history storage with atomic writes.

    Entries are stored newest-last; queries return newest-first.
    Trims to _MAX_ENTRIES automatically on append.
    """

    def __init__(self, file_path: Path) -> None:
        super().__init__(file_path)
        self._entries: List[ProfileHistoryEntry] = []
        self._load_entries()

    # ── Loading ───────────────────────────────────────────────────

    def _load_entries(self) -> None:
        rows = self._load_raw()
        self._entries = []
        for row in rows:
            try:
                self._entries.append(self._deserialize(row))
            except Exception as exc:
                logger.warning("Skipping corrupt history row: %s", exc)
        logger.info("Loaded %d history entries from %s", len(self._entries), self._path)

    def _flush(self) -> None:
        self._save_raw([self._serialize(e) for e in self._entries])

    # ── HistoryRepository interface ───────────────────────────────

    def append(self, entry: ProfileHistoryEntry) -> None:
        if not entry.id:
            entry.id = str(uuid.uuid4())
        self._entries.append(entry)
        if len(self._entries) > _MAX_ENTRIES:
            self._entries = self._entries[-_MAX_ENTRIES:]
        self._flush()
        logger.info("History entry added: %s on %s", entry.profile_name, entry.adapter)

    def list(
        self,
        limit: Optional[int] = None,
        profile_id: Optional[str] = None,
        success_only: Optional[bool] = None,
    ) -> List[ProfileHistoryEntry]:
        result = list(self._entries)
        if profile_id is not None:
            result = [e for e in result if e.profile_id == profile_id]
        if success_only is not None:
            result = [e for e in result if e.success == success_only]
        result.sort(key=lambda e: e.timestamp, reverse=True)
        if limit is not None:
            result = result[:limit]
        return result

    def get(self, entry_id: str) -> Optional[ProfileHistoryEntry]:
        for e in self._entries:
            if e.id == entry_id:
                return e
        return None

    def stats(self) -> HistoryStats:
        if not self._entries:
            return HistoryStats(total_applies=0, successful_applies=0,
                                failed_applies=0, avg_duration_ms=0.0)
        ok = [e for e in self._entries if e.success]
        avg_ms = sum(e.duration_ms for e in self._entries) / len(self._entries)
        profile_ctr = Counter(e.profile_name for e in self._entries)
        adapter_ctr = Counter(e.adapter for e in self._entries)
        return HistoryStats(
            total_applies=len(self._entries),
            successful_applies=len(ok),
            failed_applies=len(self._entries) - len(ok),
            avg_duration_ms=avg_ms,
            most_used_profile=profile_ctr.most_common(1)[0][0] if profile_ctr else None,
            most_used_adapter=adapter_ctr.most_common(1)[0][0] if adapter_ctr else None,
        )

    def clear(self) -> None:
        self._entries = []
        self._flush()
        logger.info("History cleared")

    # ── Serialization ─────────────────────────────────────────────

    @staticmethod
    def _serialize(e: ProfileHistoryEntry) -> dict:
        def _cfg(c: Optional[AdapterConfig]) -> Optional[dict]:
            if c is None:
                return None
            return {"adapter": c.adapter, "ip": c.ip, "mask": c.mask,
                    "gateway": c.gateway, "dns_servers": c.dns_servers,
                    "dhcp_enabled": c.dhcp_enabled, "timestamp": c.timestamp}

        return {
            "id": e.id,
            "timestamp": e.timestamp,
            "profile_id": e.profile_id,
            "profile_name": e.profile_name,
            "adapter": e.adapter,
            "success": e.success,
            "duration_ms": e.duration_ms,
            "previous_config": _cfg(e.previous_config),
            "new_config": _cfg(e.new_config),
            "commands": e.commands,
            "output": e.output,
            "error_message": e.error_message,
        }

    @staticmethod
    def _deserialize(data: dict) -> ProfileHistoryEntry:
        def _cfg(d: Optional[dict]) -> Optional[AdapterConfig]:
            if d is None:
                return None
            return AdapterConfig(
                adapter=d["adapter"], ip=d["ip"], mask=d["mask"],
                gateway=d["gateway"], dns_servers=d.get("dns_servers", []),
                dhcp_enabled=d.get("dhcp_enabled", False),
                timestamp=d.get("timestamp", datetime.now().isoformat()),
            )

        return ProfileHistoryEntry(
            id=data.get("id", str(uuid.uuid4())),
            timestamp=data["timestamp"],
            profile_id=data["profile_id"],
            profile_name=data["profile_name"],
            adapter=data["adapter"],
            success=data["success"],
            duration_ms=data["duration_ms"],
            previous_config=_cfg(data.get("previous_config")),
            new_config=_cfg(data.get("new_config")),
            commands=data.get("commands", []),
            output=data.get("output", []),
            error_message=data.get("error_message", ""),
        )
