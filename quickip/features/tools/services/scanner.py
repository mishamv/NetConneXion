"""Tools feature — network scanner service.

Three scan modes:
  ICMP — ping each host (admin-free on Windows via standard ping.exe)
  ARP  — check ARP cache for existing entries
  TCP  — attempt connect on common ports to detect live hosts

Scanning runs in a ThreadPoolExecutor; progress is reported via callbacks
from worker threads. Export to CSV is also supported.

Performance notes:
  - Shared _resolver_pool: DNS resolution reuses one executor across all hosts
    instead of spinning up a new ThreadPoolExecutor per IP (was O(n) thread overhead).
  - TCP scan: single bounded pool for all (ip, port) pairs — eliminates per-host
    executor creation and caps peak thread count to _TCP_WORKERS.

Safety limits:
  - MAX_SCAN_HOSTS: /8 or /0 would create 16M+ futures and exhaust memory.
    Default cap is /20 (4 094 hosts). Override with allow_large=True for up to
    MAX_SCAN_HOSTS_EXTENDED (/16, 65 534 hosts) after explicit user confirmation.
  - Futures are submitted lazily via as_completed over a generator, not all at once.
"""

from __future__ import annotations

import csv
import ipaddress
import logging
import os
import socket
import threading
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Iterable, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from quickip.infrastructure.system.process_runner import ProcessRunner

logger = logging.getLogger(__name__)

_COMMON_PORTS = [22, 23, 80, 135, 139, 443, 445, 3389, 5900, 8080]
_SCAN_WORKERS = min(32, (os.cpu_count() or 4) * 4)
# Один bounded pool для всех TCP-проверок (ip, port).
# Заменяет per-host ThreadPoolExecutor(max_workers=10) который при 32 хостах
# создавал пиково 32×10 = 320 потоков + 32 DNS = 352 потока.
_TCP_WORKERS = 64
# Размер пула для DNS-резолвинга: один pool на весь lifetime сервиса.
_DNS_WORKERS = 32

