"""Import/Export service for profile data exchange."""

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from quickip.domain.models import (
    Profile, IPMode, DNSMode,
    ImportConflict, ImportReport
)
from quickip.domain.interfaces import ProfileRepository
from quickip.events.bus import EventBus
from quickip.events.event_types import ProfilesImported

logger = logging.getLogger(__name__)

EXPORT_SCHEMA_VERSION = 1


class ImportExportService:
    """Service for importing and exporting profile collections."""

    def __init__(self, profile_repo: ProfileRepository, event_bus: EventBus):
        self.profile_repo = profile_repo
        self.events = event_bus

    # ── Export ──────────────────────────────────────────────────

    def export_profiles(
        self,
        path: str,
        profile_ids: Optional[List[str]] = None
    ) -> None:
        """
        Export profiles to JSON file.

        Args:
            path: Destination file path
            profile_ids: Specific IDs to export (None = all)
        """
        profiles = self.profile_repo.list()
        if profile_ids is not None:
            profiles = [p for p in profiles if p.id in profile_ids]

        payload = {
            "schema_version": EXPORT_SCHEMA_VERSION,
            "app": "quick-ip-change",
            "exported_at": datetime.now().isoformat(),
            "profiles": [self._serialize(p) for p in profiles],
        }

        dest = Path(path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        logger.info(f"Exported {len(profiles)} profiles to {dest}")

    # ── Import ──────────────────────────────────────────────────

    def import_profiles(
        self,
        path: str,
        strategy: str = "rename",        # "skip" | "rename" | "replace"
        selected_names: Optional[List[str]] = None,
    ) -> ImportReport:
        """
        Import profiles from a JSON file.

        Args:
            path: Source file path
            strategy: Conflict resolution ("skip", "rename", "replace")
            selected_names: Only import these profile names (None = all)

        Returns:
            ImportReport with counts and conflicts
        """
        raw_profiles = self._load_file(path)

        if selected_names is not None:
            raw_profiles = [p for p in raw_profiles if p.name in selected_names]

        conflicts: List[ImportConflict] = []
        errors: List[str] = []
        imported_ids: List[str] = []

        for imported in raw_profiles:
            existing = self.profile_repo.find_by_name(imported.name)
            if existing:
                conflict = ImportConflict(
                    existing_profile=existing,
                    imported_profile=imported,
                    conflict_type="name",
                )
                conflicts.append(conflict)

                if strategy == "skip":
                    continue
                elif strategy == "rename":
                    imported.name = self._unique_name(imported.name)
                    imported.id = str(uuid.uuid4())
                elif strategy == "replace":
                    imported.id = existing.id   # overwrite in-place

            try:
                self.profile_repo.save(imported)
                imported_ids.append(imported.id)
            except Exception as exc:
                errors.append(f"{imported.name}: {exc}")

        skipped = len(conflicts) if strategy == "skip" else 0
        successful = len(imported_ids)

        if imported_ids:
            self.events.publish(ProfilesImported(
                count=successful,
                profile_ids=imported_ids,
            ))

        logger.info(
            f"Import finished – imported={successful}, "
            f"skipped={skipped}, errors={len(errors)}"
        )

        return ImportReport(
            total_imported=len(raw_profiles),
            successful=successful,
            skipped=skipped,
            conflicts=conflicts,
            errors=errors,
        )

    # ── Preview ──────────────────────────────────────────────────

    def preview_import(self, path: str) -> List[ImportConflict]:
        """
        Check which profiles would conflict without applying changes.

        Args:
            path: Source file path

        Returns:
            List of conflicts (empty = no conflicts)
        """
        raw_profiles = self._load_file(path)
        conflicts = []

        for imported in raw_profiles:
            existing = self.profile_repo.find_by_name(imported.name)
            if existing:
                conflicts.append(ImportConflict(
                    existing_profile=existing,
                    imported_profile=imported,
                    conflict_type="name",
                ))

        return conflicts

    # ── Helpers ──────────────────────────────────────────────────

    def _load_file(self, path: str) -> List[Profile]:
        """Load and parse profiles from file."""
        src = Path(path)
        if not src.exists():
            raise FileNotFoundError(f"Import file not found: {src}")

        payload = json.loads(src.read_text(encoding="utf-8"))

        # Wrap bare list in schema envelope
        if isinstance(payload, list):
            profile_list = payload
        elif isinstance(payload, dict):
            profile_list = payload.get("profiles", [])
        else:
            raise ValueError("Unrecognised import file format")

        return [self._deserialize(item) for item in profile_list]

    def _unique_name(self, base: str) -> str:
        """Generate unique profile name by appending (N)."""
        name = f"{base} (imported)"
        idx = 2
        while self.profile_repo.find_by_name(name):
            name = f"{base} (imported {idx})"
            idx += 1
        return name

    def _serialize(self, profile: Profile) -> dict:
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
        }

    def _deserialize(self, data: dict) -> Profile:
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
        )
