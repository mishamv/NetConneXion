"""Tools page — navigation and composition of diagnostic panels."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from quickip.ui_qt.tool_panels.adapters import IpconfigPanel
from quickip.ui_qt.tool_panels.basic import (
    DnsPanel,
    PingPanel,
    TraceroutePanel,
)
from quickip.ui_qt.tool_panels.dns_cache import DnsCachePanel
from quickip.ui_qt.tool_panels.ip_batch import IpBatchPanel
from quickip.ui_qt.tool_panels.network_tables import ArpPanel, NetstatPanel
from quickip.ui_qt.tool_panels.port_scan import PortScanPanel
from quickip.ui_qt.tool_panels.routes import RouteTablePanel
from quickip.ui_qt.tool_panels.signal_monitor import SignalMonitorPanel
from quickip.ui_qt.tool_panels.subnet import SubnetCalcPanel
from quickip.ui_qt.tool_panels.web_checks import HttpCheckPanel, SslPanel

if TYPE_CHECKING:
    from quickip.app.bootstrap import ServiceContainer


# fmt: (group_name,) for headers, (name, icon) for tools
_TOOLS = [
    ("Диагностика",),
    ("Ping",           "\u25ce"),   # ◎  target
    ("Traceroute",     "\u21ac"),   # ↬  path
    ("DNS Lookup",     "\u2315"),   # ⌕  search
    ("HTTP Check",     "\u21d7"),   # ⇗  request
    ("SSL Cert",       "\u26BF"),   # ⚿  lock
    ("Локальная сеть",),
    ("tools_nav_adapters", "\u2637"),   # ☷  layers
    ("Netstat",        "\u21c4"),   # ⇄  exchange
    ("ARP",            "\u2237"),   # ∷  table
    ("Routes",         "\u21e2"),   # ⇢  route
    ("Signal Monitor", "\u25d4"),   # ◔  signal
    ("Утилиты",),
    ("Port Scan",      "\u22a1"),   # ⊡  scan
    ("DNS Cache",      "\u2338"),   # ⌸  cache
    ("Subnet Calc",    "\u229e"),   # ⊞  grid
    ("tools_nav_ip_batch", "\u2317"),   # ⌗  grid/list
]


class _ToolNavItem(QFrame):
    """Sidebar nav row: accent-bar | icon | name."""

    clicked_sig = Signal()

    def __init__(self, icon: str, name: str) -> None:
        super().__init__()
        self.setObjectName("ToolNavItem")
        # EN: This custom QFrame must explicitly paint its QSS background.
        # RU: Этот пользовательский QFrame должен явно рисовать фон из QSS.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Left accent bar
        self._bar = QFrame()
        self._bar.setObjectName("ToolNavBar")
        self._bar.setFixedWidth(3)
        lay.addWidget(self._bar)

        # Icon label — fixed width so text always aligns
        ico_lbl = QLabel(icon)
        ico_lbl.setObjectName("ToolNavIcon")
        ico_lbl.setFixedWidth(26)
        ico_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(ico_lbl)

        self._name = QLabel(name)
        self._name.setObjectName("ToolNavText")
        lay.addWidget(self._name, 1)

    def set_name(self, name: str) -> None:
        self._name.setText(name)

    def set_active(self, active: bool) -> None:
        state = "true" if active else "false"
        for w in (self, self._bar, self._name):
            w.setProperty("active", state)
            w.style().unpolish(w)
            w.style().polish(w)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked_sig.emit()
        super().mousePressEvent(event)


class ToolsPage(QWidget):

    def __init__(self, container: "ServiceContainer") -> None:
        super().__init__()
        # Stable page selector for theme/QSS rules.
        self.setObjectName("ToolsPage")
        self._container = container
        self._dark = True
        self._build()

    def _build(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("ToolsSidebar")
        sidebar.setFixedWidth(190)
        sb_lay = QVBoxLayout(sidebar)
        sb_lay.setContentsMargins(0, 16, 6, 14)
        sb_lay.setSpacing(1)

        self._nav_items: list[_ToolNavItem] = []
        self._item_panel_map: list[int] = []
        self._group_labels: list[QLabel] = []  # refs for retranslate
        self._nav_i18n: list[tuple[_ToolNavItem, str]] = []  # (item, key) for translatable names
        _i18n_build = self._container.i18n
        panel_idx = 0
        first = True
        for entry in _TOOLS:
            if len(entry) == 1:
                if panel_idx > 0:
                    div = QFrame()
                    div.setObjectName("ToolDivider")
                    div.setFixedHeight(1)
                    sb_lay.addSpacing(6)
                    sb_lay.addWidget(div)
                    sb_lay.addSpacing(4)
                grp = QLabel(entry[0])
                grp.setObjectName("ToolGroupLabel")
                self._group_labels.append(grp)
                sb_lay.addWidget(grp)
                sb_lay.addSpacing(3)
            else:
                name, icon = entry
                # If name is an i18n key, translate it
                display_name = _i18n_build.get(name) if name.startswith("tools_") else name
                item = _ToolNavItem(icon, display_name)
                if name.startswith("tools_"):
                    self._nav_i18n.append((item, name))
                item.set_active(first)
                item.clicked_sig.connect(lambda p=panel_idx: self._switch_tool(p))
                sb_lay.addWidget(item)
                self._nav_items.append(item)
                self._item_panel_map.append(panel_idx)
                panel_idx += 1
                first = False

        sb_lay.addStretch(1)
        root.addWidget(sidebar)

        self._stack = QStackedWidget()
        self._stack.setObjectName("ToolsStack")

        # Order must match tool entries in _TOOLS (excluding group headers)
        _i18n = self._container.i18n
        _runner = self._container.process_runner
        self._panels: list = [
            PingPanel(self._dark, i18n=_i18n, runner=_runner),                              # Диагностика
            TraceroutePanel(self._dark, i18n=_i18n, runner=_runner),
            DnsPanel(self._dark, i18n=_i18n, runner=_runner),
            HttpCheckPanel(self._dark, i18n=_i18n),
            SslPanel(self._dark, i18n=_i18n),
            IpconfigPanel(self._dark, i18n=_i18n, runner=_runner),              # Локальная сеть
            NetstatPanel(self._dark, i18n=_i18n, runner=_runner),
            ArpPanel(self._dark, i18n=_i18n, runner=_runner),
            RouteTablePanel(self._dark, i18n=_i18n, runner=_runner),
            SignalMonitorPanel(
                self._dark,
                i18n=_i18n,
                runner=_runner,
                container=self._container,
            ),
            PortScanPanel(self._dark, i18n=_i18n),                              # Утилиты
            DnsCachePanel(self._dark, i18n=_i18n, runner=_runner),
            SubnetCalcPanel(self._dark, i18n=_i18n),
            IpBatchPanel(self._dark, i18n=_i18n, runner=_runner),
        ]
        for panel in self._panels:
            self._stack.addWidget(panel)

        root.addWidget(self._stack, 1)
        self._switch_tool(0)

    def _switch_tool(self, idx: int) -> None:
        self._stack.setCurrentIndex(idx)
        for item, p_idx in zip(self._nav_items, self._item_panel_map):
            item.set_active(p_idx == idx)

    def refresh_theme(self, dark_mode: bool) -> None:
        self._dark = dark_mode
        for panel in self._panels:
            panel.refresh_theme(dark_mode)

    def retranslate(self) -> None:
        i18n = self._container.i18n
        # Group labels sidebar
        group_keys = ["tools_group_diagnostics", "tools_group_local", "tools_group_utils"]
        for lbl, key in zip(self._group_labels, group_keys):
            lbl.setText(i18n.get(key))
        # Translatable nav item names
        for item, key in self._nav_i18n:
            item.set_name(i18n.get(key))
        # Buttons in all panels
        run_text   = i18n.get("tools_btn_run")
        stop_text  = i18n.get("tools_btn_stop")
        clear_text = i18n.get("tools_btn_clear")
        for panel in self._panels:
            if hasattr(panel, "btn_run"):
                panel.btn_run.setText(run_text)
            if hasattr(panel, "btn_stop"):
                panel.btn_stop.setText(stop_text)
            if hasattr(panel, "btn_clear"):
                panel.btn_clear.setText(clear_text)
            if hasattr(panel, "retranslate"):
                panel.retranslate()

