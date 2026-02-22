from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List
import json
import locale
import os
import platform
import sys
import re
import shlex
import subprocess
import time
import uuid


APP_DIR_NAME = "QuickIPChange"
LEGACY_DIR_NAMES = ["Quick-IP-change", "QuickIPChange"]
EXPORT_SCHEMA_VERSION = 1


def _is_portable_mode() -> bool:
    cwd_flag = Path.cwd() / "portable.flag"
    if cwd_flag.exists():
        return True

    exe_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    return (exe_dir / "portable.flag").exists()


_BASE_DIR: Path | None = None


def _candidate_dirs_windows() -> list[Path]:
    """Return candidate storage directories (ordered by preference).

    We keep backwards compatibility with older builds that stored data under:
      - %APPDATA%\QuickIPChange
      - %LOCALAPPDATA%\Quick-IP-change
    """
    candidates: list[Path] = []
    roaming = os.environ.get("APPDATA")
    local = os.environ.get("LOCALAPPDATA")

    if roaming:
        candidates.append(Path(roaming) / APP_DIR_NAME)

    if local:
        for name in LEGACY_DIR_NAMES:
            candidates.append(Path(local) / name)

    return candidates


def _detect_base_dir() -> Path:
    global _BASE_DIR
    if _BASE_DIR is not None:
        return _BASE_DIR

    if _is_portable_mode():
        _BASE_DIR = Path.cwd()
        return _BASE_DIR

    if platform.system().lower() == "windows":
        candidates = _candidate_dirs_windows()
        for base in candidates:
            if (base / "profiles.json").exists() or (base / "settings.json").exists() or (base / "history.json").exists():
                _BASE_DIR = base
                return _BASE_DIR
        if candidates:
            _BASE_DIR = candidates[0]
            return _BASE_DIR

    _BASE_DIR = Path.home() / f".{APP_DIR_NAME.lower()}"
    return _BASE_DIR


def _data_dir() -> Path:
    return _detect_base_dir()


def _storage_file(name: str) -> Path:
    base = _data_dir()
    base.mkdir(parents=True, exist_ok=True)
    return base / name


PROFILES_FILE = _storage_file("profiles.json")
HISTORY_FILE = _storage_file("history.json")
SETTINGS_FILE = _storage_file("settings.json")


@dataclass
class NetworkProfile:
    name: str
    adapter: str
    dhcp_ip: bool = False
    ip: str = ""
    mask: str = ""
    gateway: str = ""
    dhcp_dns: bool = False
    dns_primary: str = ""
    dns_secondary: str = ""


@dataclass
class ApplyResult:
    commands: List[str] = field(default_factory=list)
    output: List[str] = field(default_factory=list)


@dataclass
class ProfileHistoryEntry:
    id: str
    timestamp: str
    profile_name: str
    adapter: str
    commands: List[str]
    output: List[str]
    success: bool
    duration_ms: int
    error: str = ""
    profile_snapshot: dict = field(default_factory=dict)


@dataclass
class HistoryStats:
    total: int = 0
    success: int = 0
    failed: int = 0
    avg_duration_ms: int = 0


@dataclass
class ImportReport:
    imported: int = 0
    skipped: int = 0
    replaced: int = 0
    renamed: int = 0


def _q(value: str) -> str:
    return '"' + value.replace('"', '\\"') + '"'


def _looks_utf16(raw: bytes) -> str | None:
    if len(raw) < 4:
        return None
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return "utf-16"

    even_zeros = sum(1 for b in raw[::2] if b == 0)
    odd_zeros = sum(1 for b in raw[1::2] if b == 0)
    half = max(1, len(raw) // 2)

    if odd_zeros / half > 0.35 and even_zeros / half < 0.1:
        return "utf-16-le"
    if even_zeros / half > 0.35 and odd_zeros / half < 0.1:
        return "utf-16-be"
    return None


def _decode_output(raw: bytes) -> str:
    if not raw:
        return ""

    utf16_guess = _looks_utf16(raw)
    if utf16_guess:
        try:
            return raw.decode(utf16_guess)
        except UnicodeDecodeError:
            pass

    encodings = ["utf-8", "cp866", "cp1251"]
    preferred = locale.getpreferredencoding(False)
    if preferred and preferred.lower() not in [e.lower() for e in encodings]:
        encodings.insert(0, preferred)

    for encoding in encodings:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue

    return raw.decode("utf-8", errors="replace")



def _subprocess_run_kwargs() -> dict:
    if platform.system().lower() != "windows":
        return {}

    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    return {"creationflags": subprocess.CREATE_NO_WINDOW, "startupinfo": startupinfo}


def _run_capture(command: List[str]) -> str:
    completed = subprocess.run(command, capture_output=True, check=True, **_subprocess_run_kwargs())
    stdout = _decode_output(completed.stdout)
    stderr = _decode_output(completed.stderr)
    return (stdout + ("\n" + stderr if stderr else "")).strip()


def parse_netsh_interfaces(output: str) -> List[str]:
    adapters: List[str] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or set(line) == {"-"}:
            continue

        lowered = line.lower()
        if "interface name" in lowered or "имя интерфейса" in lowered:
            continue
        if lowered.startswith("admin state") or lowered.startswith("состояние"):
            continue

        parts = re.split(r"\s{2,}", line)
        if len(parts) >= 4 and parts[-1]:
            adapters.append(parts[-1])

    return adapters


def _unique(items: List[str]) -> List[str]:
    seen: set[str] = set()
    result: List[str] = []
    for item in items:
        normalized = item.strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def list_network_adapters() -> List[str]:
    fallback = ["Ethernet", "Wi-Fi"]
    if platform.system().lower() != "windows":
        return fallback

    discovered: List[str] = []

    try:
        text = _run_capture(["netsh", "interface", "show", "interface"])
        discovered.extend(parse_netsh_interfaces(text))
    except Exception:
        pass

    try:
        text = _run_capture(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; Get-NetAdapter | Select-Object -ExpandProperty Name",
            ]
        )
        discovered.extend([line.strip() for line in text.splitlines() if line.strip()])
    except Exception:
        pass

    adapters = _unique(discovered)
    return adapters or fallback


