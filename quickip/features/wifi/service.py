"""Wi-Fi feature — WifiService.

All Wi-Fi adapter operations via netsh. Passwords are decrypted via the
DPAPI vault just before use and never persisted in plaintext.
"""

from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass
from typing import List, Optional, TYPE_CHECKING

from quickip.features.wifi.netsh_parser import (
    WifiNetworkSnapshot,
    parse_networks, parse_interface_status, parse_saved_profiles,
)
from quickip.features.wifi.repository import WifiProfile
from quickip.features.wifi.xml_builder import build_profile_xml

if TYPE_CHECKING:
    from quickip.app.bootstrap import ServiceContainer

logger = logging.getLogger(__name__)


@dataclass
class ConnectResult:
    success: bool
    message: str


class WifiService:
    """High-level Wi-Fi operations via netsh."""

    def __init__(self, container: "ServiceContainer") -> None:
        self._runner = container.process_runner
        self._vault_available = container.vault_available

    # ── Scanning ──────────────────────────────────────────────────

    def scan_networks(self) -> List[WifiNetworkSnapshot]:
        """Trigger a rescan then return visible networks."""
        self._runner.run(["netsh", "wlan", "scan"], timeout=8)
        result = self._runner.run(
            ["netsh", "wlan", "show", "networks", "mode=bssid"],
            timeout=15,
        )
        return parse_networks(result.stdout) if result.stdout else []

    def get_interface_status(self) -> dict:
        """Return dict with keys: name, state, ssid, signal, auth, channel."""
        result = self._runner.run(
            ["netsh", "wlan", "show", "interfaces"],
            timeout=10,
        )
        return parse_interface_status(result.stdout) if result.stdout else {}

    def get_saved_netsh_profiles(self) -> List[str]:
        """Return WLAN profile names currently stored in Windows."""
        result = self._runner.run(["netsh", "wlan", "show", "profiles"], timeout=10)
        return parse_saved_profiles(result.stdout) if result.success else []

    # ── Connect / Disconnect ──────────────────────────────────────

    def connect(self, ssid: str, profile: WifiProfile) -> ConnectResult:
        """Connect using a WifiProfile.

        Decrypts the PSK via DPAPI vault, builds a WLAN XML profile,
        registers it with netsh, connects, then deletes the temp file.
        Raises quickip.core.security.vault.VaultPortabilityError if the
        password was encrypted on a different machine/user.
        """
        password = ""
        if profile.key_protected and self._vault_available:
            from quickip.core.security.vault import unprotect_text
            password = unprotect_text(profile.key_protected)
        elif profile.key_protected and not self._vault_available:
            logger.warning("Vault unavailable — connecting without password for %s", ssid)

        add_result = self._add_profile_xml(ssid, profile, password)
        if not add_result.success:
            return add_result
        return self._connect_by_name(ssid)

    def connect_open(self, ssid: str) -> ConnectResult:
        """Connect to an open (password-free) network."""
        fake = WifiProfile(id="", ssid=ssid, auth="Open", cipher="None",
                           key_protected="")
        add_result = self._add_profile_xml(ssid, fake, "")
        if not add_result.success:
            return add_result
        return self._connect_by_name(ssid)

    def disconnect(self) -> ConnectResult:
        result = self._runner.run(["netsh", "wlan", "disconnect"], timeout=10)
        ok = result.success or "successfully" in result.stdout.lower()
        return ConnectResult(success=ok, message=result.stdout.strip())

    def delete_netsh_profile(self, ssid: str) -> ConnectResult:
        result = self._runner.run(
            ["netsh", "wlan", "delete", "profile", f"name={ssid}"],
            timeout=10,
        )
        ok = result.success or "deleted" in result.stdout.lower()
        return ConnectResult(success=ok, message=result.stdout.strip())

    # ── Internal ──────────────────────────────────────────────────

    def _add_profile_xml(
        self, ssid: str, profile: WifiProfile, password: str
    ) -> ConnectResult:
        xml_content = build_profile_xml(
            ssid=ssid,
            auth=profile.auth,
            cipher=profile.cipher,
            password=password,
            auto_connect=profile.auto_connect,
            connect_hidden=profile.connect_hidden,
            is_adhoc=profile.is_adhoc,
        )
        tmp_path = None
        try:
            fd, tmp_path = tempfile.mkstemp(suffix=".xml", prefix="quickip_wifi_")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(xml_content)

            result = self._runner.run(
                ["netsh", "wlan", "add", "profile",
                 f"filename={tmp_path}", "user=all"],
                timeout=15,
            )
            if not result.success:
                result = self._runner.run(
                    ["netsh", "wlan", "add", "profile", f"filename={tmp_path}"],
                    timeout=15,
                )
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

        ok = result.success or "profile" in result.stdout.lower()
        return ConnectResult(success=ok, message=result.stdout.strip())

    def _connect_by_name(self, ssid: str) -> ConnectResult:
        result = self._runner.run(
            ["netsh", "wlan", "connect", f"name={ssid}", f"ssid={ssid}"],
            timeout=15,
        )
        ok = result.success or "successfully" in result.stdout.lower()
        return ConnectResult(success=ok, message=result.stdout.strip())
