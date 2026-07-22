"""Wi-Fi feature presenter — coordinates WifiService and repositories."""

from __future__ import annotations

import json
import logging
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, TYPE_CHECKING

from quickip.core.events.types import (
    WifiNetworksUpdated, WifiProfileSaved, WifiProfileDeleted,
)
from quickip.features.wifi.repository import (
    WifiProfileRepository, WifiOptionsRepository,
    WifiProfile, WifiOptions, WifiNetworkSnapshot, AUTH_OPTIONS, CIPHER_OPTIONS,
)
from quickip.features.wifi.service import WifiService

if TYPE_CHECKING:
    from quickip.app.bootstrap import ServiceContainer

logger = logging.getLogger(__name__)

class WifiPresenter:
    """Coordinates Wi-Fi service + repositories; all UI calls route here."""

    def __init__(self, container: "ServiceContainer") -> None:
        self._container = container
        self._service = WifiService(container)
        self._profile_repo = WifiProfileRepository()
        self._options_repo = WifiOptionsRepository()
        self._view = None

    def bind_view(self, view) -> None:
        self._view = view
        logger.debug("WifiPresenter bound to view")

    # ── Scanning ──────────────────────────────────────────────────

    def scan(self, callback: Optional[Callable[[List[WifiNetworkSnapshot]], None]] = None) -> None:
        """Scan networks in background; push results to view and call callback."""
        def _work() -> None:
            try:
                networks = self._service.scan_networks()
                self._container.event_bus.publish(  # type: ignore[arg-type]
                    WifiNetworksUpdated(network_count=len(networks))
                )
                if callback:
                    callback(networks)
            except Exception:
                logger.exception("WifiPresenter.scan error")
                if callback:
                    callback([])
        threading.Thread(target=_work, daemon=True, name="wifi_scan").start()

    # ── Connect / Disconnect ──────────────────────────────────────

    def connect(
        self,
        ssid: str,
        callback: Optional[Callable[[bool, str], None]] = None,
    ) -> None:
        """Connect to *ssid*. Looks up saved profile; prompts if not found."""
        profile = self._profile_repo.find_by_ssid(ssid)

        def _work() -> None:
            try:
                if profile:
                    current_profile = profile
                    # Мигрировать b64-профили ДО вызова сервиса (T1552.001).
                    # WifiService.connect() отклоняет b64 — миграция здесь обязательна.
                    if current_profile.key_protected.startswith("b64:"):
                        current_profile = self._migrate_b64_profile(current_profile)
                        if current_profile.key_protected.startswith("b64:"):
                            # Миграция не удалась (нет vault/keyring) — блокируем
                            if callback:
                                callback(
                                    False,
                                    f"Профиль '{ssid}' использует устаревший формат хранения пароля.\n"
                                    "Пересохраните профиль вручную: Настройки Wi-Fi → редактировать → Сохранить.",
                                )
                            return
                    result = self._service.connect(ssid, current_profile)
                else:
                    result = self._service.connect_open(ssid)
                if callback:
                    callback(result.success, result.message)
            except Exception as exc:
                logger.exception("WifiPresenter.connect error")
                if callback:
                    callback(False, str(exc))

        threading.Thread(target=_work, daemon=True, name="wifi_connect").start()

    def disconnect(
        self, callback: Optional[Callable[[bool, str], None]] = None
    ) -> None:
        def _work() -> None:
            try:
                result = self._service.disconnect()
                if callback:
                    callback(result.success, result.message)
            except Exception as exc:
                if callback:
                    callback(False, str(exc))
        threading.Thread(target=_work, daemon=True, name="wifi_disconnect").start()

    # ── Profiles ──────────────────────────────────────────────────

    def load_profiles(self) -> List[WifiProfile]:
        return self._profile_repo.list()

    def save_profile(
        self,
        ssid: str, auth: str, cipher: str, password: str,
        auto_connect: bool, connect_hidden: bool, is_adhoc: bool,
        profile_id: Optional[str] = None,
    ) -> None:
        """Encrypt password with DPAPI vault (primary) or keyring (fallback) and persist profile.

        Keyring key is profile UUID, not SSID — avoids collisions when two profiles
        share the same network name but have different passwords.
        """
        # UUID нужен до encrypt — keyring использует его как ключ
        pid = profile_id or str(uuid.uuid4())
        key_protected = ""
        if password:
            if self._container.vault_available:
                from quickip.core.security.vault import protect_text
                key_protected = protect_text(password)
            elif self._container.keyring_available:
                from quickip.core.security.keyring_vault import protect_text as kr_protect
                key_protected = kr_protect(pid, password)
            else:
                raise RuntimeError(
                    "Шифрование паролей недоступно (pywin32 не установлен и keyring недоступен)"
                )
        p = WifiProfile(
            id=pid, ssid=ssid, auth=auth, cipher=cipher,
            key_protected=key_protected,
            auto_connect=auto_connect,
            connect_hidden=connect_hidden,
            is_adhoc=is_adhoc,
        )
        self._profile_repo.save(p)
        self._container.event_bus.publish(WifiProfileSaved(profile_id=pid, ssid=ssid))  # type: ignore[arg-type]

    def delete_profile(self, profile_id: str) -> None:
        p = self._profile_repo.get(profile_id)
        self._profile_repo.delete(profile_id)
        if p:
            # Удаляем secret из keyring если профиль использовал его
            if p.key_protected.startswith("kr:"):
                _suffix = p.key_protected[3:]
                if _suffix:
                    from quickip.core.security.keyring_vault import delete as kr_delete
                    kr_delete(_suffix)
                else:
                    # legacy kr: — удаляем по SSID
                    from quickip.core.security.keyring_vault import delete_legacy as kr_del_legacy
                    kr_del_legacy(p.ssid)
            self._container.event_bus.publish(WifiProfileDeleted(profile_id=profile_id))  # type: ignore[arg-type]

    def get_system_profiles(self) -> List[str]:
        return self._service.get_saved_netsh_profiles()

    def delete_system_profile(
        self, ssid: str, callback: Optional[Callable[[bool, str], None]] = None
    ) -> None:
        def _work() -> None:
            r = self._service.delete_netsh_profile(ssid)
            if callback:
                callback(r.success, r.message)
        threading.Thread(target=_work, daemon=True).start()

    def export_profiles(self, path: Path) -> None:
        profiles = self._profile_repo.list()
        data = {
            "schema_version": 1,
            "portable": False,
            "exported_at": datetime.now().isoformat(),
            "profiles": [
                {
                    "id": p.id, "ssid": p.ssid, "auth": p.auth, "cipher": p.cipher,
                    "key_protected": p.key_protected,
                    "auto_connect": p.auto_connect,
                    "connect_hidden": p.connect_hidden,
                    "is_adhoc": p.is_adhoc,
                    "created_at": p.created_at,
                }
                for p in profiles
            ],
        }
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2),
                               encoding="utf-8")

    def import_profiles(self, path: Path) -> tuple[int, List[str]]:
        """Import profiles from JSON file. Returns (count, errors)."""
        raw = Path(path).read_text(encoding="utf-8")
        data = json.loads(raw)
        imported = 0
        errors: List[str] = []
        for row in data.get("profiles", []):
            try:
                p = WifiProfile(
                    id=row.get("id") or str(uuid.uuid4()),
                    ssid=row["ssid"],
                    auth=row.get("auth", "WPA2-Personal"),
                    cipher=row.get("cipher", "AES"),
                    key_protected=row.get("key_protected", ""),
                    auto_connect=bool(row.get("auto_connect", True)),
                    connect_hidden=bool(row.get("connect_hidden", False)),
                    is_adhoc=bool(row.get("is_adhoc", False)),
                    created_at=row.get("created_at", datetime.now().isoformat()),
                )
                from quickip.core.security.vault import VaultPortabilityError
                if p.key_protected and self._container.vault_available:
                    try:
                        from quickip.core.security.vault import unprotect_text
                        unprotect_text(p.key_protected)   # test decrypt
                    except VaultPortabilityError:
                        p.key_protected = ""
                        errors.append(f"{p.ssid}: пароль зашифрован на другом устройстве")
                self._profile_repo.save(p)
                imported += 1
            except Exception as exc:
                errors.append(f"{row.get('ssid', '?')}: {exc}")
        return imported, errors

    # ── Options ───────────────────────────────────────────────────

    def load_options(self) -> WifiOptions:
        return self._options_repo.load()

    def save_options(self, opts: WifiOptions) -> None:
        self._options_repo.save(opts)

    # ── Service façade (keeps UI away from _service/_profile_repo) ────

    def scan_networks(self) -> List[WifiNetworkSnapshot]:
        return self._service.scan_networks()

    def get_interface_status(self) -> dict:
        return self._service.get_interface_status()

    def connect_with_ssid(
        self, ssid: str, password: str,
        auth: str = "WPA2-Personal", cipher: str = "AES",
    ):
        """Connect using a plaintext password (no saved profile)."""
        return self._service.connect_with_password(ssid, password, auth=auth, cipher=cipher)

    def connect_with_profile(self, ssid: str, profile):
        if profile.key_protected.startswith("b64:"):
            profile = self._migrate_b64_profile(profile)
        return self._service.connect(ssid, profile)

    def _migrate_b64_profile(self, profile: WifiProfile) -> WifiProfile:
        """Upgrade a legacy b64: profile to DPAPI or keyring in-place.

        Decodes the weak base64 password and re-encrypts it using the best
        available vault. Updates the repo immediately so subsequent connects
        use the secure storage. Returns the (possibly updated) profile.
        """
        import base64 as _b64
        try:
            password = _b64.b64decode(profile.key_protected[4:]).decode()
        except Exception as exc:
            logger.warning("Cannot decode b64: for SSID=%r: %s", profile.ssid, exc)
            return profile

        new_key: Optional[str] = None
        if self._container.vault_available:
            try:
                from quickip.core.security.vault import protect_text
                new_key = protect_text(password)
                logger.info("Migrated b64: → dpapi for SSID=%r", profile.ssid)
            except Exception as exc:
                logger.warning("DPAPI migration failed for SSID=%r: %s", profile.ssid, exc)

        if new_key is None and self._container.keyring_available:
            try:
                from quickip.core.security.keyring_vault import protect_text as kr_protect
                # Ключ — profile UUID, не SSID: исключает коллизии при одинаковых именах сетей
                new_key = kr_protect(profile.id, password)
                logger.info("Migrated b64: → keyring(v2) for profile_id=%r", profile.id)
            except Exception as exc:
                logger.warning("Keyring migration failed for profile_id=%r: %s", profile.id, exc)

        if new_key is not None:
            profile.key_protected = new_key
            self._profile_repo.save(profile)
        else:
            logger.warning(
                "Cannot migrate b64: profile for SSID=%r — no vault/keyring available", profile.ssid
            )
        return profile

    def migrate_legacy_profiles(self) -> None:
        """Migrate all b64:-prefixed profiles to DPAPI/keyring at startup.

        MITRE T1555.004 / T1552.001 — removes plaintext-equivalent base64
        credentials from wifi_profiles.json before any user interaction.
        Runs in the calling thread; invoke from a daemon thread to avoid
        blocking the UI.
        """
        profiles = self._profile_repo.list()
        legacy = [p for p in profiles if p.key_protected.startswith("b64:")]
        if not legacy:
            return
        logger.info("Startup b64: migration — found %d legacy profile(s)", len(legacy))
        for profile in legacy:
            self._migrate_b64_profile(profile)

    def reauth_connect(self, ssid: str, password: str) -> "ConnectResult":
        """Connect using a user-supplied password and re-save the profile under the current account.

        Called after needs_reauth=True from connect_with_profile() — i.e. the stored
        DPAPI blob was encrypted by a different Windows account and cannot be decrypted here.

        On success:
          - connects via netsh
          - re-encrypts the password with the *current* account's vault (DPAPI or keyring)
          - overwrites the profile so subsequent connects succeed without prompting

        On failure (wrong password, netsh error): returns ConnectResult(success=False).
        """
        from quickip.features.wifi.service import ConnectResult  # local import to avoid circular
        profile = self._profile_repo.find_by_ssid(ssid)
        auth = profile.auth if profile else "WPA2-Personal"
        cipher = profile.cipher if profile else "AES"

        result = self._service.connect_with_password(ssid, password, auth=auth, cipher=cipher)

        if result.success and profile:
            # Re-encrypt and persist under the current account's vault.
            # save_profile() picks the best available vault automatically.
            try:
                self.save_profile(
                    ssid=ssid,
                    auth=auth,
                    cipher=cipher,
                    password=password,
                    auto_connect=profile.auto_connect,
                    connect_hidden=profile.connect_hidden,
                    is_adhoc=profile.is_adhoc,
                    profile_id=profile.id,   # reuse existing UUID
                )
                logger.info(
                    "Profile %r re-encrypted under current account after reauth", ssid
                )
                result = ConnectResult(
                    success=True,
                    message=result.message + "\nПароль сохранён для текущего аккаунта.",
                )
            except Exception as exc:
                # Connection succeeded; re-save failed — non-fatal, warn the user.
                logger.warning("reauth_connect: re-save failed for %r: %s", ssid, exc)
                result = ConnectResult(
                    success=True,
                    message=(
                        result.message
                        + f"\n⚠ Не удалось сохранить пароль для текущего аккаунта: {exc}"
                    ),
                )

        return result

    def connect_open_network(self, ssid: str):
        return self._service.connect_open(ssid)

    def disconnect_network(self):
        return self._service.disconnect()

    def get_wifi_interface_config(self, interface_name: str):
        """Run netsh to read current IP config for the Wi-Fi interface."""
        return self._service._runner.run(
            ["netsh", "interface", "ipv4", "show", "config",
             f"name={interface_name}"],
            timeout=8,
        )

    def get_wifi_interface_name(self) -> str:
        return self._service._get_wifi_interface()

    def delete_netsh_profile_for_ssid(
        self, ssid: str, callback=None
    ) -> None:
        self.delete_system_profile(ssid, callback=callback)

    def find_wifi_profile_by_ssid(self, ssid: str):
        return self._profile_repo.find_by_ssid(ssid)

    def get_wifi_profile(self, profile_id: str):
        return self._profile_repo.get(profile_id)

    def save_wifi_profile_obj(self, profile) -> None:
        self._profile_repo.save(profile)

    # ── Helpers ───────────────────────────────────────────────────

    @property
    def vault_available(self) -> bool:
        return self._container.vault_available

    @property
    def keyring_available(self) -> bool:
        return self._container.keyring_available

    def get_auth_options(self) -> List[str]:
        return list(AUTH_OPTIONS)

    def get_cipher_options(self, auth: str) -> List[str]:
        return list(CIPHER_OPTIONS.get(auth, ["AES"]))
