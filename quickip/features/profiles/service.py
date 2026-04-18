"""Profile feature service — apply, IP conflict check, adapter list."""

from __future__ import annotations

import json
import logging
import platform
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List

from quickip.domain.models import Profile, ApplyResult, ProfileHistoryEntry
from quickip.core.events.types import ProfileApplied, ProfileApplyFailed
from quickip.shared.net_utils import prefix_to_mask
from quickip.shared.ps_scripts import build_net_adapters_ps

if TYPE_CHECKING:
    from quickip.app.bootstrap import ServiceContainer

logger = logging.getLogger(__name__)

_PS_NET_ADAPTERS = build_net_adapters_ps(include_media=False)



class ProfileService:
    """Consolidates profile application and conflict detection for the profiles feature."""

    def __init__(self, container: "ServiceContainer") -> None:
        self._container = container

    # ── Apply ─────────────────────────────────────────────────────

    def apply(self, profile: Profile) -> ApplyResult:
        """Apply *profile* via netsh, record history, publish event."""
        logger.debug("Applying profile '%s' on %s", profile.name, profile.adapter)

        prev_config = self._container.netsh.get_adapter_config(profile.adapter)
        start = datetime.now()
        cmd_result = self._container.netsh.apply_profile(profile)
        duration_ms = int((datetime.now() - start).total_seconds() * 1000)
        new_config = self._container.netsh.get_adapter_config(profile.adapter)

        result = ApplyResult(
            success=cmd_result.success,
            message=cmd_result.stdout if cmd_result.success else cmd_result.stderr,
            duration_ms=duration_ms,
            profile_id=profile.id,
            profile_name=profile.name,
            adapter=profile.adapter,
            previous_config=prev_config,  # type: ignore[arg-type]
            new_config=new_config,  # type: ignore[arg-type]
            commands_executed=[cmd_result.command],
            error=cmd_result.stderr if not cmd_result.success else None,
        )

        # Record to history repository
        self._container.history_repo.append(
            ProfileHistoryEntry(  # type: ignore[arg-type]
                id=str(uuid.uuid4()),
                timestamp=start.isoformat(),
                profile_id=profile.id,
                profile_name=profile.name,
                adapter=profile.adapter,
                success=cmd_result.success,
                duration_ms=duration_ms,
                previous_config=prev_config,  # type: ignore[arg-type]
                new_config=new_config,  # type: ignore[arg-type]
                commands=[cmd_result.command],
                output=[cmd_result.stdout] if cmd_result.stdout else [],
                error_message=cmd_result.stderr if not cmd_result.success else "",
            )
        )

        bus = self._container.event_bus
        if cmd_result.success:
            logger.debug("Profile applied: %s", profile.name)
            bus.publish(ProfileApplied(  # type: ignore[arg-type]
                profile_id=profile.id,
                profile_name=profile.name,
                adapter=profile.adapter,
                result=result,
            ))
        else:
            logger.error("Profile apply failed: %s — %s", profile.name, cmd_result.stderr)
            bus.publish(ProfileApplyFailed(  # type: ignore[arg-type]
                profile_id=profile.id,
                profile_name=profile.name,
                adapter=profile.adapter,
                error=cmd_result.stderr,
            ))

        return result

    # ── Conflict check ────────────────────────────────────────────

    def is_ip_in_use(self, ip: str) -> bool:
        """Return True if *ip* responds to a fast ping (potential conflict)."""
        if platform.system().lower() == "windows":
            cmd = ["ping", "-n", "1", "-w", "500", ip]
        else:
            cmd = ["ping", "-c", "1", "-W", "1", ip]

        result = self._container.process_runner.run(cmd, timeout=5)
        in_use = result.success and self._ping_got_reply(result.stdout)
        logger.debug("IP conflict check %s: %s", ip, "in_use" if in_use else "free")
        return in_use

    @staticmethod
    def _ping_got_reply(output: str) -> bool:
        lower = output.lower()
        return "ttl=" in lower or "время" in lower or "time=" in lower

    # ── Adapters ─────────────────────────────────────────────────

    def get_adapters(self) -> List[str]:
        """Return list of available network adapter names."""
        try:
            return self._container.netsh.list_adapters()
        except Exception:
            logger.warning("Failed to list adapters, using defaults")
            return ["Ethernet", "Wi-Fi"]

    def get_adapters_detail(self) -> list:
        """Return detailed adapter info as a list of dicts for the 'Current Networks' tab."""
        result = self._container.process_runner.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS_NET_ADAPTERS],
            timeout=20,
        )
        if not result.success:
            logger.warning("get_adapters_detail failed: %s", result.stderr[:80])
            return []
        raw = result.stdout.strip()
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if isinstance(data, dict):
            data = [data]
        out = []
        for row in data:
            try:
                prefix = int(row.get("Prefix", 0) or 0)
                out.append({
                    "name":        str(row.get("Name", "")),
                    "description": str(row.get("Description", "")),
                    "status":      str(row.get("Status", "")),
                    "mac":         str(row.get("Mac", "")),
                    "speed":       str(row.get("Speed", "")),
                    "ipv4":        str(row.get("IPv4", "")),
                    "mask":        prefix_to_mask(prefix),
                    "ipv6":        str(row.get("IPv6", "")),
                    "gateway":     str(row.get("Gateway", "")),
                    "dns":         str(row.get("DNS", "")),
                    "dhcp":        str(row.get("DHCP", "")),
                })
            except Exception:
                continue
        return out