def build_netsh_commands(profile: NetworkProfile) -> List[str]:
    if not profile.adapter.strip():
        raise ValueError("Adapter name is required")

    commands: List[str] = []
    adapter = _q(profile.adapter.strip())

    if profile.dhcp_ip:
        commands.append(f"netsh interface ipv4 set address name={adapter} source=dhcp")
    else:
        if not all([profile.ip.strip(), profile.mask.strip()]):
            raise ValueError("IP and subnet mask are required for static mode")
        if profile.gateway.strip():
            commands.append(
                "netsh interface ipv4 set address "
                f"name={adapter} source=static "
                f"address={profile.ip.strip()} mask={profile.mask.strip()} "
                f"gateway={profile.gateway.strip()} gwmetric=1"
            )
        else:
            commands.append(
                "netsh interface ipv4 set address "
                f"name={adapter} source=static address={profile.ip.strip()} mask={profile.mask.strip()} gateway=none"
            )

    if profile.dhcp_dns:
        commands.append(f"netsh interface ipv4 set dnsservers name={adapter} source=dhcp")
    elif profile.dns_primary.strip():
        commands.append(
            "netsh interface ipv4 set dnsservers "
            f"name={adapter} source=static address={profile.dns_primary.strip()} register=primary validate=no"
        )
        if profile.dns_secondary.strip():
            commands.append(
                "netsh interface ipv4 add dnsservers "
                f"name={adapter} address={profile.dns_secondary.strip()} index=2 validate=no"
            )

    return commands


def apply_profile(profile: NetworkProfile) -> ApplyResult:
    commands = build_netsh_commands(profile)
    result = ApplyResult(commands=commands)

    if platform.system().lower() != "windows":
        result.output.append("Non-Windows environment detected. Commands were generated but not executed.")
        return result

    for cmd in commands:
        try:
            completed = subprocess.run(
                shlex.split(cmd, posix=False),
                capture_output=True,
                check=True,
                **_subprocess_run_kwargs(),
            )
            stdout = _decode_output(completed.stdout).strip()
            stderr = _decode_output(completed.stderr).strip()
            if stdout:
                result.output.append(stdout)
            if stderr:
                result.output.append(stderr)
        except subprocess.CalledProcessError as exc:
            out = _decode_output(exc.stdout).strip()
            err = _decode_output(exc.stderr).strip()
            detail = err or out or "Unknown netsh error"
            raise RuntimeError(f"Ошибка выполнения: {cmd}\n{detail}") from exc

    return result




def load_settings() -> dict:
    defaults = {
        "wifi_mappings": [],
        "wifi_auto_apply": False,
        "wifi_auto_interval_sec": 5,
        "ui_theme": "light",
    }
    if not SETTINGS_FILE.exists():
        return defaults.copy()

    payload = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return defaults.copy()
    for key, value in defaults.items():
        payload.setdefault(key, value)
    return payload


def save_settings(settings: dict) -> None:
    SETTINGS_FILE.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")

def load_profiles() -> dict[str, NetworkProfile]:
    if not PROFILES_FILE.exists():
        return {}

    payload = json.loads(PROFILES_FILE.read_text(encoding="utf-8"))
    profiles: dict[str, NetworkProfile] = {}
    for item in payload:
        profile = NetworkProfile(**item)
        profiles[profile.name] = profile
    return profiles


