"""Wi-Fi feature — netsh output parsers.

Pure parsing functions; no I/O, no subprocess calls.
All frequencies are calculated from channel numbers per IEEE 802.11 spec.
"""

from __future__ import annotations

import re
from typing import Dict, List

from quickip.features.wifi.repository import WifiNetworkSnapshot


# ── Frequency tables ──────────────────────────────────────────────────────────

_5GHZ_CHANNELS: Dict[int, float] = {
    36: 5.180, 40: 5.200, 44: 5.220, 48: 5.240,
    52: 5.260, 56: 5.280, 60: 5.300, 64: 5.320,
    100: 5.500, 104: 5.520, 108: 5.540, 112: 5.560,
    116: 5.580, 120: 5.600, 124: 5.620, 128: 5.640,
    132: 5.660, 136: 5.680, 140: 5.700, 144: 5.720,
    149: 5.745, 153: 5.765, 157: 5.785, 161: 5.805,
    165: 5.825,
}


def channel_to_freq(channel: int) -> float:
    """Return frequency in GHz for a Wi-Fi channel number."""
    if 1 <= channel <= 13:
        return round(2.412 + (channel - 1) * 0.005, 3)
    if channel == 14:
        return 2.484
    return _5GHZ_CHANNELS.get(channel, 0.0)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _clean(value: str) -> str:
    return value.strip().rstrip(".")


def _int(value: str, default: int = 0) -> int:
    try:
        return int(re.sub(r"[^\d]", "", value) or str(default))
    except (ValueError, TypeError):
        return default


def _extract_mbps(raw_block: str) -> int:
    """Extract max Mbps — prefer 'Other rates' (high speed) over 'Basic rates' (legacy)."""
    basic: List[int] = []
    other: List[int] = []
    pattern_basic = re.compile(
        r"^(?:Basic rates|Основные скорости)\s*\([^)]*\)\s*:\s*([\d\s\.]+)",
        re.IGNORECASE
    )
    pattern_other = re.compile(
        r"^(?:Other rates|Другие скорости)\s*\([^)]*\)\s*:\s*([\d\s\.]+)",
        re.IGNORECASE
    )
    for line in raw_block.splitlines():
        s = line.strip()
        m = pattern_other.match(s)
        if m:
            for token in re.split(r"[\s;,]+", m.group(1)):
                try:
                    other.append(int(float(token)))
                except ValueError:
                    pass
            continue
        m = pattern_basic.match(s)
        if m:
            for token in re.split(r"[\s;,]+", m.group(1)):
                try:
                    basic.append(int(float(token)))
                except ValueError:
                    pass
    # Если есть "Другие скорости" — берём максимум оттуда (это реальные HT/VHT скорости)
    if other:
        return max(other)
    return max(basic) if basic else 0


# ── Network parser ────────────────────────────────────────────────────────────

