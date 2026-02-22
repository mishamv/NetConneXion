"""Profile matching service for auto-switching."""

import logging
from typing import Optional

from quickip.domain.models import NetworkFingerprint
from quickip.domain.interfaces import ProfileRepository, NetworkMappingRepository
from quickip.infrastructure.system.network_probe import NetworkProbe


logger = logging.getLogger(__name__)


class ProfileMatchService:
    """Match networks to profiles for auto-switching."""

    def __init__(
        self,
        profile_repo: ProfileRepository,
        mapping_repo: NetworkMappingRepository,
        network_probe: NetworkProbe
    ):
        """
        Initialize service.
        
        Args:
            profile_repo: Profile repository
            mapping_repo: Network mapping repository
            network_probe: Network detection service
        """
        self.profile_repo = profile_repo
        self.mapping_repo = mapping_repo
        self.probe = network_probe

    def resolve_for_current_network(self) -> Optional[str]:
        """
        Get profile ID for current network.
        
        Returns:
            Profile ID to apply or None if no match
        """
        # Detect current network
        fingerprint = self.probe.get_current_network()
        
        if not fingerprint.is_valid:
            logger.debug("No valid network fingerprint detected")
            return None

        return self.resolve(fingerprint)

    def resolve(self, fingerprint: NetworkFingerprint) -> Optional[str]:
        """
        Resolve network fingerprint to profile ID.
        
        Args:
            fingerprint: Network characteristics
            
        Returns:
            Profile ID or None if no mapping exists
        """
        network_key = fingerprint.primary_key
        
        if not network_key:
            logger.debug("No primary network key in fingerprint")
            return None

        # Find mapping for network
        mapping = self.mapping_repo.find_by_network(network_key)
        
        if not mapping:
            logger.debug(f"No mapping found for network: {network_key}")
            return None

        if not mapping.enabled:
            logger.debug(f"Mapping disabled for network: {network_key}")
            return None

        # Verify profile exists
        profile = self.profile_repo.get(mapping.profile_id)
        if not profile:
            logger.warning(
                f"Mapping points to non-existent profile: {mapping.profile_id}"
            )
            return None

        logger.info(
            f"Matched network '{network_key}' to profile '{profile.name}'",
            extra={"network_key": network_key, "profile_id": profile.id}
        )

        return profile.id

    def create_mapping(
        self, 
        network_key: str, 
        profile_id: str, 
        enabled: bool = True
    ) -> bool:
        """
        Create auto-switch mapping.
        
        Args:
            network_key: Network identifier (SSID, BSSID, or gateway MAC)
            profile_id: Profile ID to apply
            enabled: Enable mapping immediately
            
        Returns:
            True if created successfully
        """
        # Verify profile exists
        profile = self.profile_repo.get(profile_id)
        if not profile:
            logger.error(f"Cannot create mapping: profile not found: {profile_id}")
            return False

        # Check for existing mapping
        existing = self.mapping_repo.find_by_network(network_key)
        if existing:
            logger.warning(
                f"Mapping already exists for network: {network_key}, "
                f"updating to profile: {profile_id}"
            )
            existing.profile_id = profile_id
            existing.enabled = enabled
            self.mapping_repo.save(existing)
        else:
            # Create new mapping
            from quickip.domain.models import NetworkMapping
            import uuid
            
            mapping = NetworkMapping(
                id=str(uuid.uuid4()),
                network_key=network_key,
                profile_id=profile_id,
                enabled=enabled
            )
            self.mapping_repo.save(mapping)
            logger.info(f"Created mapping: {network_key} → {profile.name}")

        return True

    def remove_mapping(self, network_key: str) -> bool:
        """
        Remove auto-switch mapping.
        
        Args:
            network_key: Network identifier
            
        Returns:
            True if removed
        """
        mapping = self.mapping_repo.find_by_network(network_key)
        if not mapping:
            logger.warning(f"No mapping found to remove: {network_key}")
            return False

        self.mapping_repo.delete(mapping.id)
        logger.info(f"Removed mapping for network: {network_key}")
        return True

    def get_current_network_key(self) -> Optional[str]:
        """
        Get current network primary key.
        
        Returns:
            Network key (SSID or gateway MAC) or None
        """
        fingerprint = self.probe.get_current_network()
        return fingerprint.primary_key if fingerprint.is_valid else None
