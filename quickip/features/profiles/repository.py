"""Profile repository — JSON file storage with atomic writes."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from quickip.core.interfaces import ProfileRepository as _ProfileRepositoryABC
from quickip.core.models import Profile, IPMode, DNSMode
from quickip.core.storage.base_repo import BaseJsonRepository

logger = logging.getLogger(__name__)


class ProfileRepository(BaseJsonRepository, _ProfileRepositoryABC):
    """JSON file-backed profile storage.

    Inherits atomic write (write→rename) from BaseJsonRepository.
    Keeps an in-memory cache to avoid re-parsing on every read.
    """

    def __init__(self, file_path: Path) -> None:
        super().__init__(file_path)
        self._cache: dict[str, Profile] = {}  # keyed by profile ID
        self._rebuild_cache()

    # ── Cache management ──────────────────────────────────────────

    def _rebuild_cache(self) -> None:
        """Parse JSON from disk and populate the in-memory cache."""
        self._cache = {}
        for row in self._load_raw():
            try:
                p = self._deserialize(row)
                self._cache[p.id] = p
            except Exception as exc:
                logger.warning("Skipping corrupt profile row: %s", exc)
        logger.info("Loaded %d profiles from %s", len(self._cache), self._path)

    def _flush(self) -> None:
        """Atomically write all cached profiles to disk."""
        self._save_raw([self._serialize(p) for p in self._cache.values()])

    # ── ProfileRepository interface ────────────────────────────────

    def list(self) -> List[Profile]:
        return list(self._cache.values())

    def get(self, profile_id: str) -> Optional[Profile]:
        return self._cache.get(profile_id)

    def save(self, profile: Profile) -> None:
        profile.updated_at = datetime.now().isoformat()
        self._cache[profile.id] = profile
        self._flush()
        logger.debug("Saved profile: %s (%s)", profile.name, profile.id)

    def delete(self, profile_id: str) -> None:
        if profile_id in self._cache:
            name = self._cache[profile_id].name
            del self._cache[profile_id]
            self._flush()
            logger.info("Deleted profile: %s (%s)", name, profile_id)

    def exists(self, profile_id: str) -> bool:
        return profile_id in self._cache

    def find_by_name(self, name: str) -> Optional[Profile]:
        for p in self._cache.values():
            if p.name == name:
                return p
        return None

    def replace_all(self, profiles: List[Profile]) -> None:
        """Atomic bulk replace — write all profiles at once (no per-item save)."""
        self._cache = {p.id: p for p in profiles}
        self._flush()

    # ── Serialization ─────────────────────────────────────────────

    @staticmethod
    def _serialize(p: Profile) -> dict:
        return {
            "id": p.id,
            "name": p.name,
            "adapter": p.adapter,
            "dhcp_ip": p.is_dhcp_ip,
            "ip": p.ipv4,
            "mask": p.mask,
            "gateway": p.gateway,
            "dhcp_dns": p.is_dhcp_dns,
            "dns_primary": p.dns_primary,
            "dns_secondary": p.dns_secondary,
            "tags": p.tags,
            "created_at": p.created_at,
            "updated_at": p.updated_at,
        }

    @staticmethod
    def _deserialize(data: dict) -> Profile:
        return Profile(
            id=data.get("id", str(uuid.uuid4())),
            name=data["name"],
            adapter=data["adapter"],
            ip_mode=IPMode.DHCP if data.get("dhcp_ip", False) else IPMode.STATIC,
            ipv4=data.get("ip", ""),
            mask=data.get("mask", ""),
            gateway=data.get("gateway", ""),
            dns_mode=DNSMode.DHCP if data.get("dhcp_dns", False) else DNSMode.STATIC,
            dns_primary=data.get("dns_primary", ""),
            dns_secondary=data.get("dns_secondary", ""),
            tags=data.get("tags", []),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
        )
