"""Tools feature — adapters service.

Fetches detailed network adapter information using PowerShell
(Get-NetAdapter + Get-NetIPAddress + Get-NetRoute + Get-DnsClientServerAddress).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import List, TYPE_CHECKING

from quickip.shared.net_utils import prefix_to_mask

if TYPE_CHECKING:
    from quickip.infrastructure.system.process_runner import ProcessRunner

from quickip.shared.ps_scripts import build_net_adapters_ps

logger = logging.getLogger(__name__)

_PS_ADAPTERS = build_net_adapters_ps(include_media=True)


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class AdapterDetail:
    name: str
    description: str
    status: str           # "Up", "Down", "Disconnected", …
    mac: str
    speed: str            # e.g. "1 Gbps"
    media: str            # e.g. "802.3"
    ipv4: str
    prefix_length: int    # CIDR prefix, e.g. 24
    ipv6: str
    gateway: str
    dns: str              # comma-separated DNS servers
    dhcp: str             # "Dhcp" or "Manual"

    @property
    def subnet_mask(self) -> str:
        return prefix_to_mask(self.prefix_length)

    @property
    def is_up(self) -> bool:
        return self.status.lower() == "up"

    @property
    def is_dhcp(self) -> bool:
        return self.dhcp.lower() == "dhcp"


# ── Service ───────────────────────────────────────────────────────────────────

class AdaptersService:
    """Fetches detailed information for all network adapters."""

    def __init__(self, process_runner: "ProcessRunner") -> None:
        self._runner = process_runner

    def fetch(self) -> List[AdapterDetail]:
        """Return an AdapterDetail entry for every network adapter."""
        result = self._runner.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS_ADAPTERS],
            timeout=20,
        )
        if not result.success:
            logger.warning("AdaptersService.fetch failed: %s", result.stderr[:120])
            return []
        return self._parse(result.stdout)

    @staticmethod
    def _parse(raw: str) -> List[AdapterDetail]:
        raw = raw.strip()
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.debug("AdaptersService JSON parse error")
            return []
        if isinstance(data, dict):
            data = [data]
        out: List[AdapterDetail] = []
        for row in data:
            try:
                out.append(AdapterDetail(
                    name=str(row.get("Name", "")),
                    description=str(row.get("Description", "")),
                    status=str(row.get("Status", "")),
                    mac=str(row.get("Mac", "")),
                    speed=str(row.get("Speed", "")),
                    media=str(row.get("Media", "")),
                    ipv4=str(row.get("IPv4", "")),
                    prefix_length=int(row.get("Prefix", 0) or 0),
                    ipv6=str(row.get("IPv6", "")),
                    gateway=str(row.get("Gateway", "")),
                    dns=str(row.get("DNS", "")),
                    dhcp=str(row.get("DHCP", "")),
                ))
            except Exception:
                continue
        return out
