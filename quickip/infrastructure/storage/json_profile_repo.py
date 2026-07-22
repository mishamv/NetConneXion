"""JSON-based profile repository implementation."""

import logging
import uuid
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from quickip.domain.interfaces import ProfileRepository
from quickip.domain.models import Profile, IPMode, DNSMode
from quickip.infrastructure.storage.base_repo import BaseJsonRepository
from quickip.shared.paths import get_profiles_file


logger = logging.getLogger(__name__)


def _serialize_profile(profile: Profile) -> dict:
    return {
        "id": profile.id,
        "name": profile.name,
        "adapter": profile.adapter,
        "dhcp_ip": profile.is_dhcp_ip,
        "ip": profile.ipv4,
        "mask": profile.mask,
        "gateway": profile.gateway,
        "dhcp_dns": profile.is_dhcp_dns,
        "dns_primary": profile.dns_primary,
        "dns_secondary": profile.dns_secondary,
        "tags": profile.tags,
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
        "auto_switch_ssid": profile.auto_switch_ssid,
    }


def _deserialize_profile(data: dict) -> Profile:
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
        auto_switch_ssid=data.get("auto_switch_ssid", ""),
    )


class JsonProfileRepository(BaseJsonRepository, ProfileRepository):
    """JSON file-based profile storage with atomic writes."""

    def __init__(self, file_path: Optional[Path] = None):
        BaseJsonRepository.__init__(self, file_path or get_profiles_file())
        self._profiles: dict[str, Profile] = {}
        self._load()

    def _load(self) -> None:
        self._profiles = {}
        for item in self._load_raw():
            profile = self._deserialize(item)
            self._profiles[profile.id] = profile
        logger.debug(f"Loaded {len(self._profiles)} profiles from {self._path}")

    def _save(self) -> None:
        self._save_raw([self._serialize(p) for p in self._profiles.values()])
        logger.debug(f"Saved {len(self._profiles)} profiles")

    _serialize = staticmethod(_serialize_profile)
    _deserialize = staticmethod(_deserialize_profile)

    def list(self) -> List[Profile]:
        return list(self._profiles.values())

    def get(self, profile_id: str) -> Optional[Profile]:
        return self._profiles.get(profile_id)

    def save(self, profile: Profile) -> None:
        profile.updated_at = datetime.now().isoformat()
        self._profiles[profile.id] = profile
        self._save()
        logger.info(f"Saved profile: {profile.name} ({profile.id})")

    def delete(self, profile_id: str) -> None:
        if profile_id in self._profiles:
            profile_name = self._profiles[profile_id].name
            del self._profiles[profile_id]
            self._save()
            logger.info(f"Deleted profile: {profile_name} ({profile_id})")

    def exists(self, profile_id: str) -> bool:
        return profile_id in self._profiles

    def find_by_name(self, name: str) -> Optional[Profile]:
        for profile in self._profiles.values():
            if profile.name == name:
                return profile
        return None

    def replace_all(self, profiles: List[Profile]) -> None:
        """Atomic bulk replace — write all profiles at once (no per-item save)."""
        self._profiles = {p.id: p for p in profiles}
        self._save()

    def reload(self) -> None:
        self._load()
