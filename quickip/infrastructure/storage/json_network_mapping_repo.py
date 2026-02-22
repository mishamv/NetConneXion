"""JSON-based network mapping repository implementation."""

import json
import logging
import uuid
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from quickip.domain.interfaces import NetworkMappingRepository
from quickip.domain.models import NetworkMapping
from quickip.shared.paths import get_mappings_file


logger = logging.getLogger(__name__)


class JsonNetworkMappingRepository(NetworkMappingRepository):
    """JSON file-based network mapping storage."""

    def __init__(self, file_path: Optional[Path] = None):
        """
        Initialize repository.
        
        Args:
            file_path: Path to network_mappings.json (None = use default)
        """
        self.file_path = file_path or get_mappings_file()
        self._mappings: Dict[str, NetworkMapping] = {}
        self._load()

    def _load(self) -> None:
        """Load mappings from JSON file."""
        if not self.file_path.exists():
            logger.info(f"Mappings file not found: {self.file_path}, starting empty")
            self._mappings = {}
            return

        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self._mappings = {}
            for item in data:
                mapping = self._deserialize(item)
                self._mappings[mapping.id] = mapping

            logger.info(f"Loaded {len(self._mappings)} network mappings")

        except Exception as e:
            logger.error(f"Error loading mappings: {e}", exc_info=True)
            self._mappings = {}

    def _save(self) -> None:
        """Save mappings to JSON file."""
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)

            data = [self._serialize(m) for m in self._mappings.values()]

            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            logger.debug(f"Saved {len(self._mappings)} network mappings")

        except Exception as e:
            logger.error(f"Error saving mappings: {e}", exc_info=True)
            raise

    def _serialize(self, mapping: NetworkMapping) -> dict:
        """Convert mapping to JSON-serializable dict."""
        return {
            "id": mapping.id,
            "network_key": mapping.network_key,
            "profile_id": mapping.profile_id,
            "enabled": mapping.enabled,
            "created_at": mapping.created_at,
        }

    def _deserialize(self, data: dict) -> NetworkMapping:
        """Convert dict to NetworkMapping."""
        return NetworkMapping(
            id=data.get("id", str(uuid.uuid4())),
            network_key=data["network_key"],
            profile_id=data["profile_id"],
            enabled=data.get("enabled", True),
            created_at=data.get("created_at", datetime.now().isoformat()),
        )

    def list(self) -> List[NetworkMapping]:
        """Get all network mappings."""
        return list(self._mappings.values())

    def get(self, mapping_id: str) -> Optional[NetworkMapping]:
        """Get mapping by ID."""
        return self._mappings.get(mapping_id)

    def find_by_network(self, network_key: str) -> Optional[NetworkMapping]:
        """Find mapping by network identifier."""
        for mapping in self._mappings.values():
            if mapping.network_key == network_key:
                return mapping
        return None

    def save(self, mapping: NetworkMapping) -> None:
        """Save or update mapping."""
        # Generate ID if missing
        if not mapping.id:
            mapping.id = str(uuid.uuid4())

        self._mappings[mapping.id] = mapping
        self._save()
        
        logger.info(f"Saved mapping: {mapping.network_key} -> {mapping.profile_id}")

    def delete(self, mapping_id: str) -> None:
        """Delete mapping."""
        if mapping_id in self._mappings:
            network_key = self._mappings[mapping_id].network_key
            del self._mappings[mapping_id]
            self._save()
            logger.info(f"Deleted mapping: {network_key} ({mapping_id})")

    def get_enabled(self) -> List[NetworkMapping]:
        """Get only enabled mappings."""
        return [m for m in self._mappings.values() if m.enabled]

    def disable(self, mapping_id: str) -> None:
        """Disable a mapping."""
        if mapping_id in self._mappings:
            self._mappings[mapping_id].enabled = False
            self._save()
            logger.info(f"Disabled mapping: {mapping_id}")

    def enable(self, mapping_id: str) -> None:
        """Enable a mapping."""
        if mapping_id in self._mappings:
            self._mappings[mapping_id].enabled = True
            self._save()
            logger.info(f"Enabled mapping: {mapping_id}")
