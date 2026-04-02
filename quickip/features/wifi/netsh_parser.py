"""Wi-Fi feature — netsh output parsers.

Pure parsing functions; no I/O, no subprocess calls.
All frequencies are calculated from channel numbers per IEEE 802.11 spec.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

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
    """Parse output of: netsh wlan show networks mode=bssid

    Returns a list of WifiNetworkSnapshot, one per unique BSSID block.
    """
    if not raw:
        return []

    networks: List[WifiNetworkSnapshot] = []
    current: dict = {}
    block_lines: List[str] = []

    def _flush() -> None:
        if not current.get("ssid"):
            return
        ch = _int(current.get("channel", "0"))
        mbps = _extract_mbps("\n".join(block_lines))
        protocol = current.get("radio_type", "")
        # Если скорость из netsh ≤ 54 (только legacy rates) — используем fallback по протоколу
        # netsh wlan show networks не возвращает реальные HT/VHT скорости
        if protocol:
            proto_lower = protocol.lower()
            proto_mbps = 0
            if "ax" in proto_lower or "wi-fi 6" in proto_lower:
                proto_mbps = 1200
            elif "ac" in proto_lower or "wi-fi 5" in proto_lower:
                proto_mbps = 867
            elif "n" in proto_lower:
                proto_mbps = 300
            elif "g" in proto_lower or "a" in proto_lower:
                proto_mbps = 54
            if proto_mbps > mbps:
                mbps = proto_mbps
        networks.append(WifiNetworkSnapshot(
            ssid=current.get("ssid", ""),
            bssid=current.get("bssid", ""),
            signal_pct=_int(current.get("signal", "0").replace("%", "")),
            auth=current.get("auth", ""),
            cipher=current.get("cipher", ""),
            channel=ch,
            freq_ghz=channel_to_freq(ch),
            mbps=mbps,
            protocol=protocol,
        ))

    for line in raw.splitlines():
        stripped = line.strip()
        block_lines.append(stripped)

        m = re.match(r"^SSID\s+\d+\s*:\s*(.+)$", stripped, re.IGNORECASE)
        if m:
            _flush()
            current = {"ssid": _clean(m.group(1))}
            block_lines = []
            continue

        m = re.match(r"^BSSID\s+1\s*:\s*(.+)$", stripped, re.IGNORECASE)
        if m:
            current.setdefault("bssid", _clean(m.group(1)))
            continue

        for key, pattern in (
            ("auth",       r"^(?:Authentication|Проверка подлинности)\s*:\s*(.+)$"),
            ("cipher",     r"^(?:Encryption|Шифрование)\s*:\s*(.+)$"),
            ("signal",     r"^(?:Signal|Сигнал)\s*:\s*(.+)$"),
            ("radio_type", r"^(?:Radio type|Тип радио)\s*:\s*(.+)$"),
            ("channel",    r"^(?:Channel|Канал)\s*:\s*(\d+)"),
        ):
            if key in current:
                continue
            m2 = re.match(pattern, stripped, re.IGNORECASE)
            if m2:
                current[key] = _clean(m2.group(1))

    _flush()
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