def parse_networks(raw: str) -> List[WifiNetworkSnapshot]:
    """Parse every BSSID returned by ``netsh wlan show networks mode=bssid``.

    One SSID can be broadcast by several access points. Authentication and
    cipher belong to the SSID block, while signal, radio type and channel
    belong to each individual BSSID block.
    """
    if not raw:
        return []

    networks: List[WifiNetworkSnapshot] = []
    ssid_data: dict = {}
    bssid_data: dict = {}
    bssid_lines: List[str] = []

    def _flush_bssid() -> None:
        if not ssid_data.get("ssid") or not bssid_data.get("bssid"):
            return
        channel = _int(bssid_data.get("channel", "0"))
        protocol = bssid_data.get("radio_type", "")
        mbps = _extract_mbps("\n".join(bssid_lines))
        if protocol:
            protocol_lower = protocol.lower()
            protocol_mbps = 0
            if "ax" in protocol_lower or "wi-fi 6" in protocol_lower:
                protocol_mbps = 1200
            elif "ac" in protocol_lower or "wi-fi 5" in protocol_lower:
                protocol_mbps = 867
            elif "n" in protocol_lower:
                protocol_mbps = 300
            elif "g" in protocol_lower or "a" in protocol_lower:
                protocol_mbps = 54
            mbps = max(mbps, protocol_mbps)
        networks.append(WifiNetworkSnapshot(
            ssid=ssid_data.get("ssid", ""),
            bssid=bssid_data.get("bssid", ""),
            signal_pct=_int(bssid_data.get("signal", "0").replace("%", "")),
            auth=ssid_data.get("auth", ""),
            cipher=ssid_data.get("cipher", ""),
            channel=channel,
            freq_ghz=channel_to_freq(channel),
            mbps=mbps,
            protocol=protocol,
        ))

    for line in raw.splitlines():
        stripped = line.strip()

        ssid_match = re.match(
            r"^SSID\s+\d+\s*:\s*(.*)$",
            stripped,
            re.IGNORECASE,
        )
        if ssid_match:
            _flush_bssid()
            ssid_data = {"ssid": _clean(ssid_match.group(1))}
            bssid_data = {}
            bssid_lines = []
            continue

        bssid_match = re.match(
            r"^BSSID\s+\d+\s*:\s*(.+)$",
            stripped,
            re.IGNORECASE,
        )
        if bssid_match:
            _flush_bssid()
            bssid_data = {"bssid": _clean(bssid_match.group(1))}
            bssid_lines = [stripped]
            continue

        if not bssid_data:
            for key, pattern in (
                ("auth", r"^(?:Authentication|Проверка подлинности)\s*:\s*(.+)$"),
                ("cipher", r"^(?:Encryption|Шифрование)\s*:\s*(.+)$"),
            ):
                match = re.match(pattern, stripped, re.IGNORECASE)
                if match:
                    ssid_data[key] = _clean(match.group(1))
                    break
            continue

        bssid_lines.append(stripped)
        for key, pattern in (
            ("signal", r"^(?:Signal|Сигнал)\s*:\s*(.+)$"),
            ("radio_type", r"^(?:Radio type|Тип радио)\s*:\s*(.+)$"),
            ("channel", r"^(?:Channel|Канал)\s*:\s*(\d+)"),
        ):
            if key in bssid_data:
                continue
            match = re.match(pattern, stripped, re.IGNORECASE)
            if match:
                bssid_data[key] = _clean(match.group(1))
                break

    _flush_bssid()
    return networks


# ── Interface parser ──────────────────────────────────────────────────────────

def parse_interface_status(raw: str) -> dict:
    """Parse output of: netsh wlan show interfaces

    Returns a dict with keys: name, state, ssid, signal, auth, channel.
    """
    if not raw:
        return {}
    fields: dict = {}
    mapping = {
        "name":    r"^(?:Name|Имя)\s*:\s*(.+)$",
        "state":   r"^(?:State|Состояние)\s*:\s*(.+)$",
        "ssid":    r"^SSID\s*:\s*(.+)$",
        "signal":  r"^(?:Signal|Сигнал)\s*:\s*(.+)$",
        "auth":    r"^(?:Authentication|Проверка подлинности)\s*:\s*(.+)$",
        "channel": r"^(?:Channel|Канал)\s*:\s*(\d+)",
    }
    for line in raw.splitlines():
        stripped = line.strip()
        for key, pattern in mapping.items():
            if key in fields:
                continue
            m = re.match(pattern, stripped, re.IGNORECASE)
            if m:
                fields[key] = _clean(m.group(1))
    if fields.get("signal"):
        fields["signal"] = _int(fields["signal"].replace("%", ""))
    if fields.get("channel"):
        fields["channel"] = _int(fields["channel"])
    return fields


def parse_saved_profiles(raw: str) -> List[str]:
    """Parse output of: netsh wlan show profiles → list of profile names."""
    names: List[str] = []
    for line in raw.splitlines():
        m = re.match(r"^\s*(?:All User Profile|Профиль всех пользователей)\s*:\s*(.+)$", line, re.IGNORECASE)
        if m:
            names.append(_clean(m.group(1)))
    return names
