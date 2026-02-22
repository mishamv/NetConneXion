"""Tools presenter – ping, DNS, netstat, flush DNS, TCP reset."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from quickip.app.bootstrap import ServiceContainer

logger = logging.getLogger(__name__)


# ── View contract ────────────────────────────────────────────────

class ToolsView(Protocol):
    """Callback interface for the network tools UI panel."""

    def show_tool_output(self, text: str) -> None:
        """Display command output in the tools text widget."""
        ...

    def ask_yes_no(self, title: str, message: str) -> bool:
        ...

    def get_tool_target(self) -> str:
        """Return the target host/IP from the input field."""
        ...


# ── Presenter ────────────────────────────────────────────────────

class ToolsPresenter:
    """Orchestrates network diagnostic tools."""

    def __init__(self, container: "ServiceContainer", view: ToolsView) -> None:
        self.container = container
        self.view = view

    def run_tool(self, tool: str) -> None:
        """
        Execute a network tool and push output to the view.

        Args:
            tool: One of 'ping', 'dns', 'netstat', 'flushdns', 'tcpreset'.
        """
        target = self.view.get_tool_target().strip()
        try:
            if tool == "ping":
                result = self.container.diagnostics.ping(target or "8.8.8.8")
                output = result.stdout

            elif tool == "dns":
                result = self.container.diagnostics.dns_check(target or "google.com")
                output = result.stdout

            elif tool == "netstat":
                result = self.container.diagnostics.netstat()
                output = result.stdout

            elif tool == "flushdns":
                ok = self.view.ask_yes_no(
                    "Подтверждение",
                    "Flush DNS очистит кеш DNS резолвера Windows. "
                    "Временно это может привести к повторным DNS-запросам. Продолжить?",
                )
                if not ok:
                    return
                result = self.container.diagnostics.flush_dns()
                output = result.stdout

            elif tool == "tcpreset":
                ok = self.view.ask_yes_no(
                    "Подтверждение",
                    "TCP/IP reset сбросит параметры TCP/IP стека к значениям по умолчанию. "
                    "Может потребоваться перезагрузка и повторная настройка сети. Продолжить?",
                )
                if not ok:
                    return
                result = self.container.diagnostics.tcp_reset()
                output = result.stdout

            else:
                output = "Неизвестный инструмент."

            self.view.show_tool_output(output)

        except Exception as exc:
            logger.exception(f"Tool '{tool}' failed")
            self.view.show_tool_output(f"Ошибка: {exc}")
