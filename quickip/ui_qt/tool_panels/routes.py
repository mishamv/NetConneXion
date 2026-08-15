"""IPv4 and IPv6 route-table panel."""

from __future__ import annotations

import base64
import json
import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
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
from quickip.ui_qt.widgets.copyable_views import (
    CopyableTree,
    tree_selection_stylesheet,
)


class RouteTableBridge(QObject):
    rows_ready = Signal(list)
    finished   = Signal(bool, str)


class RouteTablePanel(QWidget):
    def __init__(self, dark: bool = True, i18n=None, runner=None) -> None:
        super().__init__()
        self._dark = dark
        self._i18n = i18n
        self._runner = runner
        self._bridge = RouteTableBridge()
        self._bridge.rows_ready.connect(self._populate)
        self._bridge.finished.connect(self._on_finished)
        self._filter_index = 0
        _t = lambda k: i18n.get(k) if i18n else k  # noqa: E731

        root = QVBoxLayout(self)
        configure_tool_root(root)

        self._hdr = QLabel(_t("tools_route_title"))
        self._hdr.setObjectName("ToolPanelTitle")
        root.addWidget(self._hdr)

        form = QHBoxLayout()
        form.setSpacing(8)
        self._filter = QComboBox()
        self._filter.setObjectName("ToolCombo")
        self._filter.setFixedHeight(28)
        self._filter.addItems([_t("tools_route_filter_both"), _t("tools_route_filter_ipv4"), _t("tools_route_filter_ipv6")])
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
        self.btn_clear = create_tool_button(
            self._tr("tools_btn_clear"),
        )
        self.btn_clear.clicked.connect(self._clear)
        btn_row.addWidget(self.btn_run, 0, Qt.AlignmentFlag.AlignVCenter)
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
        self._table.setHeaderLabels([_t("tools_route_col_net"), _t("tools_route_col_mask"), _t("tools_route_col_gw"), _t("tools_route_col_iface"), _t("tools_route_col_metric")])
        hdr = self._table.header()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        root.addWidget(self._table, 1)

        self._status = QLabel("")
        self._status.setObjectName("ToolStatus")
        root.addWidget(self._status)

    def _clear(self) -> None:
        self._table.clear()
        set_tool_status(self._status, "")

    def _on_run(self) -> None:
        self._table.clear()
        self._filter_index = self._filter.currentIndex()
        set_tool_busy(self.btn_run, True)
        set_tool_status(
            self._status,
            self._tr("tools_route_loading"),
            ToolStatusKind.RUNNING,
        )
        threading.Thread(target=self._worker, daemon=True).start()

    def _on_finished(self, ok: bool, msg: str) -> None:
        set_tool_busy(self.btn_run, False)
        set_tool_status(
            self._status,
            msg,
            ToolStatusKind.SUCCESS if ok else ToolStatusKind.ERROR,
        )

    def _populate(self, rows: list) -> None:
        self._table.setUpdatesEnabled(False)
        for row in rows:
            item = QTreeWidgetItem(row)
            center_tree_item(item)
            self._table.addTopLevelItem(item)
        self._table.setUpdatesEnabled(True)

    @staticmethod
    def _clean(s: str) -> str:
        """Оставляет только ASCII-печатные символы из имён адаптеров Windows."""
        return "".join(c for c in s if 0x20 <= ord(c) <= 0x7E).strip()

    def _tr(self, key: str) -> str:
        return self._i18n.get(key) if self._i18n else key

    def retranslate(self) -> None:
        self._hdr.setText(self._tr("tools_route_title"))
        self.btn_run.setText(self._tr("tools_btn_run"))
        self.btn_clear.setText(self._tr("tools_btn_clear"))
        cur_idx = self._filter.currentIndex()
        self._filter.blockSignals(True)
        self._filter.setItemText(0, self._tr("tools_route_filter_both"))
        self._filter.setItemText(1, self._tr("tools_route_filter_ipv4"))
        self._filter.setItemText(2, self._tr("tools_route_filter_ipv6"))
        self._filter.blockSignals(False)
        self._filter.setCurrentIndex(cur_idx)
        self._table.setHeaderLabels([
            self._tr("tools_route_col_net"),
            self._tr("tools_route_col_mask"),
            self._tr("tools_route_col_gw"),
            self._tr("tools_route_col_iface"),
            self._tr("tools_route_col_metric"),
        ])

    def _worker(self) -> None:
        try:
            flt_idx = self._filter_index
            rows: list[list[str]] = []

            if flt_idx != 2:  # not IPv6-only
                # IPv4 маршруты через PowerShell — надёжный парсинг
                ps = (
                    "Get-NetRoute -AddressFamily IPv4 | "
                    "Select-Object DestinationPrefix,NextHop,InterfaceAlias,RouteMetric | "
                    "ConvertTo-Json -Compress"
                )
                enc = base64.b64encode(ps.encode("utf-16-le")).decode("ascii")
                result = self._runner.run(
                    ["powershell", "-NonInteractive", "-EncodedCommand", enc],
                    timeout=15,
                )
                if not result.success:
                    raise RuntimeError(
                        (result.stderr or result.stdout).strip()
                        or self._tr("tools_route_error")
                    )
                if result.stdout.strip():
                    data = json.loads(result.stdout)
                    if isinstance(data, dict):
                        data = [data]
                    for r in data:
                        dest    = r.get("DestinationPrefix", "")
                        gw      = r.get("NextHop", "") or "—"
                        iface   = self._clean(r.get("InterfaceAlias", ""))
                        metric  = str(r.get("RouteMetric", ""))
                        if "/" in dest:
                            net, prefix = dest.split("/", 1)
                        else:
                            net, prefix = dest, ""
                        rows.append([net, f"/{prefix}", gw, iface, metric])

            if flt_idx != 1:  # not IPv4-only
                ps6 = (
                    "Get-NetRoute -AddressFamily IPv6 | "
                    "Select-Object DestinationPrefix,NextHop,InterfaceAlias,RouteMetric | "
                    "ConvertTo-Json -Compress"
                )
                enc6 = base64.b64encode(ps6.encode("utf-16-le")).decode("ascii")
                r6 = self._runner.run(
                    ["powershell", "-NonInteractive", "-EncodedCommand", enc6],
                    timeout=15,
                )
                if not r6.success:
                    raise RuntimeError(
                        (r6.stderr or r6.stdout).strip()
                        or self._tr("tools_route_error")
                    )
                if r6.stdout.strip():
                    data6 = json.loads(r6.stdout)
                    if isinstance(data6, dict):
                        data6 = [data6]
                    for r in data6:
                        dest   = r.get("DestinationPrefix", "")
                        gw     = r.get("NextHop", "") or "—"
                        iface  = self._clean(r.get("InterfaceAlias", ""))
                        metric = str(r.get("RouteMetric", ""))
                        if "/" in dest:
                            net, prefix = dest.split("/", 1)
                        else:
                            net, prefix = dest, ""
                        rows.append([net, f"/{prefix}", gw, iface, metric])

            self._bridge.rows_ready.emit(rows)
            self._bridge.finished.emit(
                True,
                self._tr("tools_route_count").format(count=len(rows)),
            )
        except Exception as e:
            self._bridge.finished.emit(False, str(e))

    def refresh_theme(self, dark: bool) -> None:
        self._dark = dark
        self._table.setStyleSheet(tree_selection_stylesheet(dark))
