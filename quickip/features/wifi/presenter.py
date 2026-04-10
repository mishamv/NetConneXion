"""Wi-Fi feature presenter — coordinates WifiService and repositories."""

from __future__ import annotations

import json
import logging
import queue
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, TYPE_CHECKING

from quickip.core.events.types import (
    WifiNetworksUpdated, WifiStatusUpdated, WifiProfileSaved, WifiProfileDeleted,
)
from quickip.features.wifi.repository import (
    WifiProfileRepository, WifiOptionsRepository,
    WifiProfile, WifiOptions, WifiNetworkSnapshot, AUTH_OPTIONS, CIPHER_OPTIONS,
)
from quickip.features.wifi.service import WifiService

if TYPE_CHECKING:
    from quickip.app.bootstrap import ServiceContainer

logger = logging.getLogger(__name__)

_POLL_INTERVAL_MS = 3000  # status poll interval in milliseconds


class WifiPresenter:
    """Coordinates Wi-Fi service + repositories; all UI calls route here."""

    def __init__(self, container: "ServiceContainer") -> None:
        self._container = container
        self._service = WifiService(container)
        self._profile_repo = WifiProfileRepository()
        self._options_repo = WifiOptionsRepository()
        self._view = None
        self._status_poll_id = None   # root.after handle
        self._root = None             # tk root ref for after() calls
        self._status_queue: queue.Queue = queue.Queue(maxsize=1)  # thread-safe

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

    # ── Status polling ────────────────────────────────────────────

    def start_status_polling(self, root) -> None:
        """Start polling interface status every 3 s via root.after()."""
        self._root = root
        self._stop_polling = False
        self._poll_status()

    def stop_status_polling(self) -> None:
        self._stop_polling = True
        if self._root and self._status_poll_id:
            try:
                self._root.after_cancel(self._status_poll_id)
            except Exception:
                pass
        self._status_poll_id = None

    def _poll_status(self) -> None:
        if getattr(self, "_stop_polling", True):
            return

        # ── Deliver any result queued by the previous worker (main thread) ──
        try:
            status = self._status_queue.get_nowait()
            self._container.event_bus.publish(  # type: ignore[arg-type]
                WifiStatusUpdated(
                    adapter=status.get("name", ""),
                    ssid=status.get("ssid", ""),
                    connected=status.get("state", "").lower() == "connected",
                )
            )
            if self._view and hasattr(self._view, "update_status"):
                self._view.update_status(status)
        except queue.Empty:
            pass

        # ── Spawn worker; result goes into queue (no tkinter calls in thread) ─
        def _work() -> None:
            try:
                status = self._service.get_interface_status()
                try:
                    self._status_queue.put_nowait(status)
                except queue.Full:
                    pass
            except Exception:
                logger.exception("WifiPresenter status poll error")

        threading.Thread(target=_work, daemon=True, name="wifi_status").start()

        if self._root and not getattr(self, "_stop_polling", True):
            self._status_poll_id = self._root.after(
                _POLL_INTERVAL_MS, self._poll_status
            )

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
                    result = self._service.connect(ssid, profile)
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
        """Encrypt password with DPAPI vault and persist profile."""
        key_protected = ""
        if password:
            if self._container.vault_available:
                from quickip.core.security.vault import protect_text
                key_protected = protect_text(password)
            else:
                raise RuntimeError(
                    "Шифрование паролей недоступно (pywin32 не установлен)"
                )
        pid = profile_id or str(uuid.uuid4())
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
        return self._service.connect(ssid, profile)

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

    def get_auth_options(self) -> List[str]:
        return list(AUTH_OPTIONS)

    def get_cipher_options(self, auth: str) -> List[str]:
        return list(CIPHER_OPTIONS.get(auth, ["AES"]))
