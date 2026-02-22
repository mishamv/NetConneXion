"""JSON-based profile repository implementation."""

import json
import logging
import uuid
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from quickip.domain.interfaces import ProfileRepository
from quickip.domain.models import Profile, IPMode, DNSMode
from quickip.shared.paths import get_profiles_file


logger = logging.getLogger(__name__)


class JsonProfileRepository(ProfileRepository):
    """JSON file-based profile storage."""

    def __init__(self, file_path: Optional[Path] = None):
        """
        Initialize repository.
        
        Args:
            file_path: Path to profiles.json (None = use default from paths.py)
        """
        self.file_path = file_path or get_profiles_file()
        self._profiles: dict[str, Profile] = {}
        self._load()

    def _load(self) -> None:
        """Load profiles from JSON file."""
        if not self.file_path.exists():
            logger.info(f"Profiles file not found: {self.file_path}, starting empty")
            self._profiles = {}
            return

        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self._profiles = {}
            for item in data:
                profile = self._deserialize(item)
                self._profiles[profile.id] = profile

            logger.info(f"Loaded {len(self._profiles)} profiles from {self.file_path}")

        except Exception as e:
            logger.error(f"Error loading profiles: {e}", exc_info=True)
            self._profiles = {}

    def _save(self) -> None:
        """Save profiles to JSON file."""
        try:
            # Ensure directory exists
            self.file_path.parent.mkdir(parents=True, exist_ok=True)

            # Serialize to JSON
            data = [self._serialize(p) for p in self._profiles.values()]

            # Write to file
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            logger.debug(f"Saved {len(self._profiles)} profiles to {self.file_path}")

        except Exception as e:
            logger.error(f"Error saving profiles: {e}", exc_info=True)
            raise

    def _serialize(self, profile: Profile) -> dict:
        """Convert Profile to JSON-serializable dict."""
        return {
            "id": profile.id,
            "name": profile.name,
            "adapter": profile.adapter,
            "dhcp_ip": profile.is_dhcp_ip,  # Backward compatibility
            "ip": profile.ipv4,
            "mask": profile.mask,
            "gateway": profile.gateway,
            "dhcp_dns": profile.is_dhcp_dns,  # Backward compatibility
            "dns_primary": profile.dns_primary,
            "dns_secondary": profile.dns_secondary,
            "tags": profile.tags,
            "created_at": profile.created_at,
            "updated_at": profile.updated_at,
        }

    def _deserialize(self, data: dict) -> Profile:
        """Convert dict to Profile object."""
        # Handle legacy format
        dhcp_ip = data.get("dhcp_ip", False)
        dhcp_dns = data.get("dhcp_dns", False)

        return Profile(
            id=data.get("id", str(uuid.uuid4())),
            name=data["name"],
            adapter=data["adapter"],
            ip_mode=IPMode.DHCP if dhcp_ip else IPMode.STATIC,
            ipv4=data.get("ip", ""),
            mask=data.get("mask", ""),
            gateway=data.get("gateway", ""),
            dns_mode=DNSMode.DHCP if dhcp_dns else DNSMode.STATIC,
            dns_primary=data.get("dns_primary", ""),
            dns_secondary=data.get("dns_secondary", ""),
            tags=data.get("tags", []),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
        )

    def list(self) -> List[Profile]:
        """Get all profiles."""
        return list(self._profiles.values())

    def get(self, profile_id: str) -> Optional[Profile]:
        """Get profile by ID."""
        return self._profiles.get(profile_id)

    def save(self, profile: Profile) -> None:
        """Save or update profile."""
        # Update timestamp
        profile.updated_at = datetime.now().isoformat()

        # Add to cache
        self._profiles[profile.id] = profile

        # Persist to file
        self._save()

        logger.info(f"Saved profile: {profile.name} ({profile.id})")

    def delete(self, profile_id: str) -> None:
        """Delete profile by ID."""
        if profile_id in self._profiles:
            profile_name = self._profiles[profile_id].name
            del self._profiles[profile_id]
            self._save()
            logger.info(f"Deleted profile: {profile_name} ({profile_id})")

    def exists(self, profile_id: str) -> bool:
        """Check if profile exists."""
        return profile_id in self._profiles

    def find_by_name(self, name: str) -> Optional[Profile]:
        """Find profile by exact name."""
        for profile in self._profiles.values():
            if profile.name == name:
                return profile
        return None

    def reload(self) -> None:
        """Reload profiles from disk."""
        self._load()
