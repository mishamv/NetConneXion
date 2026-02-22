"""Profile import/export service — JSON file-based data exchange."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional, TYPE_CHECKING

from quickip.core.models import Profile, IPMode, DNSMode, ImportConflict, ImportReport
from quickip.core.events.types import ProfilesImported

if TYPE_CHECKING:
    from quickip.features.profiles.repository import ProfileRepository
    from quickip.core.events.bus import EventBus

logger = logging.getLogger(__name__)

EXPORT_SCHEMA_VERSION = 1


class ImportExportService:
    """Import and export profile collections to/from JSON files."""

    def __init__(self, repo: "ProfileRepository", event_bus: "EventBus") -> None:
        self._repo = repo
        self._bus = event_bus

    # ── Export ────────────────────────────────────────────────────

    def export_profiles(
        self,
        path: str,
        profile_ids: Optional[List[str]] = None,
    ) -> None:
        """Export profiles to a JSON file.

        Args:
            path: Destination file path.
            profile_ids: Specific IDs to export; None exports all.
        """
        profiles = self._repo.list()
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
        logger.info("Exported %d profiles to %s", len(profiles), dest)

    # ── Import ────────────────────────────────────────────────────

    def import_profiles(
        self,
        path: str,
        strategy: str = "rename",        # "skip" | "rename" | "replace"
        selected_names: Optional[List[str]] = None,
    ) -> ImportReport:
        """Import profiles from a JSON file.

        Args:
            path: Source file path.
            strategy: Conflict resolution — "skip", "rename", or "replace".
            selected_names: Only import these profile names; None imports all.

        Returns:
            ImportReport with counts and conflict details.
        """
        raw_profiles = self._load_file(path)
        if selected_names is not None:
            raw_profiles = [p for p in raw_profiles if p.name in selected_names]

        conflicts: List[ImportConflict] = []
        errors: List[str] = []
        imported_ids: List[str] = []

        for imported in raw_profiles:
            existing = self._repo.find_by_name(imported.name)
            if existing:
                conflicts.append(ImportConflict(
                    existing_profile=existing,
                    imported_profile=imported,
                    conflict_type="name",
                ))
                if strategy == "skip":
                    continue
                elif strategy == "rename":
                    imported.name = self._unique_name(imported.name)
                    imported.id = str(uuid.uuid4())
                elif strategy == "replace":
                    imported.id = existing.id

            try:
                self._repo.save(imported)
                imported_ids.append(imported.id)
            except Exception as exc:
                errors.append(f"{imported.name}: {exc}")

        skipped = len(conflicts) if strategy == "skip" else 0
        successful = len(imported_ids)

        if imported_ids:
            self._bus.publish(ProfilesImported(count=successful, profile_ids=imported_ids))

        logger.info(
            "Import finished — imported=%d, skipped=%d, errors=%d",
            successful, skipped, len(errors),
        )
        return ImportReport(
            total_imported=len(raw_profiles),
            successful=successful,
            skipped=skipped,
            conflicts=conflicts,
            errors=errors,
        )

    # ── Preview ───────────────────────────────────────────────────

    def preview_import(self, path: str) -> List[ImportConflict]:
        """Check which profiles would conflict without applying changes."""
        return [
            ImportConflict(
                existing_profile=self._repo.find_by_name(p.name),
                imported_profile=p,
                conflict_type="name",
            )
            for p in self._load_file(path)
            if self._repo.find_by_name(p.name)
        ]

    # ── Helpers ───────────────────────────────────────────────────

    def _load_file(self, path: str) -> List[Profile]:
        src = Path(path)
        if not src.exists():
            raise FileNotFoundError(f"Import file not found: {src}")
        payload = json.loads(src.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            profile_list = payload
        elif isinstance(payload, dict):
            profile_list = payload.get("profiles", [])
        else:
            raise ValueError("Unrecognised import file format")
        return [self._deserialize(item) for item in profile_list]

    def _unique_name(self, base: str) -> str:
        name = f"{base} (imported)"
        idx = 2
        while self._repo.find_by_name(name):
            name = f"{base} (imported {idx})"
            idx += 1
        return name

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
        )
