"""NetworkMonitorService — polls the active Wi-Fi SSID and fires NetworkSsidChanged events.

Polling interval is configurable (default 10s). The monitor runs in a daemon thread
and stops gracefully on stop() or when the process exits.

Design notes:
  - Uses the existing WifiService._get_wifi_interface() and netsh wlan show interfaces.
  - Does NOT use Windows WLAN API events (would require win32wifi / comtypes) to keep
    the dependency footprint minimal; polling is sufficient for auto-switch use case.
  - MITRE D3FEND mapping: D3-NTA (Network Traffic Analysis complement).
"""

from __future__ import annotations

import logging
import threading
from typing import Optional, TYPE_CHECKING

from quickip.core.events.types import NetworkSsidChanged

if TYPE_CHECKING:
    from quickip.app.bootstrap import ServiceContainer

logger = logging.getLogger(__name__)

_DEFAULT_POLL_INTERVAL = 10.0  # секунд


class NetworkMonitorService:
    """Polls the active Wi-Fi SSID; publishes NetworkSsidChanged on change.

    Args:
        container:      DI-контейнер (нужен process_runner и event_bus).
        poll_interval:  Интервал опроса в секундах (по умолчанию 10s).
    """

    def __init__(
        self,
        container: "ServiceContainer",
        poll_interval: float = _DEFAULT_POLL_INTERVAL,
    ) -> None:
        self._runner = container.process_runner
        self._bus = container.event_bus
        self._poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._prev_ssid: str = ""
        self._prev_adapter: str = ""

    # ── Public API ────────────────────────────────────────────────

    def start(self) -> None:
        """Запустить мониторинг в daemon-потоке."""
        if self._thread and self._thread.is_alive():
            logger.debug("NetworkMonitorService already running")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="net_monitor",
        )
        self._thread.start()
        logger.info("NetworkMonitorService started (interval=%.0fs)", self._poll_interval)

    def stop(self) -> None:
        """Остановить мониторинг."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=self._poll_interval + 2)
        logger.info("NetworkMonitorService stopped")

    # ── Internal ──────────────────────────────────────────────────

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._poll()
            except Exception:
                logger.exception("NetworkMonitorService poll error")
            self._stop_event.wait(timeout=self._poll_interval)

    def _poll(self) -> None:
        """Один цикл опроса. Публикует событие если SSID изменился."""
        status = self._get_interface_status()
        ssid = status.get("ssid", "")
        adapter = status.get("name", "")
        connected = bool(ssid and status.get("state", "").lower() in
                         ("connected", "подключено"))

        if ssid != self._prev_ssid:
            logger.info(
                "SSID changed: %r → %r (adapter=%r)",
                self._prev_ssid, ssid, adapter,
            )
            self._bus.publish(NetworkSsidChanged(  # type: ignore[arg-type]
                ssid=ssid,
                prev_ssid=self._prev_ssid,
                adapter=adapter or self._prev_adapter,
                connected=connected,
            ))
            self._prev_ssid = ssid
            if adapter:
                self._prev_adapter = adapter

    def _get_interface_status(self) -> dict:
        """Запрашивает текущий статус Wi-Fi через netsh."""
        import re
        result = self._runner.run(
            ["netsh", "wlan", "show", "interfaces"], timeout=10
        )
        if not result.stdout:
            return {}
        fields: dict = {}
        mapping = {
            "name":  r"^(?:Name|Имя)\s*:\s*(.+)$",
            "state": r"^(?:State|Состояние)\s*:\s*(.+)$",
            "ssid":  r"^SSID\s*:\s*(.+)$",
        }
        for line in result.stdout.splitlines():
            stripped = line.strip()
            for key, pattern in mapping.items():
                if key in fields:
                    continue
                m = re.match(pattern, stripped, re.IGNORECASE)
                if m:
                    fields[key] = m.group(1).strip().rstrip(".")
        return fields
