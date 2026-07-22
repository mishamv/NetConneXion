"""Wi-Fi feature — WifiService.

All Wi-Fi adapter operations via netsh. Passwords are decrypted via the
DPAPI vault just before use and never persisted in plaintext.
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
import threading
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
    # True when DPAPI blob was encrypted by a different Windows account
    # (VaultPortabilityError). UI should prompt the user to re-enter the
    # password and call WifiPresenter.reauth_connect() to reconnect and
    # re-save the profile under the current account's vault.
    needs_reauth: bool = False


class WifiService:
    """High-level Wi-Fi operations via netsh."""

    def __init__(self, container: "ServiceContainer") -> None:
        self._runner = container.process_runner
        self._vault_available = container.vault_available
        # Debounce: не запускать параллельные сканы при быстрых нажатиях «Refresh»
        self._scan_lock = threading.Lock()
        # Кеш последнего успешного скана — возвращается при повторном вызове
        # пока предыдущий скан ещё выполняется (вместо пустого [])
        self._last_scan_result: List[WifiNetworkSnapshot] = []

    # ── Scanning ──────────────────────────────────────────────────

    def scan_networks(self) -> List[WifiNetworkSnapshot]:
        """Trigger a rescan then return visible networks.

        Защищён Lock: если скан уже выполняется (быстрые повторные нажатия Refresh),
        возвращает последний кешированный результат вместо пустого списка —
        иначе UI очищал таблицу при каждом повторном нажатии Refresh.
        """
        if not self._scan_lock.acquire(blocking=False):
            logger.debug("scan_networks: scan in progress — returning cached result (%d networks)",
                         len(self._last_scan_result))
            return list(self._last_scan_result)  # копия, не ссылка
        try:
            self._runner.run(["netsh", "wlan", "scan"], timeout=8)
            result = self._runner.run(
                ["netsh", "wlan", "show", "networks", "mode=bssid"],
                timeout=15,
            )
            if result.stdout:
                if logger.isEnabledFor(logging.DEBUG):
                    rate_lines = [ln for ln in result.stdout.splitlines()
                                  if re.search(r"скорост|rates", ln, re.IGNORECASE)]
                    logger.debug("Rate lines sample: %s", rate_lines[:6])
            networks = parse_networks(result.stdout) if result.stdout else []
            self._last_scan_result = networks  # обновляем кеш
            return networks
        finally:
            self._scan_lock.release()

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

    @staticmethod
    def _validate_ssid(ssid: str) -> None:
        """Raise ValueError for invalid SSIDs (IEEE 802.11 §7.3.2.1).

        Rules:
        - 1–32 bytes when UTF-8 encoded (802.11 max SSID length)
        - No control characters (< 0x20)
        - No double-quote (") — prevents f-string injection in netsh name=
        """
        if not ssid:
            raise ValueError("SSID must not be empty")
        encoded = ssid.encode("utf-8")
        if len(encoded) > 32:
            raise ValueError(
                f"SSID '{ssid!r}' exceeds 32 bytes (IEEE 802.11 limit): "
                f"{len(encoded)} bytes"
            )
        if any(b < 0x20 for b in encoded):
            raise ValueError(
                f"SSID '{ssid!r}' contains control characters (< 0x20)"
            )
        if '"' in ssid:
            raise ValueError(
                f"SSID '{ssid!r}' contains a double-quote character"
            )

    def connect(self, ssid: str, profile: WifiProfile) -> ConnectResult:
        """Connect using a WifiProfile.

        Decrypts the PSK via DPAPI vault, builds a WLAN XML profile,
        registers it with netsh, connects, then deletes the temp file.
        Raises quickip.core.security.vault.VaultPortabilityError if the
        password was encrypted on a different machine/user.
        """
        self._validate_ssid(ssid)
        password = ""
        if profile.key_protected:
            if profile.key_protected.startswith("kr:"):
                _kr_suffix = profile.key_protected[3:]   # "" → legacy, uuid → v2
                if _kr_suffix:
                    # v2: kr:<profile_uuid> — lookup by UUID
                    from quickip.core.security.keyring_vault import unprotect_text as kr_unprotect
                    password = kr_unprotect(_kr_suffix)
                    logger.info("Secret source: keyring(v2) for profile_id=%r", _kr_suffix)
                else:
                    # v1 legacy: kr: — lookup by SSID, auto-migrate on success
                    from quickip.core.security.keyring_vault import (
                        unprotect_legacy as _kr_legacy,
                        migrate_legacy_kr as _kr_migrate,
                    )
                    password = _kr_legacy(ssid)
                    logger.warning(
                        "keyring v1 sentinel 'kr:' for SSID=%r — auto-migrating to kr:<uuid>",
                        ssid,
                    )
                    # Миграция best-effort: обновляем sentinel в repo
                    new_sentinel = _kr_migrate(ssid, profile.id)
                    if new_sentinel:
                        profile.key_protected = new_sentinel
                        # Сохраняем обновлённый профиль — требуется repo, но у сервиса
                        # нет прямого доступа к нему. Профиль будет мигрирован
                        # в presenter при следующем save_profile().
                        logger.info("Keyring v1→v2 migration staged for SSID=%r", ssid)
            elif profile.key_protected.startswith("b64:"):
                # SECURITY: base64 — не шифрование. Тихий fallback удалён (T1552.001).
                # Миграция должна выполняться в WifiPresenter.connect() до вызова сервиса.
                # Если сюда всё же попал b64-профиль — отклоняем подключение.
                msg = (
                    f"SSID {ssid!r}: профиль использует небезопасное хранение пароля (b64). "
                    "Пересохраните профиль в настройках Wi-Fi → вкладка «Профили»."
                )
                logger.error("Blocked b64 connect attempt for SSID=%r — require re-save", ssid)
                return ConnectResult(success=False, message=msg)
            elif self._vault_available:
                from quickip.core.security.vault import unprotect_text, VaultPortabilityError
                try:
                    password = unprotect_text(profile.key_protected)
                    logger.info("Secret source: dpapi for SSID=%r", ssid)
                except VaultPortabilityError:
                    # Blob was encrypted by a different Windows account (cross-user scenario).
                    # Return needs_reauth=True so the UI can prompt for password re-entry
                    # and re-save the profile under the current account's vault.
                    logger.warning(
                        "DPAPI cross-user decrypt failed for SSID=%r — signalling needs_reauth",
                        ssid,
                    )
                    return ConnectResult(
                        success=False,
                        needs_reauth=True,
                        message=(
                            f"Пароль для «{ssid}» зашифрован под другим аккаунтом Windows "
                            "и недоступен для текущего пользователя.\n"
                            "Введите пароль повторно — он будет сохранён для этого аккаунта."
                        ),
                    )
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
        self._validate_ssid(ssid)
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
        self._validate_ssid(ssid)
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
        # exit_code == 0 — единственный надёжный критерий успеха netsh.
        # Substring-match по stdout ненадёжен: слово "successfully" может встречаться
        # и в сообщениях об ошибках на некоторых локализациях.
        return ConnectResult(success=result.success, message=result.stdout.strip())

    def delete_netsh_profile(self, ssid: str) -> ConnectResult:
        self._validate_ssid(ssid)
        result = self._runner.run(
            ["netsh", "wlan", "delete", "profile", f'name="{ssid}"'],
            timeout=10,
        )
        return ConnectResult(success=result.success, message=result.stdout.strip())

    # ── Internal ──────────────────────────────────────────────────

    def _add_profile_xml(
        self, ssid: str, profile: WifiProfile, password: str
    ) -> ConnectResult:
        # Строим XML до создания temp-файла.
        # build_profile_xml может поднять ValueError (например, WEP) —
        # в этом случае файл не создаётся и finally-блок не нужен.
        try:
            xml_content = build_profile_xml(
                ssid=ssid,
                auth=profile.auth,
                cipher=profile.cipher,
                password=password,
                auto_connect=profile.auto_connect,
                connect_hidden=profile.connect_hidden,
                is_adhoc=profile.is_adhoc,
            )
        except ValueError as exc:
            logger.error("XML build rejected for SSID=%r: %s", ssid, exc)
            return ConnectResult(success=False, message=str(exc))

        tmp_path = None
        # result инициализируем до try чтобы исключить UnboundLocalError
        # если OSError при mkstemp или write случится раньше runner.run().
        result = None
        try:
            try:
                fd, tmp_path = tempfile.mkstemp(suffix=".xml", prefix="quickip_wifi_")
            except OSError as exc:
                logger.error("Failed to create temp XML for SSID=%r: %s", ssid, exc)
                return ConnectResult(success=False, message=f"Не удалось создать временный профиль: {exc}")

            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(xml_content)
            except OSError as exc:
                logger.error("Failed to write temp XML for SSID=%r: %s", ssid, exc)
                return ConnectResult(success=False, message=f"Не удалось записать XML профиль: {exc}")

            # Пробуем добавить с user=all (системный профиль), при отказе — текущий пользователь
            result = self._runner.run(
                ["netsh", "wlan", "add", "profile",
                 f"filename={tmp_path}", "user=all"],
                timeout=15,
            )
            if not result.success:
                logger.debug("user=all failed (exit=%d), retrying without scope", result.exit_code)
                result = self._runner.run(
                    ["netsh", "wlan", "add", "profile", f"filename={tmp_path}"],
                    timeout=15,
                )
        finally:
            # Secure wipe + unlink во всех случаях (успех/ошибка/исключение).
            # os.unlink не стирает данные — перезаписываем нулями перед удалением.
            # На SSD эффективность зависит от trim, но это лучше, чем ничего.
            if tmp_path and os.path.exists(tmp_path):
                try:
                    file_size = os.path.getsize(tmp_path)
                    if file_size > 0:
                        with open(tmp_path, "r+b") as _wf:
                            _wf.write(b"\x00" * file_size)
                            _wf.flush()
                            os.fsync(_wf.fileno())
                except OSError:
                    pass  # best-effort — не роняем основной поток
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

        if result is None:
            # Не должно случиться после явной обработки OSError выше,
            # но защищаемся на случай неожиданного пути исполнения.
            return ConnectResult(success=False, message="Не удалось выполнить netsh.")

        # exit_code == 0 — единственный надёжный критерий успеха netsh.
        # Substring-match по stdout ненадёжен: сообщение об ошибке тоже может
        # содержать слово "profile" / "профиль" (например "The profile could not be added").
        if not result.success:
            logger.error("add profile failed: exit=%d stdout=%r stderr=%r",
                         result.exit_code, result.stdout, result.stderr)
        else:
            logger.info("Profile added for SSID=%r", ssid)
        return ConnectResult(success=result.success, message=result.stdout.strip())

    def _windows_profile_exists(self, ssid: str) -> bool:
        """Проверяет есть ли профиль для SSID в системе Windows.

        Использует exit_code как критерий: netsh возвращает 0 если профиль найден,
        ненулевой код если не найден — независимо от локализации.
        """
        result = self._runner.run(
            ["netsh", "wlan", "show", "profile", f'name="{ssid}"'],
            timeout=10,
        )
        return result.success  # exit_code == 0

    def _connect_by_name(self, ssid: str) -> ConnectResult:
        cmd = ["netsh", "wlan", "connect", f'name="{ssid}"', f'ssid="{ssid}"']
        iface = self._get_wifi_interface()
        if iface:
            cmd.append(f"interface={iface}")
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Connect cmd: netsh wlan connect name=*** ssid=***")
        result = self._runner.run(cmd, timeout=15)
        return ConnectResult(success=result.success, message=result.stdout.strip())

    def _get_wifi_interface(self) -> str:
        """Возвращает имя первого активного Wi-Fi адаптера."""
        result = self._runner.run(["netsh", "wlan", "show", "interfaces"], timeout=10)
        if not result.stdout:
            return ""
        for line in result.stdout.splitlines():
            m = re.match(r"^\s*(?:Name|Имя)\s*:\s*(.+)$", line.strip(), re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return ""
