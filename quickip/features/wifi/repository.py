"""Wi-Fi feature repositories — profile store and options store.

Two repositories in one file:
  WifiProfileRepository — saved credential profiles (SSID + DPAPI-encrypted PSK)
  WifiOptionsRepository — global Wi-Fi preferences
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from quickip.shared.paths import get_wifi_profiles_file, get_wifi_options_file
from quickip.core.storage.base_repo import BaseJsonRepository

logger = logging.getLogger(__name__)


# ── Auth & cipher constants ───────────────────────────────────────────────────

AUTH_OPTIONS: List[str] = [
    "Open",
    "WEP",
    "WPA-Personal",
    "WPA2-Personal",
    "WPA3-Personal",
    "WPA-Enterprise",
    "WPA2-Enterprise",
    "WPA3-Enterprise",
    "WPA2/WPA3-Transition",
    "OWE",
]

CIPHER_OPTIONS: Dict[str, List[str]] = {
    "Open":                  ["None"],
    "WEP":                   ["WEP"],
    "WPA-Personal":          ["TKIP", "AES"],
    "WPA2-Personal":         ["AES"],
    "WPA3-Personal":         ["AES"],
    "WPA-Enterprise":        ["TKIP", "AES"],
    "WPA2-Enterprise":       ["AES"],
    "WPA3-Enterprise":       ["AES"],
    "WPA2/WPA3-Transition":  ["AES"],
    "OWE":                   ["AES"],
}


# ── Data models ───────────────────────────────────────────────────────────────

@dataclass
class WifiNetworkSnapshot:
    """A visible Wi-Fi network from netsh wlan show networks mode=bssid."""
    ssid: str
    bssid: str
    signal_pct: int
    auth: str
    cipher: str
    channel: int
    freq_ghz: float    # calculated from channel
    mbps: int          # max rate from netsh output
    protocol: str      # 802.11n/ac/ax etc.


@dataclass
class WifiProfile:
    """Saved Wi-Fi credential profile stored in app storage."""
    id: str
    ssid: str
    auth: str
    cipher: str
    key_protected: str   # DPAPI base64 blob; "" for open networks
    auto_connect: bool = True
    connect_hidden: bool = False
    is_adhoc: bool = False
    created_at: str = field(
        default_factory=lambda: datetime.now().isoformat()
    )


@dataclass
class WifiOptions:
    """Global Wi-Fi feature preferences."""
    disable_wifi_when_lan: bool = False
    roam_strongest_same_ssid: bool = False
    enable_logging: bool = False


# ── Credential profiles repo ──────────────────────────────────────────────────

class WifiProfileRepository(BaseJsonRepository):
    """Persists saved Wi-Fi credential profiles to wifi_profiles.json."""

    def __init__(self, file_path: Optional[Path] = None) -> None:
        super().__init__(file_path or get_wifi_profiles_file())
        self._cache: Dict[str, WifiProfile] = {}
        self._load_cache()

    def list(self) -> List[WifiProfile]:
        return list(self._cache.values())

    def get(self, profile_id: str) -> Optional[WifiProfile]:
        return self._cache.get(profile_id)

    def find_by_ssid(self, ssid: str) -> Optional[WifiProfile]:
        return next((p for p in self._cache.values() if p.ssid == ssid), None)

    def save(self, profile: WifiProfile) -> None:
        self._cache[profile.id] = profile
        self._flush()

    def delete(self, profile_id: str) -> None:
        self._cache.pop(profile_id, None)
        self._flush()

    def _load_cache(self) -> None:
        for row in self._load_raw():
            try:
                p = WifiProfile(
                    id=str(row["id"]),
                    ssid=str(row["ssid"]),
                    auth=str(row.get("auth", "WPA2-Personal")),
                    cipher=str(row.get("cipher", "AES")),
                    key_protected=str(row.get("key_protected", "")),
                    auto_connect=bool(row.get("auto_connect", True)),
                    connect_hidden=bool(row.get("connect_hidden", False)),
                    is_adhoc=bool(row.get("is_adhoc", False)),
                    created_at=str(row.get("created_at", "")),
                )
                self._cache[p.id] = p
            except (KeyError, TypeError):
                continue

    def _flush(self) -> None:
        rows = [
            {
                "id": p.id, "ssid": p.ssid, "auth": p.auth, "cipher": p.cipher,
                "key_protected": p.key_protected, "auto_connect": p.auto_connect,
                "connect_hidden": p.connect_hidden, "is_adhoc": p.is_adhoc,
                "created_at": p.created_at,
            }
            for p in self._cache.values()
        ]
        self._save_raw(rows)


# ── Options repo ──────────────────────────────────────────────────────────────

class WifiOptionsRepository(BaseJsonRepository):
    """Persists global Wi-Fi options to wifi_options.json (single-element list)."""

    _DEFAULTS = {
        "disable_wifi_when_lan": False,
        "roam_strongest_same_ssid": False,
        "enable_logging": False,
    }

    def __init__(self, file_path: Optional[Path] = None) -> None:
        super().__init__(file_path or get_wifi_options_file())
        rows = self._load_raw()
        self._data: dict = dict(self._DEFAULTS)
        if rows and isinstance(rows[0], dict):
            self._data.update(rows[0])

    def load(self) -> WifiOptions:
        d = self._data
        return WifiOptions(
            disable_wifi_when_lan=bool(d.get("disable_wifi_when_lan", False)),
            roam_strongest_same_ssid=bool(d.get("roam_strongest_same_ssid", False)),
            enable_logging=bool(d.get("enable_logging", False)),
        )

    def save(self, opts: WifiOptions) -> None:
        self._data = {
            "disable_wifi_when_lan": opts.disable_wifi_when_lan,
            "roam_strongest_same_ssid": opts.roam_strongest_same_ssid,
            "enable_logging": opts.enable_logging,
        }
        self._save_raw([self._data])
