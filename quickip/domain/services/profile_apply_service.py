"""Profile application service - core business logic."""

import logging
import uuid
from datetime import datetime
from typing import Optional

from quickip.domain.models import Profile, ApplyResult, ProfileHistoryEntry
from quickip.domain.interfaces import ProfileRepository, HistoryRepository
from quickip.infrastructure.system.netsh_client import NetshClient
from quickip.events.bus import EventBus
from quickip.events.event_types import ProfileApplied, ProfileApplyFailed


logger = logging.getLogger(__name__)


class ProfileApplyService:
    """Service for applying network profiles."""

    def __init__(
        self,
        profile_repo: ProfileRepository,
        history_repo: HistoryRepository,
        netsh_client: NetshClient,
        event_bus: EventBus
    ):
        """
        Initialize service.
        
        Args:
            profile_repo: Profile repository
            history_repo: History repository
            netsh_client: Network client
            event_bus: Event bus for notifications
        """
        self.profile_repo = profile_repo
        self.history_repo = history_repo
        self.netsh = netsh_client
        self.events = event_bus

    def apply(self, profile_id: str) -> ApplyResult:
        """
        Apply profile by ID.
        
        Args:
            profile_id: Profile ID to apply
            
        Returns:
            ApplyResult with execution details
        """
        # Get profile
        profile = self.profile_repo.get(profile_id)
        if not profile:
            error_msg = f"Profile not found: {profile_id}"
            logger.error(error_msg)
            return ApplyResult(
                success=False,
                message=error_msg,
                duration_ms=0,
                profile_id=profile_id,
                profile_name="",
                adapter="",
                error=error_msg
            )

        return self.apply_profile(profile)

    def apply_profile(self, profile: Profile) -> ApplyResult:
        """
        Apply profile object.
        
        Args:
            profile: Profile to apply
            
        Returns:
            ApplyResult with execution details
        """
        logger.info(
            f"Applying profile: {profile.name} on {profile.adapter}",
            extra={"profile_id": profile.id, "adapter": profile.adapter}
        )

        # Get current config for rollback
        previous_config = self.netsh.get_adapter_config(profile.adapter)

        # Apply profile
        start_time = datetime.now()
        result = self.netsh.apply_profile(profile)
        end_time = datetime.now()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        # Get new config
        new_config = self.netsh.get_adapter_config(profile.adapter)

        # Create result
        apply_result = ApplyResult(
            success=result.success,
            message=result.stdout if result.success else result.stderr,
            duration_ms=duration_ms,
            profile_id=profile.id,
            profile_name=profile.name,
            adapter=profile.adapter,
            previous_config=previous_config,
            new_config=new_config,
            commands_executed=[result.command],
            error=result.stderr if not result.success else None
        )

        # Record history
        history_entry = ProfileHistoryEntry(
            id=str(uuid.uuid4()),
            timestamp=start_time.isoformat(),
            profile_id=profile.id,
            profile_name=profile.name,
            adapter=profile.adapter,
            success=result.success,
            duration_ms=duration_ms,
            previous_config=previous_config,
            new_config=new_config,
            commands=[result.command],
            output=[result.stdout] if result.stdout else [],
            error_message=result.stderr if not result.success else ""
        )
        self.history_repo.append(history_entry)

        # Publish events
        if result.success:
            logger.info(f"Profile applied successfully: {profile.name}")
            self.events.publish(ProfileApplied(
                profile_id=profile.id,
                profile_name=profile.name,
                adapter=profile.adapter,
                result=apply_result
            ))
        else:
            logger.error(f"Profile application failed: {profile.name}")
            self.events.publish(ProfileApplyFailed(
                profile_id=profile.id,
                profile_name=profile.name,
                adapter=profile.adapter,
                error=result.stderr
            ))

        return apply_result

    def rollback(self, history_entry_id: str) -> ApplyResult:
        """
        Rollback to previous configuration from history.
        
        Args:
            history_entry_id: History entry ID to rollback to
            
        Returns:
            ApplyResult from applying previous config
        """
        entry = self.history_repo.get(history_entry_id)
        if not entry:
            error_msg = f"History entry not found: {history_entry_id}"
            logger.error(error_msg)
            return ApplyResult(
                success=False,
                message=error_msg,
                duration_ms=0,
                profile_id="",
                profile_name="",
                adapter="",
                error=error_msg
            )

        if not entry.previous_config:
            error_msg = "No previous configuration to rollback to"
            logger.error(error_msg)
            return ApplyResult(
                success=False,
                message=error_msg,
                duration_ms=0,
                profile_id=entry.profile_id,
                profile_name=entry.profile_name,
                adapter=entry.adapter,
                error=error_msg
            )

        # Create temporary profile from previous config
        prev = entry.previous_config
        rollback_profile = Profile(
            id=str(uuid.uuid4()),
            name=f"Rollback from {entry.profile_name}",
            adapter=entry.adapter,
            ip_mode="dhcp" if prev.dhcp_enabled else "static",
            ipv4=prev.ip,
            mask=prev.mask,
            gateway=prev.gateway,
            dns_primary=prev.dns_servers[0] if prev.dns_servers else "",
            dns_secondary=prev.dns_servers[1] if len(prev.dns_servers) > 1 else ""
        )

        logger.info(f"Rolling back to configuration from {entry.timestamp}")
        return self.apply_profile(rollback_profile)
