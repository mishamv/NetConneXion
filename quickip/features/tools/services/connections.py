"""Tools feature — connections service.

Gathers active TCP/UDP connections, enriches with process info,
provides reverse-DNS lookup with TTL cache, and kill-process helper.
Polling runs on a background threading.Timer (never root.after).
"""

from __future__ import annotations

import json
import logging
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from quickip.infrastructure.system.process_runner import ProcessRunner

logger = logging.getLogger(__name__)

# ── PowerShell queries ─────────────────────────────────────────────────────────

_PS_TCP = (
    "Get-NetTCPConnection | ForEach-Object {"
    "$p = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue;"
    "[PSCustomObject]@{"
    "LocalAddress=$_.LocalAddress;LocalPort=$_.LocalPort;"
    "RemoteAddress=$_.RemoteAddress;RemotePort=$_.RemotePort;"
    "State=$_.State;Protocol='TCP';PID=$_.OwningProcess;"
    "Name=if($p){$p.ProcessName}else{''};"
    "Path=if($p){try{$p.MainModule.FileName}catch{''}}else{''}}}"
    "| ConvertTo-Json -Compress"
)

_PS_UDP = (
    "Get-NetUDPEndpoint | ForEach-Object {"
    "$p = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue;"
    "[PSCustomObject]@{"
    "LocalAddress=$_.LocalAddress;LocalPort=$_.LocalPort;"
    "RemoteAddress='';RemotePort=0;"
    "State='N/A';Protocol='UDP';PID=$_.OwningProcess;"
    "Name=if($p){$p.ProcessName}else{''};"
    "Path=if($p){try{$p.MainModule.FileName}catch{''}}else{''}}}"
    "| ConvertTo-Json -Compress"
)


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class ConnectionEntry:
    pid: int
    process_name: str
    process_path: str
    local_addr: str
    local_port: int
    remote_addr: str
    remote_port: int
    remote_host: str    # filled by reverse DNS, empty initially
    protocol: str       # "TCP" or "UDP"
    state: str          # e.g. "Established", "Listen", "N/A"


# ── DNS cache ─────────────────────────────────────────────────────────────────

class _DnsCache:
    """Thread-safe TTL reverse-DNS cache."""

    def __init__(self, ttl_seconds: int = 600) -> None:
        self._lock = threading.Lock()
        self._store: dict[str, tuple[str, float]] = {}
        self.ttl = ttl_seconds

    def get(self, ip: str) -> Optional[str]:
        with self._lock:
            entry = self._store.get(ip)
            if entry is None:
                return None
            host, expires = entry
            if time.monotonic() < expires:
                return host
            del self._store[ip]
            return None

    def put(self, ip: str, host: str) -> None:
        with self._lock:
            self._store[ip] = (host, time.monotonic() + self.ttl)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


# ── Service ───────────────────────────────────────────────────────────────────

class ConnectionsService:
    """Fetches active network connections and manages background polling."""

    def __init__(
        self,
        process_runner: "ProcessRunner",
        scan_interval: int = 2,
        dns_cache_ttl: int = 600,
    ) -> None:
        self._runner = process_runner
        self._scan_interval = max(1, scan_interval)
        self._dns_cache = _DnsCache(dns_cache_ttl)
        self._timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()
        self._running = False
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="qdns")

    # ── Public API ────────────────────────────────────────────────

    @property
    def scan_interval(self) -> int:
        return self._scan_interval

    @scan_interval.setter
    def scan_interval(self, value: int) -> None:
        self._scan_interval = max(1, value)

    def fetch_once(self) -> List[ConnectionEntry]:
        """Return current TCP + UDP connections enriched with reverse DNS."""
        entries = self._fetch_tcp() + self._fetch_udp()
        self._enrich_dns(entries)
        return entries

    def start_polling(
        self, callback: Callable[[List[ConnectionEntry]], None]
    ) -> None:
        """Start background polling; *callback* is called from worker thread."""
        with self._lock:
            if self._running:
                return
            self._running = True
        # Run first poll in a daemon thread so the UI is never blocked
        t = threading.Thread(
            target=self._schedule, args=(callback,),
            daemon=True, name="conn_poll_0",
        )
        t.start()

    def stop_polling(self) -> None:
        """Stop background polling."""
        with self._lock:
            self._running = False
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None

    def kill_process(self, pid: int, kill_tree: bool = False) -> bool:
        """Kill process by PID. Returns True on success."""
        cmd = ["taskkill", "/PID", str(pid), "/F"]
        if kill_tree:
            cmd.insert(3, "/T")
        result = self._runner.run(cmd, timeout=10)
        if result.success:
            logger.info("Killed PID %s (tree=%s)", pid, kill_tree)
        else:
            logger.warning("Kill PID %s failed: %s", pid, result.stderr[:80])
        return result.success

    def flush_dns_cache(self) -> None:
        """Clear the reverse-DNS TTL cache."""
        self._dns_cache.clear()

    # ── Internal ──────────────────────────────────────────────────

    def _schedule(self, callback: Callable) -> None:
        if not self._running:
            return
        try:
            entries = self.fetch_once()
            callback(entries)
        except Exception:
            logger.exception("ConnectionsService poll error")
        with self._lock:
            if self._running:
                t = threading.Timer(
                    self._scan_interval, self._schedule, args=(callback,)
                )
                t.daemon = True
                t.start()
                self._timer = t

    def _fetch_tcp(self) -> List[ConnectionEntry]:
        result = self._runner.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS_TCP],
            timeout=15,
        )
        return self._parse_ps(result.stdout) if result.success else []

    def _fetch_udp(self) -> List[ConnectionEntry]:
        result = self._runner.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS_UDP],
            timeout=15,
        )
        return self._parse_ps(result.stdout) if result.success else []

    @staticmethod
    def _parse_ps(raw: str) -> List[ConnectionEntry]:
        raw = raw.strip()
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if isinstance(data, dict):
            data = [data]
        out: List[ConnectionEntry] = []
        for row in data:
            try:
                out.append(ConnectionEntry(
                    pid=int(row.get("PID", 0)),
                    process_name=str(row.get("Name", "")),
                    process_path=str(row.get("Path", "")),
                    local_addr=str(row.get("LocalAddress", "")),
                    local_port=int(row.get("LocalPort", 0)),
                    remote_addr=str(row.get("RemoteAddress", "")),
                    remote_port=int(row.get("RemotePort", 0)),
                    remote_host="",
                    protocol=str(row.get("Protocol", "TCP")),
                    state=str(row.get("State", "N/A")),
                ))
            except Exception:
                continue
        return out

    def _enrich_dns(self, entries: List[ConnectionEntry]) -> None:
        """Fill remote_host via reverse DNS (cached, parallel lookups)."""
        unique_ips = {
            e.remote_addr for e in entries
            if e.remote_addr and e.remote_addr not in ("", "::", "0.0.0.0")
        }
        miss = [ip for ip in unique_ips if self._dns_cache.get(ip) is None]
        if miss:
            futures = {ip: self._executor.submit(self._resolve, ip) for ip in miss}
            for ip, fut in futures.items():
                try:
                    host = fut.result(timeout=2)
                    self._dns_cache.put(ip, host)
                except Exception:
                    self._dns_cache.put(ip, ip)
        for e in entries:
            cached = self._dns_cache.get(e.remote_addr)
            if cached:
                e.remote_host = cached

    @staticmethod
    def _resolve(ip: str) -> str:
        try:
            return socket.gethostbyaddr(ip)[0]
        except OSError:
            return ip
