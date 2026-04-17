"""Tools feature — network scanner service.

Three scan modes:
  ICMP — ping each host (admin-free on Windows via standard ping.exe)
  ARP  — check ARP cache for existing entries
  TCP  — attempt connect on common ports to detect live hosts

Scanning runs in a ThreadPoolExecutor; progress is reported via callbacks
from worker threads. Export to CSV is also supported.
"""

from __future__ import annotations

import csv
import ipaddress
import logging
import os
import socket
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from quickip.infrastructure.system.process_runner import ProcessRunner

logger = logging.getLogger(__name__)

_COMMON_PORTS = [22, 23, 80, 135, 139, 443, 445, 3389, 5900, 8080]
_SCAN_WORKERS = min(32, (os.cpu_count() or 4) * 4)


# ── Enum ──────────────────────────────────────────────────────────────────────

class ScanMode(str, Enum):
    ICMP = "icmp"
    ARP = "arp"
    TCP = "tcp"


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class ScanResult:
    ip: str
    hostname: str
    reachable: bool
    open_ports: List[int] = field(default_factory=list)  # TCP mode only
    latency_ms: float = 0.0                               # ICMP mode only
    mode: str = ScanMode.ICMP


# ── Service ───────────────────────────────────────────────────────────────────

class ScannerService:
    """Scan a subnet or single IP for reachable hosts."""

    def __init__(self, process_runner: "ProcessRunner") -> None:
        self._runner = process_runner
        self._stop_event = threading.Event()

    # ── Public API ────────────────────────────────────────────────

    def scan(
        self,
        target: str,
        mode: ScanMode = ScanMode.ICMP,
        on_progress: Optional[Callable[[int, int, ScanResult], None]] = None,
        on_complete: Optional[Callable[[List[ScanResult]], None]] = None,
    ) -> None:
        """Start scan in a background daemon thread.

        Callbacks are invoked from worker threads — callers must marshal
        to the UI thread themselves (e.g. via ``root.after(0, ...)``.
        """
        self._stop_event.clear()
        t = threading.Thread(
            target=self._run_scan,
            args=(target, mode, on_progress, on_complete),
            daemon=True,
            name="qscanner",
        )
        t.start()

    def stop(self) -> None:
        """Signal the running scan to abort."""
        self._stop_event.set()

    @staticmethod
    def export_csv(results: List[ScanResult], path: str) -> None:
        """Write *results* to a CSV file at *path*."""
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["ip", "hostname", "reachable", "open_ports",
                            "latency_ms", "mode"],
            )
            writer.writeheader()
            for r in results:
                writer.writerow({
                    "ip": r.ip,
                    "hostname": r.hostname,
                    "reachable": r.reachable,
                    "open_ports": ";".join(str(p) for p in r.open_ports),
                    "latency_ms": round(r.latency_ms, 2),
                    "mode": r.mode,
                })

    # ── Internal ──────────────────────────────────────────────────

    def _run_scan(
        self,
        target: str,
        mode: ScanMode,
        on_progress: Optional[Callable],
        on_complete: Optional[Callable],
    ) -> None:
        hosts = self._expand_target(target)
        total = len(hosts)
        results: List[ScanResult] = []

        with ThreadPoolExecutor(max_workers=_SCAN_WORKERS,
                                thread_name_prefix="qscan") as ex:
            fmap = {ex.submit(self._scan_host, ip, mode): ip for ip in hosts}
            done = 0
            for fut in as_completed(fmap):
                if self._stop_event.is_set():
                    ex.shutdown(wait=False, cancel_futures=True)
                    break
                done += 1
                try:
                    r = fut.result()
                    results.append(r)
                    if on_progress:
                        on_progress(done, total, r)
                except Exception:
                    logger.debug("Scan host error", exc_info=True)

        if on_complete:
            on_complete(results)

    @staticmethod
    def _expand_target(target: str) -> List[str]:
        try:
            net = ipaddress.ip_network(target.strip(), strict=False)
            return [str(h) for h in net.hosts()]
        except ValueError:
            return [target.strip()]

    def _scan_host(self, ip: str, mode: ScanMode) -> ScanResult:
        if mode == ScanMode.ICMP:
            return self._icmp_scan(ip)
        if mode == ScanMode.ARP:
            return self._arp_scan(ip)
        return self._tcp_scan(ip)

    def _icmp_scan(self, ip: str) -> ScanResult:
        import time
        t0 = time.perf_counter()
        result = self._runner.run(["ping", "-n", "1", "-w", "1000", ip], timeout=6)
        latency = (time.perf_counter() - t0) * 1000
        reachable = result.success and "TTL=" in result.stdout.upper()
        hostname = self._try_resolve(ip) if reachable else ""
        return ScanResult(
            ip=ip, hostname=hostname, reachable=reachable,
            latency_ms=latency if reachable else 0.0,
            mode=ScanMode.ICMP,
        )

    def _arp_scan(self, ip: str) -> ScanResult:
        result = self._runner.run(["arp", "-a", ip], timeout=5)
        reachable = (
            result.success
            and ip in result.stdout
            and "dynamic" in result.stdout.lower()
        )
        hostname = self._try_resolve(ip) if reachable else ""
        return ScanResult(
            ip=ip, hostname=hostname, reachable=reachable, mode=ScanMode.ARP,
        )

    @staticmethod
    def _tcp_scan(ip: str) -> ScanResult:
        open_ports: List[int] = []
        for port in _COMMON_PORTS:
            try:
                with socket.create_connection((ip, port), timeout=0.5):
                    open_ports.append(port)
            except OSError:
                pass
        reachable = bool(open_ports)
        hostname = ScannerService._try_resolve(ip) if reachable else ""
        return ScanResult(
            ip=ip, hostname=hostname, reachable=reachable,
            open_ports=open_ports, mode=ScanMode.TCP,
        )

    @staticmethod
    def _try_resolve(ip: str) -> str:
        # socket.setdefaulttimeout is process-global — unsafe under concurrent calls.
        # Use concurrent.futures with a 2-second wall-clock timeout instead.
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as _TimeoutError
        try:
            with ThreadPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(socket.gethostbyaddr, ip)
                return fut.result(timeout=2)[0]
        except (OSError, _TimeoutError):
            return ""
