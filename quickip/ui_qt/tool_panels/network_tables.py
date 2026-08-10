"""Netstat and ARP table panels."""

from __future__ import annotations

import re
import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QStyleFactory,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from quickip.ui_qt.tool_panels.components import (
    ToolStatusKind,
    center_tree_item,
    configure_tool_tree,
    create_tool_button,
    set_tool_busy,
    set_tool_status,
)
from quickip.ui_qt.tool_panels.layout import configure_tool_root
from quickip.ui_qt.palette import semantic_color
from quickip.ui_qt.widgets.copyable_views import (
    CopyableTree,
    tree_selection_stylesheet,
)


class NetstatBridge(QObject):
    rows_ready = Signal(list)
    finished   = Signal(bool, str)


class NetstatPanel(QWidget):
    def __init__(self, dark: bool = True, i18n=None, runner=None) -> None:
        super().__init__()
        self._dark = dark
        self._i18n = i18n
        self._runner = runner
        self._bridge = NetstatBridge()
        self._bridge.rows_ready.connect(self._populate)
        self._bridge.finished.connect(self._on_finished)
        self._cancel_requested = False
        self._filter_mode = (0, "")
        _t = lambda k: i18n.get(k) if i18n else k  # noqa: E731

        root = QVBoxLayout(self)
        configure_tool_root(root)

        self._hdr = QLabel(_t("tools_netstat_title"))
        self._hdr.setObjectName("ToolPanelTitle")
        root.addWidget(self._hdr)

        form = QHBoxLayout()
        form.setSpacing(8)
        self._filter = QComboBox()
        self._filter.setObjectName("ToolCombo")
        self._filter.setFixedHeight(28)
        self._filter.addItems([_t("tools_filter_all"), "TCP", "UDP", "LISTENING", "ESTABLISHED"])
        form.addWidget(self._filter, 0, Qt.AlignmentFlag.AlignVCenter)
        form.addStretch(1)
        root.addLayout(form)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        self.btn_run = create_tool_button(
            self._tr("tools_btn_run"),
            role="primary",
        )
        self.btn_run.clicked.connect(self._on_run)
        self.btn_stop = create_tool_button(
            self._tr("tools_btn_stop"),
        )
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._on_stop)
        self.btn_clear = create_tool_button(
            self._tr("tools_btn_clear"),
        )
        self.btn_clear.clicked.connect(self._clear)
        btn_row.addWidget(self.btn_run, 0, Qt.AlignmentFlag.AlignVCenter)
        btn_row.addWidget(self.btn_stop, 0, Qt.AlignmentFlag.AlignVCenter)
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_clear, 0, Qt.AlignmentFlag.AlignVCenter)
        root.addLayout(btn_row)

        self._table = CopyableTree(i18n=i18n)
        configure_tool_tree(
            self._table,
            dark=dark,
            object_name="NetstatTable",
        )
        self._table.setColumnCount(5)
        self._table.setHeaderLabels(["Протокол", "Локальный", "Удалённый", "Состояние", "PID"])
        self._table.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._table.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.header().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._table.header().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        root.addWidget(self._table, 1)

        self._status = QLabel("")
        self._status.setObjectName("ToolStatus")
        root.addWidget(self._status)

    def _clear(self) -> None:
        self._table.clear()
        set_tool_status(self._status, "")

    def _on_run(self) -> None:
        self._table.clear()
        self._cancel_requested = False
        self._filter_mode = (
            self._filter.currentIndex(),
            self._filter.currentText(),
        )
        set_tool_busy(self.btn_run, True, stop_button=self.btn_stop)
        set_tool_status(
            self._status,
            self._tr("tools_netstat_loading"),
            ToolStatusKind.RUNNING,
        )
        threading.Thread(target=self._worker, daemon=True).start()

    def _on_stop(self) -> None:
        self._cancel_requested = True
        self.btn_stop.setEnabled(False)
        set_tool_status(
            self._status,
            self._tr("tools_status_cancelling"),
            ToolStatusKind.RUNNING,
        )

    def _on_finished(self, ok: bool, msg: str) -> None:
        set_tool_busy(self.btn_run, False, stop_button=self.btn_stop)
        set_tool_status(
            self._status,
            msg,
            ToolStatusKind.SUCCESS if ok else ToolStatusKind.ERROR,
        )

    def _populate(self, rows: list) -> None:
        self._table.setUpdatesEnabled(False)
        for proto, local, remote, state, pid in rows:
            item = QTreeWidgetItem([proto, local, remote, state, pid])
            center_tree_item(item)
            self._table.addTopLevelItem(item)
        self._table.setUpdatesEnabled(True)

    def _worker(self) -> None:
        try:
            result = self._runner.run(["netstat", "-ano"], timeout=15)
            if not result.success:
                raise RuntimeError(
                    (result.stderr or result.stdout).strip()
                    or self._tr("tools_netstat_error")
                )
            filter_index, flt = self._filter_mode
            rows = []
            for line in result.stdout.splitlines():
                parts = line.split()
                if len(parts) < 4:
                    continue
                proto = parts[0].upper()
                if proto not in ("TCP", "UDP"):
                    continue
                if len(parts) == 5:
                    proto, local, remote, state, pid = parts
                elif len(parts) == 4:
                    proto, local, remote, pid = parts
                    state = "—"
                else:
                    continue
                if filter_index != 0:  # 0 = All
                    if flt in ("TCP", "UDP") and proto != flt:
                        continue
                    if flt in ("LISTENING", "ESTABLISHED") and state.upper() != flt:
                        continue
                rows.append((proto, local, remote, state, pid))
            if self._cancel_requested:
                self._bridge.finished.emit(
                    False,
                    self._tr("tools_status_cancelled"),
                )
                return
            self._bridge.rows_ready.emit(rows)
            self._bridge.finished.emit(
                True,
                self._tr("tools_netstat_count").format(count=len(rows)),
            )
        except Exception as e:
            self._bridge.finished.emit(False, str(e))

    def _tr(self, key: str) -> str:
        return self._i18n.get(key) if self._i18n else key

    def retranslate(self) -> None:
        self._hdr.setText(self._tr("tools_netstat_title"))
        cur_idx = self._filter.currentIndex()
        self._filter.blockSignals(True)
        self._filter.setItemText(0, self._tr("tools_filter_all"))
        self._filter.blockSignals(False)
        self._filter.setCurrentIndex(cur_idx)
        self._table.setHeaderLabels([
            self._tr("tools_netstat_col_proto"),
            self._tr("tools_netstat_col_local"),
            self._tr("tools_netstat_col_remote"),
            self._tr("tools_netstat_col_state"),
            "PID",
        ])

    def refresh_theme(self, dark: bool) -> None:
        self._dark = dark
        self._table.setStyleSheet(tree_selection_stylesheet(dark))


