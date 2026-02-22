"""Tools feature — adapters service.

Fetches detailed network adapter information using PowerShell
(Get-NetAdapter + Get-NetIPAddress + Get-NetRoute + Get-DnsClientServerAddress).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from quickip.core.system.process_runner import ProcessRunner

logger = logging.getLogger(__name__)

# ── PowerShell query ───────────────────────────────────────────────────────────

_PS_ADAPTERS = (
    "$adapters = Get-NetAdapter | Select-Object Name,InterfaceDescription,"
    "Status,MacAddress,LinkSpeed,MediaType,InterfaceIndex;"
    "$ips = Get-NetIPAddress | Select-Object InterfaceIndex,IPAddress,"
    "PrefixLength,AddressFamily,PrefixOrigin;"
    "$gws = Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue"
    " | Select-Object InterfaceIndex,NextHop;"
    "$dns_map = @{};"
    "(Get-DnsClientServerAddress -ErrorAction SilentlyContinue) | ForEach-Object {"
    "  $dns_map[$_.InterfaceIndex] = $_.ServerAddresses -join ', '};"
    "$result = foreach ($a in $adapters) {"
    "  $idx = $a.InterfaceIndex;"
    "  $ip4 = ($ips | Where-Object {"
    "    $_.InterfaceIndex -eq $idx -and $_.AddressFamily -eq 2} | Select-Object -First 1);"
    "  $ip6 = ($ips | Where-Object {"
    "    $_.InterfaceIndex -eq $idx -and $_.AddressFamily -eq 23} | Select-Object -First 1);"
    "  $gw = ($gws | Where-Object {$_.InterfaceIndex -eq $idx} | Select-Object -First 1);"
    "  [PSCustomObject]@{"
    "    Name=$a.Name; Description=$a.InterfaceDescription; Status=$a.Status;"
    "    Mac=$a.MacAddress; Speed=$a.LinkSpeed; Media=$a.MediaType;"
    "    IPv4=if($ip4){$ip4.IPAddress}else{''};"
    "    Prefix=if($ip4){$ip4.PrefixLength}else{0};"
    "    IPv6=if($ip6){$ip6.IPAddress}else{''};"
    "    Gateway=if($gw){$gw.NextHop}else{''};"
    "    DNS=if($dns_map[$idx]){$dns_map[$idx]}else{''};"
    "    DHCP=if($ip4){$ip4.PrefixOrigin}else{''}}};"
    "$result | ConvertTo-Json -Compress"
)


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
        """Convert CIDR prefix length to dotted-decimal subnet mask."""
        pl = self.prefix_length
        if not (0 <= pl <= 32):
            return ""
        mask = (0xFFFFFFFF << (32 - pl)) & 0xFFFFFFFF
        return ".".join(str((mask >> (8 * i)) & 0xFF) for i in reversed(range(4)))

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
