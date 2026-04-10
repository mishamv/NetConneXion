"""JSON-based history repository implementation."""

import logging
import uuid
from pathlib import Path
from typing import List, Optional
from datetime import datetime
from collections import Counter

from quickip.domain.interfaces import HistoryRepository
from quickip.domain.models import ProfileHistoryEntry, HistoryStats, AdapterConfig
from quickip.infrastructure.storage.base_repo import BaseJsonRepository
from quickip.shared.paths import get_history_file


logger = logging.getLogger(__name__)


class JsonHistoryRepository(BaseJsonRepository, HistoryRepository):
    """JSON file-based history storage with atomic writes."""

    def __init__(self, file_path: Optional[Path] = None, max_entries: int = 1000):
        BaseJsonRepository.__init__(self, file_path or get_history_file())
        self.max_entries = max_entries
        self._entries: List[ProfileHistoryEntry] = []
        self._load()

    def _load(self) -> None:
        self._entries = [self._deserialize(item) for item in self._load_raw()]
        if len(self._entries) > self.max_entries:
            self._entries = self._entries[-self.max_entries:]
            self._save()
        logger.debug(f"Loaded {len(self._entries)} history entries")

    def _save(self) -> None:
        self._save_raw([self._serialize(e) for e in self._entries])
        logger.debug(f"Saved {len(self._entries)} history entries")

    def _serialize(self, entry: ProfileHistoryEntry) -> dict:
        return {
            "id": entry.id,
            "timestamp": entry.timestamp,
            "profile_id": entry.profile_id,
            "profile_name": entry.profile_name,
            "adapter": entry.adapter,
            "success": entry.success,
            "duration_ms": entry.duration_ms,
            "previous_config": self._serialize_config(entry.previous_config),
            "new_config": self._serialize_config(entry.new_config),
            "commands": entry.commands,
            "output": entry.output,
            "error_message": entry.error_message,
        }

    def _serialize_config(self, config: Optional[AdapterConfig]) -> Optional[dict]:
        if config is None:
            return None
        return {
            "adapter": config.adapter,
            "ip": config.ip,
            "mask": config.mask,
            "gateway": config.gateway,
            "dns_servers": config.dns_servers,
            "dhcp_enabled": config.dhcp_enabled,
            "timestamp": config.timestamp,
        }

    def _deserialize(self, data: dict) -> ProfileHistoryEntry:
        return ProfileHistoryEntry(
            id=data.get("id", str(uuid.uuid4())),
            timestamp=data["timestamp"],
            profile_id=data["profile_id"],
            profile_name=data["profile_name"],
            adapter=data["adapter"],
            success=data["success"],
            duration_ms=data["duration_ms"],
            previous_config=self._deserialize_config(data.get("previous_config")),
            new_config=self._deserialize_config(data.get("new_config")),
            commands=data.get("commands", []),
            output=data.get("output", []),
            error_message=data.get("error_message", ""),
        )

    def _deserialize_config(self, data: Optional[dict]) -> Optional[AdapterConfig]:
        if data is None:
            return None
        return AdapterConfig(
            adapter=data["adapter"],
            ip=data["ip"],
            mask=data["mask"],
            gateway=data["gateway"],
            dns_servers=data.get("dns_servers", []),
            dhcp_enabled=data.get("dhcp_enabled", False),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
        )

    def append(self, entry: ProfileHistoryEntry) -> None:
        if not entry.id:
            entry.id = str(uuid.uuid4())
        self._entries.append(entry)
        if len(self._entries) > self.max_entries:
            self._entries = self._entries[-self.max_entries:]
        self._save()
        logger.debug(f"Added history entry: {entry.profile_name} on {entry.adapter}")

    def list(
        self,
        limit: Optional[int] = None,
        profile_id: Optional[str] = None,
        success_only: Optional[bool] = None,
    ) -> List[ProfileHistoryEntry]:
        result = self._entries.copy()
        if profile_id is not None:
            result = [e for e in result if e.profile_id == profile_id]
        if success_only is not None:
            result = [e for e in result if e.success == success_only]
        result.sort(key=lambda e: e.timestamp, reverse=True)
        if limit is not None:
            result = result[:limit]
        return result

    def get(self, entry_id: str) -> Optional[ProfileHistoryEntry]:
        for entry in self._entries:
            if entry.id == entry_id:
                return entry
        return None

    def stats(self) -> HistoryStats:
        if not self._entries:
            return HistoryStats(
                total_applies=0,
                successful_applies=0,
                failed_applies=0,
                avg_duration_ms=0.0,
                most_used_profile=None,
                most_used_adapter=None,
            )
        successful = [e for e in self._entries if e.success]
        failed = [e for e in self._entries if not e.success]
        avg_duration = sum(e.duration_ms for e in self._entries) / len(self._entries)
        profile_counter = Counter(e.profile_name for e in self._entries)
        adapter_counter = Counter(e.adapter for e in self._entries)
        return HistoryStats(
            total_applies=len(self._entries),
            successful_applies=len(successful),
            failed_applies=len(failed),
            avg_duration_ms=avg_duration,
            most_used_profile=profile_counter.most_common(1)[0][0] if profile_counter else None,
            most_used_adapter=adapter_counter.most_common(1)[0][0] if adapter_counter else None,
        )

    def clear(self) -> None:
        self._entries = []
        self._save()
        logger.info("Cleared all history")