def save_profiles(profiles: dict[str, NetworkProfile]) -> None:
    data = [asdict(p) for p in profiles.values()]
    PROFILES_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def export_profiles(export_path: Path, profiles: dict[str, NetworkProfile]) -> None:
    payload = {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "app": "quick-ip-change",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "profiles": [asdict(profile) for profile in profiles.values()],
    }
    export_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _make_unique_name(existing: dict[str, NetworkProfile], base_name: str) -> str:
    if base_name not in existing:
        return base_name

    idx = 2
    candidate = f"{base_name} ({idx})"
    while candidate in existing:
        idx += 1
        candidate = f"{base_name} ({idx})"
    return candidate


def import_profiles(import_path: Path, existing: dict[str, NetworkProfile], strategy: str = "rename") -> tuple[dict[str, NetworkProfile], ImportReport]:
    raw = json.loads(import_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "profiles" not in raw:
        raise ValueError("Некорректный формат файла импорта.")

    report = ImportReport()
    merged = dict(existing)

    for item in raw.get("profiles", []):
        incoming = NetworkProfile(**item)
        if incoming.name not in merged:
            merged[incoming.name] = incoming
            report.imported += 1
            continue

        if strategy == "skip":
            report.skipped += 1
            continue

        if strategy == "replace":
            merged[incoming.name] = incoming
            report.replaced += 1
            continue

        if strategy == "rename":
            new_name = _make_unique_name(merged, incoming.name)
            incoming.name = new_name
            merged[new_name] = incoming
            report.renamed += 1
            report.imported += 1
            continue

        raise ValueError(f"Неизвестная стратегия импорта: {strategy}")

    return merged, report


def load_history() -> list[ProfileHistoryEntry]:
    if not HISTORY_FILE.exists():
        return []

    payload = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    return [ProfileHistoryEntry(**item) for item in payload]


def save_history(entries: list[ProfileHistoryEntry]) -> None:
    HISTORY_FILE.write_text(json.dumps([asdict(entry) for entry in entries], ensure_ascii=False, indent=2), encoding="utf-8")


def compute_history_stats(entries: list[ProfileHistoryEntry]) -> HistoryStats:
    if not entries:
        return HistoryStats()

    total = len(entries)
    success = sum(1 for entry in entries if entry.success)
    failed = total - success
    avg_duration = int(sum(entry.duration_ms for entry in entries) / total)
    return HistoryStats(total=total, success=success, failed=failed, avg_duration_ms=avg_duration)


def append_history_entry(
    profile: NetworkProfile,
    commands: list[str],
    output: list[str],
    success: bool,
    duration_ms: int,
    error: str = "",
) -> ProfileHistoryEntry:
    entries = load_history()
    entry = ProfileHistoryEntry(
        id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc).isoformat(),
        profile_name=profile.name,
        adapter=profile.adapter,
        commands=commands,
        output=output,
        success=success,
        duration_ms=duration_ms,
        error=error,
        profile_snapshot=asdict(profile),
    )
    entries.append(entry)
    save_history(entries)
    return entry


def apply_profile_with_history(profile: NetworkProfile) -> ApplyResult:
    started = time.perf_counter()
    try:
        result = apply_profile(profile)
        duration_ms = int((time.perf_counter() - started) * 1000)
        append_history_entry(
            profile=profile,
            commands=result.commands,
            output=result.output,
            success=True,
            duration_ms=duration_ms,
        )
        return result
    except Exception as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        append_history_entry(
            profile=profile,
            commands=build_netsh_commands(profile),
            output=[],
            success=False,
            duration_ms=duration_ms,
            error=str(exc),
        )
        raise




def get_last_successful_profile_snapshot(profile_name: str | None = None) -> NetworkProfile | None:
    target = profile_name.strip().lower() if profile_name else ""
    entries = load_history()

    for entry in reversed(entries):
        if not entry.success:
            continue
        if target and entry.profile_name.strip().lower() != target:
            continue
        if not entry.profile_snapshot:
            continue
        try:
            return NetworkProfile(**entry.profile_snapshot)
        except Exception:
            continue
    return None


def rollback_last_successful_profile(
    profiles: dict[str, NetworkProfile],
    profile_name: str | None = None,
) -> NetworkProfile:
    snapshot = get_last_successful_profile_snapshot(profile_name)
    if not snapshot:
        if profile_name:
            raise ValueError(f"Нет успешной записи истории для профиля '{profile_name}'.")
        raise ValueError("Нет успешной записи истории для отката.")

    profiles[snapshot.name] = snapshot
    save_profiles(profiles)
    apply_profile_with_history(snapshot)
    return snapshot


def _ping_once(host: str, timeout_ms: int = 900) -> bool:
    if platform.system().lower() == "windows":
        cmd = ["ping", "-n", "1", "-w", str(timeout_ms), host]
    else:
        timeout_sec = max(1, int(round(timeout_ms / 1000)))
        cmd = ["ping", "-c", "1", "-W", str(timeout_sec), host]

    completed = subprocess.run(
        cmd,
        capture_output=True,
        check=False,
        **_subprocess_run_kwargs(),
    )
    return completed.returncode == 0


