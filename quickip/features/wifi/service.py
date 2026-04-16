"""Wi-Fi feature — WifiService.

All Wi-Fi adapter operations via netsh. Passwords are decrypted via the
DPAPI vault just before use and never persisted in plaintext.
"""

from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass
from typing import List, TYPE_CHECKING

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
        if result.stdout:
            if logger.isEnabledFor(logging.DEBUG):
                import re as _re
                rate_lines = [ln for ln in result.stdout.splitlines()
                              if _re.search(r"скорост|rates", ln, _re.IGNORECASE)]
                logger.debug("Rate lines sample: %s", rate_lines[:6])
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
        if profile.key_protected:
            if profile.key_protected == "kr:":
                from quickip.core.security.keyring_vault import unprotect_text as kr_unprotect
                password = kr_unprotect(ssid)
                logger.info("Secret source: keyring for SSID=%r", ssid)
            elif profile.key_protected.startswith("b64:"):
                # Legacy weak encoding — presenter should have migrated this already.
                # Log a warning and use it as a last resort so existing profiles
                # don't break before the user re-saves them.
                import base64
                logger.warning(
                    "SSID=%r uses legacy b64 encoding — re-save the profile to upgrade", ssid
                )
                password = base64.b64decode(profile.key_protected[4:]).decode()
            elif self._vault_available:
                from quickip.core.security.vault import unprotect_text
                password = unprotect_text(profile.key_protected)
                logger.info("Secret source: dpapi for SSID=%r", ssid)
            else:
                logger.warning("Vault unavailable for %s — trying Windows profile", ssid)

        # Если пароль не удалось получить — не трогаем Windows-профиль,
        # просто пробуем подключиться к существующему
        if not password and self._windows_profile_exists(ssid):
            logger.info("No password decrypted — using existing Windows profile for %s", ssid)
            return self._connect_by_name(ssid)

        add_result = self._add_profile_xml(ssid, profile, password)
        if not add_result.success:
            return add_result
        return self._connect_by_name(ssid)

    def connect_with_password(
        self, ssid: str, password: str,
        auth: str = "WPA2-Personal", cipher: str = "AES"
    ) -> ConnectResult:
        """Connect using a plaintext password — bypasses vault.
        Used when vault (pywin32) is unavailable or for one-off connections.
        """
        if len(password) < 8:
            return ConnectResult(
                success=False,
                message="Wi-Fi password must be at least 8 characters."
            )
        fake = WifiProfile(
            id="", ssid=ssid, auth=auth, cipher=cipher,
            key_protected="",
        )
        add_result = self._add_profile_xml(ssid, fake, password)
        if not add_result.success:
            return add_result
        return self._connect_by_name(ssid)

    def connect_open(self, ssid: str) -> ConnectResult:
        """Connect to an open (password-free) network.
        Если Windows уже знает этот профиль — просто подключаемся, не перезаписываем.
        """
        if self._windows_profile_exists(ssid):
            logger.info("Windows profile exists for %s — skipping XML add", ssid)
            return self._connect_by_name(ssid)
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

            # Удаляем существующий профиль чтобы наш XML точно применился
            self._runner.run(
                ["netsh", "wlan", "delete", "profile", f"name={ssid}"],
                timeout=10,
            )

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

        ok = result.success or "profile" in result.stdout.lower() or "профиль" in result.stdout.lower()
        if not ok:
            logger.error(f"add profile failed: stdout={result.stdout!r} stderr={result.stderr!r}")
        else:
            logger.info(f"Profile added for SSID={ssid!r}")
        return ConnectResult(success=ok, message=result.stdout.strip())

    def _windows_profile_exists(self, ssid: str) -> bool:
        """Проверяет есть ли профиль для SSID в системе Windows."""
        result = self._runner.run(
            ["netsh", "wlan", "show", "profile", f"name={ssid}"],
            timeout=10,
        )
        return result.success or "profile" in result.stdout.lower() or "профиль" in result.stdout.lower()

    def _connect_by_name(self, ssid: str) -> ConnectResult:
        cmd = ["netsh", "wlan", "connect", f"name={ssid}", f"ssid={ssid}"]
        iface = self._get_wifi_interface()
        if iface:
            cmd.append(f"interface={iface}")
        if logger.isEnabledFor(logging.DEBUG):
            # SSID redacted in logs — shown only at DEBUG level for diagnostics
            logger.debug("Connect cmd: netsh wlan connect name=*** ssid=***")
        result = self._runner.run(cmd, timeout=15)
        ok = result.success or "successfully" in result.stdout.lower() or "успешно" in result.stdout.lower()
        return ConnectResult(success=ok, message=result.stdout.strip())

    def _get_wifi_interface(self) -> str:
        """Возвращает имя первого активного Wi-Fi адаптера."""
        result = self._runner.run(["netsh", "wlan", "show", "interfaces"], timeout=10)
        if not result.stdout:
            return ""
        import re
        for line in result.stdout.splitlines():
            m = re.match(r"^\s*(?:Name|Имя)\s*:\s*(.+)$", line.strip(), re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return ""
