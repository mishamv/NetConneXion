"""Tools feature presenter — coordinates the four tool services."""

from __future__ import annotations

import logging
from typing import Callable, List, Optional, TYPE_CHECKING

from quickip.features.tools.repository import ToolsRepository
from quickip.features.tools.services.connections import (
    ConnectionsService, ConnectionEntry,
)
from quickip.features.tools.services.adapters import AdaptersService, AdapterDetail
from quickip.features.tools.services.console import ConsoleService, ConsoleResult
from quickip.features.tools.services.scanner import ScannerService, ScanMode, ScanResult

if TYPE_CHECKING:
    from quickip.app.bootstrap import ServiceContainer

logger = logging.getLogger(__name__)


class ToolsPresenter:
    """Coordinates tool services; all UI callbacks route through here."""

    def __init__(self, container: "ServiceContainer") -> None:
        self._container = container
        self._repo = ToolsRepository()

        runner = container.process_runner
        scan_interval = int(self._repo.get("scan_interval", 2))
        dns_cache_ttl = int(self._repo.get("dns_cache_ttl", 600))

        self._conn_svc = ConnectionsService(
            runner,
            scan_interval=scan_interval,
            dns_cache_ttl=dns_cache_ttl,
        )
        self._adapter_svc = AdaptersService(runner)
        self._console_svc = ConsoleService(runner)
        self._scanner_svc = ScannerService(runner)

        self._view = None

    def bind_view(self, view) -> None:
        self._view = view
        logger.debug("ToolsPresenter bound to view")

    # ── Connections ───────────────────────────────────────────────

    def start_connection_polling(
        self, callback: Callable[[List[ConnectionEntry]], None]
    ) -> None:
        """Begin background polling; *callback* receives fresh data each tick."""
        self._conn_svc.start_polling(callback)

    def stop_connection_polling(self) -> None:
        self._conn_svc.stop_polling()

    def kill_process(self, pid: int, kill_tree: bool = False) -> bool:
        """Kill a process by PID. Returns True on success."""
        return self._conn_svc.kill_process(pid, kill_tree)

    def flush_dns_cache(self) -> None:
        self._conn_svc.flush_dns_cache()

    def set_scan_interval(self, seconds: int) -> None:
        """Persist new polling interval and apply immediately."""
        self._conn_svc.scan_interval = seconds
        self._repo.set("scan_interval", seconds)

    # ── Adapters ──────────────────────────────────────────────────

    def fetch_adapters(self) -> List[AdapterDetail]:
        """Return full adapter details list (synchronous)."""
        return self._adapter_svc.fetch()

    # ── Console ───────────────────────────────────────────────────

    def get_console_tools(self) -> List[str]:
        return self._console_svc.get_tools()

    def get_console_presets(self, tool: str) -> dict:
        return self._console_svc.get_presets(tool)

    def run_console(self, tool: str, target: str = "") -> ConsoleResult:
        """Run a whitelisted diagnostic tool and return its output."""
        return self._console_svc.run(tool, target)

    # ── Scanner ───────────────────────────────────────────────────

    def start_scan(
        self,
        target: str,
        mode: str,
        on_progress: Optional[Callable[[int, int, ScanResult], None]] = None,
        on_complete: Optional[Callable[[List[ScanResult]], None]] = None,
    ) -> None:
        """Launch a background subnet scan."""
        try:
            scan_mode = ScanMode(mode)
        except ValueError:
            scan_mode = ScanMode.ICMP
        self._scanner_svc.scan(target, scan_mode, on_progress, on_complete)

    def stop_scan(self) -> None:
        self._scanner_svc.stop()

    def export_scan_csv(self, results: List[ScanResult], path: str) -> None:
        self._scanner_svc.export_csv(results, path)

    # ── Lifecycle ─────────────────────────────────────────────────

    def on_close(self) -> None:
        """Called by main window on application exit."""
        self._conn_svc.stop_polling()
        self._scanner_svc.stop()
        logger.debug("ToolsPresenter cleaned up")
