"""Network detection service for auto-switching."""

import logging
import re
from typing import Optional
from quickip.domain.models import NetworkFingerprint
from quickip.infrastructure.system.process_runner import ProcessRunner


logger = logging.getLogger(__name__)


class NetworkProbe:
    """Detect current network characteristics for auto-switching."""

    def __init__(self, process_runner: Optional[ProcessRunner] = None):
        """
        Initialize network probe.
        
        Args:
            process_runner: ProcessRunner instance (None = create new)
        """
        self.runner = process_runner or ProcessRunner()

    def get_current_network(self) -> NetworkFingerprint:
        """
        Get current network fingerprint.
        
        Returns:
            NetworkFingerprint with available network data
        """
        fingerprint = NetworkFingerprint()

        # Get Wi-Fi SSID and BSSID
        wifi_info = self._get_wifi_info()
        if wifi_info:
            fingerprint.ssid = wifi_info.get('ssid', '')
            fingerprint.bssid = wifi_info.get('bssid', '')

        # Get default gateway
        gateway_info = self._get_gateway_info()
        if gateway_info:
            fingerprint.gateway_ip = gateway_info.get('ip', '')
            fingerprint.gateway_mac = gateway_info.get('mac', '')
            fingerprint.adapter_name = gateway_info.get('adapter', '')

        logger.debug(f"Network fingerprint: {fingerprint}")
        return fingerprint

    def _get_wifi_info(self) -> Optional[dict]:
        """
        Get current Wi-Fi SSID and BSSID.
        
        Returns:
            Dict with 'ssid' and 'bssid' or None
        """
        result = self.runner.run(["netsh", "wlan", "show", "interfaces"])
        
        if not result.success:
            logger.debug("No Wi-Fi interface or not connected")
            return None

        info = {}
        for line in result.stdout.splitlines():
            line = line.strip()
            
            # Extract SSID (avoid BSSID line)
            if "SSID" in line and "BSSID" not in line:
                parts = line.split(":", 1)
                if len(parts) == 2:
                    info['ssid'] = parts[1].strip()
            
            # Extract BSSID
            elif "BSSID" in line:
                parts = line.split(":", 1)
                if len(parts) == 2:
                    # BSSID format: aa:bb:cc:dd:ee:ff
                    bssid_parts = parts[1].strip().split(":")
                    if len(bssid_parts) >= 6:
                        info['bssid'] = parts[1].strip()

        return info if info else None

    def _get_gateway_info(self) -> Optional[dict]:
        """
        Get default gateway IP and MAC address.
        
        Returns:
            Dict with 'ip', 'mac', and 'adapter' or None
        """
        # Get default gateway IP from route
        gateway_ip = self._get_default_gateway_ip()
        if not gateway_ip:
            return None

        # Get MAC address from ARP table
        gateway_mac = self._get_mac_from_arp(gateway_ip)

        return {
            'ip': gateway_ip,
            'mac': gateway_mac or '',
            'adapter': ''  # Could be enhanced to detect adapter
        }

    def _get_default_gateway_ip(self) -> Optional[str]:
        """Get default gateway IP address."""
        result = self.runner.run(["route", "print", "0.0.0.0"])
        
        if not result.success:
            return None

        # Parse route table for default gateway
        # Looking for line like: "0.0.0.0  0.0.0.0  192.168.1.1  ..."
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("0.0.0.0"):
                parts = line.split()
                if len(parts) >= 3:
                    # Third column is gateway
                    gateway = parts[2]
                    if self._is_valid_ip(gateway):
                        logger.debug(f"Default gateway: {gateway}")
                        return gateway

        return None

    def _get_mac_from_arp(self, ip: str) -> Optional[str]:
        """Get MAC address for IP from ARP table."""
        result = self.runner.run(["arp", "-a", ip])
        
        if not result.success:
            return None

        # Parse ARP output
        # Format: "192.168.1.1  aa-bb-cc-dd-ee-ff  dynamic"
        for line in result.stdout.splitlines():
            if ip in line:
                # Look for MAC address pattern
                mac_match = re.search(r'([0-9a-fA-F]{2}[-:]){5}[0-9a-fA-F]{2}', line)
                if mac_match:
                    mac = mac_match.group(0)
                    # Normalize to colon format
                    mac = mac.replace('-', ':').upper()
                    logger.debug(f"Gateway MAC: {mac}")
                    return mac

        return None

    def _is_valid_ip(self, ip: str) -> bool:
        """Check if string is valid IPv4 address."""
        parts = ip.split('.')
        if len(parts) != 4:
            return False
        
        try:
            return all(0 <= int(p) <= 255 for p in parts)
        except ValueError:
            return False

    def get_wifi_ssid(self) -> str:
        """
        Get current Wi-Fi SSID only (convenience method).
        
        Returns:
            SSID string or empty string if not connected
        """
        wifi_info = self._get_wifi_info()
        return wifi_info.get('ssid', '') if wifi_info else ''
