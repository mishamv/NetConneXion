"""Windows netsh client for network configuration."""

import logging
import re
from typing import List, Optional
from quickip.domain.models import Profile, CommandResult, AdapterConfig
from quickip.infrastructure.system.process_runner import ProcessRunner


logger = logging.getLogger(__name__)


class NetshClient:
    """Client for Windows netsh network operations."""

    def __init__(self, process_runner: Optional[ProcessRunner] = None):
        """
        Initialize netsh client.
        
        Args:
            process_runner: ProcessRunner instance (None = create new)
        """
        self.runner = process_runner or ProcessRunner()

    def list_adapters(self) -> List[str]:
        """
        Get list of network adapter names.
        
        Returns:
            List of adapter names
        """
        result = self.runner.run(["netsh", "interface", "show", "interface"])
        
        if not result.success:
            logger.error(f"Failed to list adapters: {result.stderr}")
            return []

        adapters = self._parse_adapter_list(result.stdout)
        logger.debug(f"Found {len(adapters)} network adapters")
        return adapters

    def _parse_adapter_list(self, output: str) -> List[str]:
        """Parse netsh interface list output."""
        adapters = []
        
        for line in output.splitlines():
            line = line.strip()
            if not line or set(line) == {'-'}:
                continue

            lowered = line.lower()
            # Skip headers
            if "interface name" in lowered or "имя интерфейса" in lowered:
                continue
            if lowered.startswith("admin state") or lowered.startswith("состояние"):
                continue

            # Parse line with multiple spaces as separator
            parts = re.split(r'\s{2,}', line)
            if len(parts) >= 4 and parts[-1]:
                adapters.append(parts[-1])

        # Remove duplicates while preserving order
        seen = set()
        unique_adapters = []
        for adapter in adapters:
            if adapter.lower() not in seen:
                seen.add(adapter.lower())
                unique_adapters.append(adapter)

        return unique_adapters

    def get_adapter_config(self, adapter: str) -> Optional[AdapterConfig]:
        """
        Get current configuration for adapter.
        
        Args:
            adapter: Adapter name
            
        Returns:
            AdapterConfig or None if failed
        """
        result = self.runner.run(
            ["netsh", "interface", "ipv4", "show", "config", f'name="{adapter}"']
        )

        if not result.success:
            logger.error(f"Failed to get adapter config: {result.stderr}")
            return None

        return self._parse_adapter_config(adapter, result.stdout)

    def _parse_adapter_config(self, adapter: str, output: str) -> Optional[AdapterConfig]:
        """Parse adapter configuration from netsh output."""
        config = AdapterConfig(adapter=adapter, ip="", mask="", gateway="")
        
        lines = output.splitlines()
        for line in lines:
            line = line.strip().lower()
            
            # Check DHCP status
            if "dhcp" in line and "enabled" in line:
                config.dhcp_enabled = True
            
            # Extract IP address
            if "ip address" in line or "ip-адрес" in line:
                parts = line.split(":")
                if len(parts) > 1:
                    config.ip = parts[1].strip()
            
            # Extract subnet mask
            if "subnet prefix" in line or "маска подсети" in line:
                parts = line.split(":")
                if len(parts) > 1:
                    mask_part = parts[1].strip()
                    # Extract mask from format "255.255.255.0/24" or just mask
                    config.mask = mask_part.split('/')[0].strip()
            
            # Extract gateway
            if "default gateway" in line or "основной шлюз" in line:
                parts = line.split(":")
                if len(parts) > 1:
                    config.gateway = parts[1].strip()
            
            # Extract DNS
            if "dns" in line and "server" in line:
                parts = line.split(":")
                if len(parts) > 1:
                    dns = parts[1].strip()
                    if dns:
                        config.dns_servers.append(dns)

        return config

    def apply_profile(self, profile: Profile) -> CommandResult:
        """
        Apply network profile configuration.
        
        Args:
            profile: Profile to apply
            
        Returns:
            CommandResult with execution details
        """
        commands = self._build_commands(profile)
        all_output = []
        all_errors = []
        total_duration = 0

        for cmd in commands:
            result = self.runner.run(cmd)
            total_duration += result.duration_ms
            
            if result.stdout:
                all_output.append(result.stdout)
            if result.stderr:
                all_errors.append(result.stderr)
            
            if not result.success:
                error_msg = f"Command failed: {' '.join(cmd)}\n{result.stderr}"
                logger.error(error_msg)
                
                return CommandResult(
                    success=False,
                    stdout='\n'.join(all_output),
                    stderr=error_msg,
                    exit_code=result.exit_code,
                    duration_ms=total_duration,
                    command='; '.join([' '.join(c) for c in commands])
                )

        return CommandResult(
            success=True,
            stdout='\n'.join(all_output),
            stderr='\n'.join(all_errors),
            exit_code=0,
            duration_ms=total_duration,
            command='; '.join([' '.join(c) for c in commands])
        )

    def _build_commands(self, profile: Profile) -> List[List[str]]:
        """Build netsh commands for profile application."""
        commands = []
        adapter = profile.adapter

        # IP configuration
        if profile.is_dhcp_ip:
            commands.append([
                "netsh", "interface", "ipv4", "set", "address",
                f'name="{adapter}"', "source=dhcp"
            ])
        else:
            if profile.gateway:
                commands.append([
                    "netsh", "interface", "ipv4", "set", "address",
                    f'name="{adapter}"', "source=static",
                    f"address={profile.ipv4}",
                    f"mask={profile.mask}",
                    f"gateway={profile.gateway}",
                    "gwmetric=1"
                ])
            else:
                commands.append([
                    "netsh", "interface", "ipv4", "set", "address",
                    f'name="{adapter}"', "source=static",
                    f"address={profile.ipv4}",
                    f"mask={profile.mask}",
                    "gateway=none"
                ])

        # DNS configuration
        if profile.is_dhcp_dns:
            commands.append([
                "netsh", "interface", "ipv4", "set", "dnsservers",
                f'name="{adapter}"', "source=dhcp"
            ])
        else:
            if profile.dns_primary:
                commands.append([
                    "netsh", "interface", "ipv4", "set", "dnsservers",
                    f'name="{adapter}"', "source=static",
                    f"address={profile.dns_primary}",
                    "register=primary", "validate=no"
                ])
                
                if profile.dns_secondary:
                    commands.append([
                        "netsh", "interface", "ipv4", "add", "dnsservers",
                        f'name="{adapter}"',
                        f"address={profile.dns_secondary}",
                        "index=2", "validate=no"
                    ])

        return commands

    def get_network_snapshot(self) -> str:
        """
        Get complete network configuration snapshot.
        
        Returns:
            Formatted network configuration text
        """
        parts = []

        # ipconfig /all
        result1 = self.runner.run(["ipconfig", "/all"])
        if result1.success:
            parts.append("=== ipconfig /all ===")
            parts.append(result1.stdout)
        else:
            parts.append(f"ipconfig failed: {result1.stderr}")

        # netsh interface ipv4 show config
        result2 = self.runner.run(["netsh", "interface", "ipv4", "show", "config"])
        if result2.success:
            parts.append("\n=== netsh interface ipv4 show config ===")
            parts.append(result2.stdout)
        else:
            parts.append(f"netsh config failed: {result2.stderr}")

        return '\n'.join(parts)