class ArpBridge(QObject):
    rows_ready = Signal(list)   # list of (iface, ip, mac, type)
    finished   = Signal(bool, str)


class ArpPanel(QWidget):
    def __init__(self, dark: bool = True, i18n=None, runner=None) -> None:
        super().__init__()
        self._dark = dark
        self._i18n = i18n
        self._runner = runner
        self._bridge = ArpBridge()
        self._bridge.rows_ready.connect(self._on_rows_ready)
        self._bridge.finished.connect(self._on_finished)
        self._build()

    def _tr(self, key: str) -> str:
        return self._i18n.get(key) if self._i18n else key

    def _build(self) -> None:
        root = QVBoxLayout(self)
        configure_tool_root(root)

        self._hdr = QLabel(self._tr("tools_arp_title"))
        self._hdr.setObjectName("ToolPanelTitle")
        root.addWidget(self._hdr)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        self.btn_run = create_tool_button(
            self._tr("tools_btn_run"),
            role="primary",
        )
        self.btn_run.clicked.connect(self._on_run)
        self.btn_clear = create_tool_button(
            self._tr("tools_btn_clear"),
        )
        self.btn_clear.clicked.connect(self._on_clear)
        btn_row.addWidget(self.btn_run, 0, Qt.AlignmentFlag.AlignVCenter)
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_clear, 0, Qt.AlignmentFlag.AlignVCenter)
        root.addLayout(btn_row)

        self._table = CopyableTree(i18n=self._i18n)
        configure_tool_tree(
            self._table,
            dark=self._dark,
            object_name="NetstatTable",
        )
        self._table.setColumnCount(4)
        self._table.setHeaderLabels([
            self._tr("tools_arp_col_ip"),
            self._tr("tools_arp_col_mac"),
            self._tr("tools_arp_col_type"),
            self._tr("tools_arp_col_iface"),
        ])
        self._table.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._table.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._table.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._table.header().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        root.addWidget(self._table, 1)

        self._status = QLabel("")
        self._status.setObjectName("ToolStatus")
        root.addWidget(self._status)

    def retranslate(self) -> None:
        self._hdr.setText(self._tr("tools_arp_title"))
        self.btn_run.setText(self._tr("tools_btn_run"))
        self.btn_clear.setText(self._tr("tools_btn_clear"))
        self._table.setHeaderLabels([
            self._tr("tools_arp_col_ip"),
            self._tr("tools_arp_col_mac"),
            self._tr("tools_arp_col_type"),
            self._tr("tools_arp_col_iface"),
        ])

    def _on_run(self) -> None:
        self._table.clear()
        self._table.setHeaderLabels([
            self._tr("tools_arp_col_ip"),
            self._tr("tools_arp_col_mac"),
            self._tr("tools_arp_col_type"),
            self._tr("tools_arp_col_iface"),
        ])
        set_tool_busy(self.btn_run, True)
        set_tool_status(
            self._status,
            self._tr("tools_arp_loading"),
            ToolStatusKind.RUNNING,
        )
        threading.Thread(target=self._worker, daemon=True).start()

    def _on_clear(self) -> None:
        self._table.clear()
        set_tool_status(self._status, "")

    def _worker(self) -> None:
        try:
            result = self._runner.run(["arp", "-a"], timeout=10)
            if not result.success:
                raise RuntimeError(
                    (result.stderr or result.stdout).strip()
                    or self._tr("tools_arp_error")
                )
            rows = []
            iface = ""
            for line in result.stdout.splitlines():
                # Interface header: "Интерфейс: 192.168.1.1 --- 0x3"
                m_iface = re.match(
                    r"^\s*(?:Interface|Интерфейс)\s*[:：]\s*([\d.]+)", line, re.IGNORECASE
                )
                if m_iface:
                    iface = m_iface.group(1)
                    continue
                # Data row: "  192.168.1.1   aa-bb-cc-dd-ee-ff   динамический"
                m_row = re.match(
                    r"^\s*([\d.]+)\s+([\da-fA-F]{2}[-:][\da-fA-F]{2}[-:][\da-fA-F]{2}"
                    r"[-:][\da-fA-F]{2}[-:][\da-fA-F]{2}[-:][\da-fA-F]{2})\s+(\S+)",
                    line,
                )
                if m_row:
                    rows.append((iface, m_row.group(1), m_row.group(2), m_row.group(3)))
            self._bridge.rows_ready.emit(rows)
            self._bridge.finished.emit(
                True,
                self._tr("tools_arp_count").format(count=len(rows)),
            )
        except Exception as exc:
            self._bridge.finished.emit(False, str(exc))

    def _on_rows_ready(self, rows: list) -> None:
        self._table.clear()
        for iface, ip, mac, kind in rows:
            item = QTreeWidgetItem([ip, mac, kind, iface])
            item.setFont(0, QFont("Consolas", 9))
            item.setFont(1, QFont("Consolas", 9))
            center_tree_item(item)
            self._table.addTopLevelItem(item)
        self._table.resizeColumnToContents(0)
        self._table.resizeColumnToContents(1)
        self._table.resizeColumnToContents(2)

    def _on_finished(self, success: bool, msg: str) -> None:
        set_tool_busy(self.btn_run, False)
        set_tool_status(
            self._status,
            msg,
            ToolStatusKind.SUCCESS if success else ToolStatusKind.ERROR,
        )

    def refresh_theme(self, dark: bool) -> None:
        self._dark = dark
        self._table.setStyleSheet(tree_selection_stylesheet(dark))