# Лимиты сканирования сети:
#   /20 = 4 094 хостов — дефолт (безопасно)
#   /16 = 65 534 хостов — расширенный режим (требует allow_large=True)
# /8, /0 и т.д. отклоняются всегда (OOM/зависание приложения)
MAX_SCAN_HOSTS = 4_094
MAX_SCAN_HOSTS_EXTENDED = 65_534


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
        # Один shared resolver pool на весь lifetime сервиса.
        # Устраняет создание нового ThreadPoolExecutor на каждый resolve-вызов.
        self._resolver_pool = ThreadPoolExecutor(
            max_workers=_DNS_WORKERS, thread_name_prefix="dns_res"
        )
        # Один shared TCP pool — все (ip, port) пары идут сюда.
        # Заменяет per-host executor который создавал 10×N потоков.
        self._tcp_pool = ThreadPoolExecutor(
            max_workers=_TCP_WORKERS, thread_name_prefix="tcp_chk"
        )

    # ── Public API ────────────────────────────────────────────────

    def scan(
        self,
        target: str,
        mode: ScanMode = ScanMode.ICMP,
        on_progress: Optional[Callable[[int, int, ScanResult], None]] = None,
        on_complete: Optional[Callable[[List[ScanResult]], None]] = None,
        allow_large: bool = False,
    ) -> None:
        """Start scan in a background daemon thread.

        Args:
            target:      IP, CIDR-сеть или hostname.
            mode:        Режим сканирования (ICMP/ARP/TCP).
            on_progress: Вызывается из рабочего потока после каждого хоста.
            on_complete: Вызывается из рабочего потока по завершении.
            allow_large: Разрешить расширенный лимит (до /16, 65 534 хостов).
                         По умолчанию False — лимит /20 (4 094 хостов).

        Raises ValueError через on_complete(error=...) если сеть слишком большая.
        Callbacks вызываются из рабочих потоков — UI должен маршалировать
        к своему потоку (например через Qt signals или root.after).
        """
        self._stop_event.clear()
        t = threading.Thread(
            target=self._run_scan,
            args=(target, mode, on_progress, on_complete, allow_large),
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
        allow_large: bool = False,
    ) -> None:
        try:
            hosts_gen, total = self._expand_target(target, allow_large)
        except ValueError as exc:
            logger.error("Scan rejected: %s", exc)
            if on_complete:
                on_complete([])
            return

        results: List[ScanResult] = []
        done = 0

        with ThreadPoolExecutor(max_workers=_SCAN_WORKERS,
                                thread_name_prefix="qscan") as ex:
            # Lazy submit: не создаём все futures сразу — сеть /16 дала бы
            # 65 534 futures в памяти до начала обработки. Вместо этого
            # submit следующий хост только когда предыдущий завершён.
            pending: dict[Future, str] = {}
            hosts_iter = iter(hosts_gen)
            # Заполняем пул начальными заданиями
            _slots = _SCAN_WORKERS * 2
            for ip in hosts_iter:
                if len(pending) >= _slots:
                    break
                pending[ex.submit(self._scan_host, ip, mode)] = ip

            while pending:
                if self._stop_event.is_set():
                    ex.shutdown(wait=False, cancel_futures=True)
                    break
                for fut in as_completed(list(pending)):
                    pending.pop(fut, None)
                    done += 1
                    try:
                        r = fut.result()
                        results.append(r)
                        if on_progress:
                            on_progress(done, total, r)
                    except Exception:
                        logger.debug("Scan host error", exc_info=True)
                    # Доливаем следующий хост в пул
                    if not self._stop_event.is_set():
                        for ip in hosts_iter:
                            pending[ex.submit(self._scan_host, ip, mode)] = ip
                            break
                    break  # возвращаемся в внешний while

        if on_complete:
            on_complete(results)

    @staticmethod
    def _expand_target(
        target: str,
        allow_large: bool = False,
    ) -> tuple[Iterable[str], int]:
        """Parse *target* into an iterable of IP strings + total count.

        Returns a lazy generator (not a list) to avoid materialising millions
        of strings for large networks.

        Raises:
            ValueError: if the network exceeds the allowed host limit.
        """
        try:
            net = ipaddress.ip_network(target.strip(), strict=False)
        except ValueError:
            # Single host / hostname — not a CIDR network
            return [target.strip()], 1

        # num_addresses includes network + broadcast; hosts() excludes them
        host_count = max(0, net.num_addresses - 2) if net.prefixlen < 31 else net.num_addresses
        limit = MAX_SCAN_HOSTS_EXTENDED if allow_large else MAX_SCAN_HOSTS

        if host_count > limit:
            raise ValueError(
                f"Сеть содержит {host_count:,} адресов. "
                f"Максимально разрешено: {limit:,} ({'расширенный режим' if allow_large else 'стандартный режим'}). "
                f"Уточните диапазон или используйте подсеть /{32 - (limit - 1).bit_length()} и меньше."
            )

        return (str(h) for h in net.hosts()), host_count

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

    def _tcp_scan(self, ip: str) -> ScanResult:
        """TCP-сканирование через shared _tcp_pool.

        Было: per-host ThreadPoolExecutor(max_workers=10) → пик 32×10=320 потоков.
        Стало: все (ip, port) пары идут в один bounded pool (_TCP_WORKERS=64).
        Пиковое число потоков: 64 TCP + 32 DNS + 32 host-scan = 128 вместо 352.
        """
        def _check_port(port: int) -> Optional[int]:
            try:
                with socket.create_connection((ip, port), timeout=0.5):
                    return port
            except OSError:
                return None

        futs = [self._tcp_pool.submit(_check_port, p) for p in _COMMON_PORTS]
        open_ports: List[int] = []
        for fut in futs:
            try:
                r = fut.result(timeout=2.0)
                if r is not None:
                    open_ports.append(r)
            except Exception:
                pass

        open_ports.sort()
        reachable = bool(open_ports)
        hostname = self._try_resolve(ip) if reachable else ""
        return ScanResult(
            ip=ip, hostname=hostname, reachable=reachable,
            open_ports=open_ports, mode=ScanMode.TCP,
        )

    def _try_resolve(self, ip: str) -> str:
        """Резолвит hostname для IP используя shared _resolver_pool.

        Не создаёт новый ThreadPoolExecutor на каждый вызов — ранее это
        генерировало O(n) thread overhead при сканировании подсети.
        """
        from concurrent.futures import TimeoutError as _TimeoutError
        try:
            fut = self._resolver_pool.submit(socket.gethostbyaddr, ip)
            return fut.result(timeout=2)[0]
        except (OSError, _TimeoutError):
            return ""