def check_ip_conflict(profile: NetworkProfile, timeout_ms: int = 900) -> tuple[bool, str]:
    if profile.dhcp_ip:
        return False, ""

    ip = profile.ip.strip()
    if not ip:
        return False, ""

    try:
        reachable = _ping_once(ip, timeout_ms=timeout_ms)
    except Exception as exc:
        return False, f"Не удалось выполнить проверку IP-конфликта: {exc}"

    if reachable:
        return (
            True,
            f"Адрес {ip} уже отвечает на ping. Возможен конфликт IP в сети.\n"
            "Если применить профиль, соединение может работать нестабильно.",
        )

    return False, ""


def run_ping(host: str, count: int = 4) -> str:
    host = host.strip()
    if not host:
        raise ValueError("Укажите адрес/хост для ping.")

    if platform.system().lower() == "windows":
        cmd = ["ping", "-n", str(count), host]
    else:
        cmd = ["ping", "-c", str(count), host]
    return _run_capture(cmd)


def run_dns_check(hostname: str) -> str:
    hostname = hostname.strip()
    if not hostname:
        raise ValueError("Укажите домен для DNS проверки.")

    try:
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            f"Resolve-DnsName -Name '{hostname}' | Format-Table -AutoSize",
        ]
        return _run_capture(cmd)
    except Exception:
        import socket

        infos = socket.getaddrinfo(hostname, None)
        rows = []
        for info in infos:
            addr = info[4][0]
            if addr not in rows:
                rows.append(addr)
        return "\n".join(rows) if rows else "No DNS records found"


def run_netstat() -> str:
    return _run_capture(["netstat", "-ano"])


def flush_dns() -> str:
    if platform.system().lower() == "windows":
        return _run_capture(["ipconfig", "/flushdns"])
    return "Доступно только на Windows."


def reset_tcp_ip() -> str:
    if platform.system().lower() == "windows":
        return _run_capture(["netsh", "int", "ip", "reset"])
    return "Доступно только на Windows."





def parse_visible_wifi_networks(output: str) -> list[str]:
    networks: list[str] = []
    for raw in output.splitlines():
        line = raw.strip()
        if not line or ":" not in line:
            continue
        left, right = [part.strip() for part in line.split(":", 1)]
        label = left.lower()
        if label == "ssid" or label.startswith("ssid "):
            if right and right not in networks:
                networks.append(right)
    return networks


def list_visible_wifi_networks() -> list[str]:
    if platform.system().lower() != "windows":
        return []
    try:
        text = _run_capture(["netsh", "wlan", "show", "networks", "mode=bssid"])
    except Exception:
        return []
    return parse_visible_wifi_networks(text)


def parse_current_wifi_ssid(output: str) -> str | None:
    for raw in output.splitlines():
        line = raw.strip()
        if not line:
            continue
        if ":" not in line:
            continue
        left, right = [part.strip() for part in line.split(":", 1)]
        label = left.lower()
        if label == "ssid" or label.startswith("ssid "):
            if right:
                return right
    return None


def get_current_wifi_ssid() -> str | None:
    if platform.system().lower() != "windows":
        return None
    try:
        text = _run_capture(["netsh", "wlan", "show", "interfaces"])
    except Exception:
        return None
    return parse_current_wifi_ssid(text)


def resolve_profile_for_ssid(settings: dict, ssid: str) -> str | None:
    target = ssid.strip().lower()
    if not target:
        return None

    mappings = settings.get("wifi_mappings", []) if isinstance(settings, dict) else []
    matched: list[dict] = []
    for item in mappings:
        mapped_ssid = str(item.get("ssid", "")).strip().lower()
        if mapped_ssid == target:
            matched.append(item)

    if not matched:
        return None

    for item in matched:
        if bool(item.get("auto", True)):
            profile_name = str(item.get("profile", "")).strip()
            if profile_name:
                return profile_name

    profile_name = str(matched[0].get("profile", "")).strip()
    return profile_name or None


def get_network_snapshot() -> str:
    if platform.system().lower() != "windows":
        return "Доступно только на Windows."

    blocks: List[str] = []
    try:
        text = _run_capture(["ipconfig", "/all"])
        blocks.append("=== ipconfig /all ===")
        blocks.append(text)
    except Exception as exc:
        blocks.append(f"ipconfig error: {exc}")

    try:
        text = _run_capture(["netsh", "interface", "ipv4", "show", "config"])
        blocks.append("\n=== netsh interface ipv4 show config ===")
        blocks.append(text)
    except Exception as exc:
        blocks.append(f"netsh error: {exc}")

    return "\n".join(blocks)
