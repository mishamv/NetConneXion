"""Core netsh client — network adapter configuration via netsh.

Provides:
  NetshClient.list_adapters()           → List[str]
  NetshClient.get_adapter_config(name)  → Optional[AdapterConfig]
  NetshClient.apply_profile(profile)    → CommandResult
"""

from __future__ import annotations

import json
import logging
import re
from typing import List, Optional, TYPE_CHECKING

from quickip.core.models import AdapterConfig, CommandResult, Profile, IPMode, DNSMode

if TYPE_CHECKING:
    from quickip.core.system.process_runner import ProcessRunner

logger = logging.getLogger(__name__)


class NetshClient:
    """Wraps netsh commands for adapter configuration."""

    def __init__(self, runner: "ProcessRunner") -> None:
        self._runner = runner

    # ── Adapter discovery ─────────────────────────────────────────

    def list_adapters(self) -> List[str]:
        """Return names of all network adapters (locale-independent via PowerShell)."""
        ps = self._runner.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "Get-NetAdapter | Select-Object -ExpandProperty Name | ConvertTo-Json -Compress"],
            timeout=10,
        )
        if ps.success and ps.stdout.strip():
            try:
                data = json.loads(ps.stdout.strip())
                if isinstance(data, str):
                    names = [data]
                else:
                    names = [str(n) for n in data if n]
                if names:
                    return names
            except Exception:
                pass

        # Fallback: netsh (English locale)
        result = self._runner.run(
            ["netsh", "interface", "show", "interface"],
            timeout=8,
        )
        adapters: List[str] = []
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 4 and parts[0] in ("Enabled", "Disabled"):
                name = " ".join(parts[3:])
                if name:
                    adapters.append(name)
        return adapters if adapters else ["Ethernet", "Wi-Fi"]

    # ── Read current config ───────────────────────────────────────

    def get_adapter_config(self, adapter: str) -> Optional[AdapterConfig]:
        """Read current IP/DNS configuration for *adapter*."""
        result = self._runner.run(
            ["netsh", "interface", "ip", "show", "address", adapter],
            timeout=8,
        )
        if not result.stdout:
            return None
        try:
            return self._parse_address(adapter, result.stdout)
        except Exception as exc:
            logger.debug("get_adapter_config parse error: %s", exc)
            return None

    @staticmethod
    def _parse_address(adapter: str, raw: str) -> AdapterConfig:
        dhcp = "dhcp enabled:                         yes" in raw.lower()
        ip = mask = gateway = ""
        dns: List[str] = []

        for line in raw.splitlines():
            line = line.strip()
            lo = line.lower()
            if lo.startswith("ip address:"):
                ip = line.split(":", 1)[-1].strip()
            elif "subnet prefix:" in lo:
                m = re.search(r"mask\s+([\d.]+)", line, re.IGNORECASE)
                if m:
                    mask = m.group(1)
            elif lo.startswith("default gateway:"):
                gateway = line.split(":", 1)[-1].strip()
            elif "dns server:" in lo or "statically configured dns" in lo:
                addr = line.split(":", 1)[-1].strip()
                if addr:
                    dns.append(addr)

        return AdapterConfig(
            adapter=adapter,
            ip=ip,
            mask=mask,
            gateway=gateway,
            dns_servers=dns,
            dhcp_enabled=dhcp,
        )

    # ── Apply profile ─────────────────────────────────────────────

    def apply_profile(self, profile: Profile) -> CommandResult:
        """Apply IP and DNS settings from *profile* via netsh."""
        if profile.ip_mode == IPMode.DHCP:
            return self._set_dhcp(profile.adapter)
        return self._set_static(profile)

    def _set_dhcp(self, adapter: str) -> CommandResult:
        r1 = self._runner.run(
            ["netsh", "interface", "ip", "set", "address", adapter, "dhcp"],
            timeout=15,
        )
        r2 = self._runner.run(
            ["netsh", "interface", "ip", "set", "dns", adapter, "dhcp"],
            timeout=15,
        )
        ok = r1.success or r2.success
        return CommandResult(
            success=ok,
            stdout=r1.stdout + "\n" + r2.stdout,
            stderr=r1.stderr + "\n" + r2.stderr,
            exit_code=0 if ok else 1,
            duration_ms=r1.duration_ms + r2.duration_ms,
            command=f"set address {adapter} dhcp",
        )

    def _set_static(self, profile: Profile) -> CommandResult:
        # Set static IP + gateway
        cmd_ip = [
            "netsh", "interface", "ip", "set", "address",
            profile.adapter, "static",
            profile.ipv4, profile.mask, profile.gateway,
        ]
        r_ip = self._runner.run(cmd_ip, timeout=15)

        # DNS
        if profile.dns_mode == DNSMode.DHCP:
            r_dns = self._runner.run(
                ["netsh", "interface", "ip", "set", "dns", profile.adapter, "dhcp"],
                timeout=10,
            )
        else:
            r_dns = self._runner.run(
                ["netsh", "interface", "ip", "set", "dns",
                 profile.adapter, "static", profile.dns_primary],
                timeout=10,
            )
            if profile.dns_secondary:
                self._runner.run(
                    ["netsh", "interface", "ip", "add", "dns",
                     profile.adapter, profile.dns_secondary, "index=2"],
                    timeout=10,
                )

        ok = r_ip.success
        return CommandResult(
            success=ok,
            stdout=r_ip.stdout + "\n" + r_dns.stdout,
            stderr=r_ip.stderr + "\n" + r_dns.stderr,
            exit_code=0 if ok else r_ip.exit_code,
            duration_ms=r_ip.duration_ms + r_dns.duration_ms,
            command=f"set address {profile.adapter} static {profile.ipv4}",
        )
