"""Live Wi-Fi signal-monitor panel and graph."""

from __future__ import annotations

import datetime
from html import escape
import re
import threading

from PySide6.QtCore import QObject, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from quickip.features.wifi.netsh_parser import parse_networks
from quickip.features.wifi.presenter import WifiPresenter
from quickip.ui_qt.tool_panels.components import (
    ToolStatusKind,
    center_table_item,
    configure_tool_table_alignment,
    create_tool_button,
    set_tool_busy,
    set_tool_status,
)
from quickip.ui_qt.tool_panels.layout import configure_tool_root
from quickip.ui_qt.widgets.copyable_views import CopyableTable
from quickip.ui_qt.palette import color, semantic_color


def _apply_windows_titlebar_theme(widget: QWidget, dark: bool) -> None:
    """Match the native Windows title bar to the active application theme."""
    try:
        import ctypes

        hwnd = int(widget.winId())
        value = ctypes.c_int(1 if dark else 0)
        dwmapi = ctypes.windll.dwmapi
        # DWMWA_USE_IMMERSIVE_DARK_MODE is 20 on current Windows builds and
        # 19 on some older Windows 10 releases.
        result = dwmapi.DwmSetWindowAttribute(
            hwnd, 20, ctypes.byref(value), ctypes.sizeof(value)
        )
        if result != 0:
            dwmapi.DwmSetWindowAttribute(
                hwnd, 19, ctypes.byref(value), ctypes.sizeof(value)
            )
    except Exception:
        # The application also runs on systems without the Windows DWM API.
        pass


class SignalGraph(QWidget):
    """Живой график уровня сигнала Wi-Fi (dBm)."""
    MAX_POINTS = 60
    LEVELS = [
        (-50, semantic_color("STATUS_SUCCESS")),
        (-65, semantic_color("STATUS_WARNING")),
        (-75, semantic_color("STATUS_ERROR")),
    ]

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._values: list[float] = []
        self._dark = True
        self._empty_text = ""
        self.setMinimumHeight(90)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    @property
    def count(self) -> int:
        return len(self._values)

    def push(self, dbm: float) -> None:
        self._values.append(dbm)
        if len(self._values) > self.MAX_POINTS:
            self._values.pop(0)
        self.update()

    def clear(self) -> None:
        self._values.clear()
        self.update()

    def set_dark(self, dark: bool) -> None:
        self._dark = dark
        self.update()

    def set_empty_text(self, text: str) -> None:
        self._empty_text = text
        self.update()

    def paintEvent(self, _) -> None:  # noqa: N802
        from PySide6.QtCore import QPointF
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            w, h = self.width(), self.height()

            # EN: The graph is a read-only data surface shared with tool results.
            # RU: График — отдельная поверхность данных, как результаты инструментов.
            graph_theme = "dark" if self._dark else "light"
            graph_prefix = "DARK" if self._dark else "LIGHT"
            bg = QColor(color(graph_theme, f"{graph_prefix}_CUSTOM_GRAPH_BG"))
            p.fillRect(0, 0, w, h, bg)

            dbm_min, dbm_max = -100.0, -40.0

            def y_of(dbm: float) -> float:
                return h - (dbm - dbm_min) / (dbm_max - dbm_min) * h

            grid_color = QColor(color(graph_theme, f"{graph_prefix}_CUSTOM_GRAPH_GRID"))
            grid_color.setAlpha(45 if self._dark else 20)
            text_color = QColor(color(graph_theme, f"{graph_prefix}_CUSTOM_GRAPH_TEXT"))
            for lvl in (-50, -60, -70, -80, -90):
                y = y_of(lvl)
                p.setPen(QPen(grid_color, 1, Qt.PenStyle.DashLine))
                p.drawLine(0, int(y), w, int(y))
                p.setPen(text_color)
                p.setFont(QFont("Segoe UI", 8))
                p.drawText(4, int(y) - 2, f"{lvl}")

            if not self._values:
                if self._empty_text:
                    p.setPen(text_color)
                    p.setFont(QFont("Segoe UI", 10))
                    p.drawText(
                        self.rect(),
                        Qt.AlignmentFlag.AlignCenter,
                        self._empty_text,
                    )
                return

            last = self._values[-1]
            if last >= -65:
                line_color = QColor(semantic_color("STATUS_SUCCESS"))
            elif last >= -75:
                line_color = QColor(semantic_color("STATUS_WARNING"))
            else:
                line_color = QColor(semantic_color("STATUS_ERROR"))

            step = w / max(self.MAX_POINTS - 1, 1)
            offset = (self.MAX_POINTS - len(self._values)) * step
            points = [
                QPointF(offset + i * step, y_of(v))
                for i, v in enumerate(self._values)
            ]
            pen = QPen(line_color, 2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            for i in range(len(points) - 1):
                p.drawLine(points[i], points[i + 1])

            p.setBrush(line_color)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(points[-1], 4, 4)
        finally:
            p.end()


class NetworkConnectBridge(QObject):
    finished = Signal(bool, str, bool)


class NetworkConnectDialog(QDialog):
    """Connect to a scanned network and optionally persist its credentials."""

    def __init__(
        self,
        network,
        presenter: WifiPresenter,
        i18n=None,
        parent=None,
        dark: bool = True,
    ) -> None:
        super().__init__(parent)
        self._dark = dark
        self._network = network
        self._presenter = presenter
        self._i18n = i18n
        self._profile = presenter.find_wifi_profile_by_ssid(network.ssid)
        self._bridge = NetworkConnectBridge()
        self._bridge.finished.connect(self._on_finished)
        self.connected_successfully = False

        self.setObjectName("NetworkConnectDialog")
        self.setWindowTitle(self._tr("tools_signal_connect_title"))
        self.setMinimumWidth(460)
        QTimer.singleShot(
            0, lambda: _apply_windows_titlebar_theme(self, self._dark)
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(14)

        title = QLabel(network.ssid)
        title.setObjectName("ToolPanelTitle")
        root.addWidget(title)
        details = QLabel(
            self._tr("tools_signal_connect_details").format(
                security=self._security_text(network),
                signal=network.signal_pct,
            )
        )
        details.setObjectName("ToolStatus")
        root.addWidget(details)

        self._password = QLineEdit()
        self._password.setObjectName("ToolInput")
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._password.setPlaceholderText(self._tr("tools_signal_connect_password"))
        self._password.setClearButtonEnabled(True)
        password_required = not self._is_open(network) and self._profile is None
        self._password.setVisible(password_required)
        if password_required:
            root.addWidget(self._password)

        self._save = QCheckBox(self._tr("tools_signal_connect_save"))
        self._save.setChecked(self._profile is None)
        self._save.setVisible(self._profile is None)
        root.addWidget(self._save)

        self._status = QLabel(
            self._tr("tools_signal_connect_saved_profile") if self._profile else ""
        )
        self._status.setObjectName("ToolStatus")
        self._status.setWordWrap(True)
        root.addWidget(self._status)

        actions = QHBoxLayout()
        actions.addStretch(1)
        cancel = create_tool_button(self._tr("btn_cancel"))
        cancel.clicked.connect(self.reject)
        actions.addWidget(cancel)
        self._connect = create_tool_button(
            self._tr("btn_connect"), role="primary", min_width=140
        )
        self._connect.clicked.connect(self._start_connect)
        actions.addWidget(self._connect)
        root.addLayout(actions)
        self._password.returnPressed.connect(self._start_connect)

    def _tr(self, key: str) -> str:
        return self._i18n.get(key) if self._i18n else key

    @staticmethod
    def _is_open(network) -> bool:
        return (network.auth or "").strip().casefold() in {
            "open", "открытая", "открыто"
        }

    @staticmethod
    def _security_text(network) -> str:
        return " · ".join(
            value for value in (network.auth, network.cipher) if value
        ) or "Open"

    @staticmethod
    def _profile_security(network) -> tuple[str, str]:
        raw_auth = (network.auth or "").strip()
        raw_cipher = (network.cipher or "").strip()
        auth_lower = raw_auth.casefold()
        if auth_lower in {"open", "открытая", "открыто"}:
            return "Open", "None"
        if "wpa3" in auth_lower:
            auth = "WPA3-Personal"
        elif "wpa2" in auth_lower:
            auth = "WPA2-Personal"
        elif "wpa" in auth_lower:
            auth = "WPA-Personal"
        else:
            auth = "WPA2-Personal"
        cipher = "AES" if raw_cipher.casefold() in {"ccmp", "aes", ""} else raw_cipher
        return auth, cipher

    def _start_connect(self) -> None:
        password = self._password.text()
        if not self._profile and not self._is_open(self._network) and not password:
            self._status.setText(self._tr("tools_signal_connect_password_required"))
            self._password.setFocus()
            return
        self._connect.setEnabled(False)
        self._password.setEnabled(False)
        self._save.setEnabled(False)
        self._status.setText(self._tr("tools_signal_connect_progress"))
        threading.Thread(
            target=self._connect_worker,
            args=(password, self._save.isChecked()),
            daemon=True,
            name="nearby_wifi_connect",
        ).start()

    def _connect_worker(self, password: str, save_profile: bool) -> None:
        saved = False
        try:
            if self._profile is not None:
                result = self._presenter.connect_with_profile(
                    self._network.ssid, self._profile
                )
            elif self._is_open(self._network):
                result = self._presenter.connect_open_network(self._network.ssid)
            else:
                auth, cipher = self._profile_security(self._network)
                result = self._presenter.connect_with_ssid(
                    self._network.ssid, password, auth=auth, cipher=cipher
                )
            if result.success and save_profile and self._profile is None:
                auth, cipher = self._profile_security(self._network)
                self._presenter.save_profile(
                    ssid=self._network.ssid,
                    auth=auth,
                    cipher=cipher,
                    password=password,
                    auto_connect=True,
                    connect_hidden=False,
                    is_adhoc=False,
                )
                saved = True
            self._bridge.finished.emit(result.success, result.message, saved)
        except Exception as exc:
            self._bridge.finished.emit(False, str(exc), saved)

    def _on_finished(self, success: bool, message: str, saved: bool) -> None:
        self._connect.setEnabled(True)
        self._password.setEnabled(True)
        self._save.setEnabled(True)
        if not success:
            self._status.setText(message or self._tr("dlg_connect_error_default"))
            return
        self.connected_successfully = True
        suffix = self._tr("tools_signal_connect_profile_saved") if saved else ""
        QMessageBox.information(
            self,
            self._tr("tools_signal_connect_title"),
            "\n".join(part for part in (message, suffix) if part),
        )
        self.accept()


class NearbyNetworksDialog(QDialog):
    """Snapshot of visible Wi-Fi networks with connection actions."""

    def __init__(
        self,
        i18n=None,
        presenter: WifiPresenter | None = None,
        parent=None,
        dark: bool = True,
    ) -> None:
        super().__init__(parent)
        self._dark = dark
        self._i18n = i18n
        self._networks: list = []
        self._visible_networks: list = []
        self._presenter = presenter
        self._active_bssid = ""
        self._last_updated: datetime.datetime | None = None
        self._sort_column = 2
        self._sort_order = Qt.SortOrder.DescendingOrder
        self.setObjectName("NearbyNetworksDialog")
        self.setWindowTitle(self._tr("tools_signal_nearby_title"))
        self.resize(940, 520)
        QTimer.singleShot(
            0, lambda: _apply_windows_titlebar_theme(self, self._dark)
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel(self._tr("tools_signal_nearby_title"))
        title.setObjectName("ToolPanelTitle")
        header.addWidget(title)
        header.addStretch(1)
        self._count = QLabel("")
        self._count.setObjectName("ToolStatus")
        header.addWidget(self._count)
        self._refresh = create_tool_button(
            self._tr("tools_signal_nearby_refresh"),
        )
        header.addWidget(self._refresh)
        root.addLayout(header)

        filters = QHBoxLayout()
        filters.setSpacing(8)
        self._search = QLineEdit()
        self._search.setObjectName("ToolInput")
        self._search.setPlaceholderText(
            self._tr("tools_signal_nearby_search")
        )
        self._search.setClearButtonEnabled(True)
        filters.addWidget(self._search, 1)

        self._band_filter = QComboBox()
        self._band_filter.setObjectName("ToolCombo")
        self._band_filter.addItem(
            self._tr("tools_signal_nearby_band_all"), "all"
        )
        self._band_filter.addItem("2.4 GHz", "2.4")
        self._band_filter.addItem("5 GHz", "5")
        filters.addWidget(self._band_filter)

        self._security_filter = QComboBox()
        self._security_filter.setObjectName("ToolCombo")
        self._security_filter.addItem(
            self._tr("tools_signal_nearby_security_all"), "all"
        )
        self._security_filter.addItem(
            self._tr("tools_signal_nearby_security_open"), "open"
        )
        self._security_filter.addItem(
            self._tr("tools_signal_nearby_security_protected"), "protected"
        )
        filters.addWidget(self._security_filter)
        root.addLayout(filters)

        self._search.textChanged.connect(self._apply_filters)
        self._band_filter.currentIndexChanged.connect(self._apply_filters)
        self._security_filter.currentIndexChanged.connect(self._apply_filters)

        self._table = CopyableTable(0, 6, i18n=i18n)
        self._table.setObjectName("ToolTable")
        self._table.setHorizontalHeaderLabels([
            "SSID",
            "BSSID",
            self._tr("tools_signal_nearby_signal"),
            self._tr("tools_signal_nearby_channel"),
            self._tr("tools_signal_nearby_band"),
            self._tr("tools_signal_nearby_security"),
        ])
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        header_view = self._table.horizontalHeader()
        configure_tool_table_alignment(self._table)
        header_view.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        header_view.setSectionsClickable(True)
        header_view.setSortIndicatorShown(True)
        header_view.setSortIndicator(self._sort_column, self._sort_order)
        header_view.sectionClicked.connect(self._change_sort)
        self._table.itemSelectionChanged.connect(
            self._update_copy_buttons
        )
        self._table.itemDoubleClicked.connect(lambda _item: self._connect_selected())
        root.addWidget(self._table, 1)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self._connect_network = create_tool_button(
            self._tr("btn_connect"), role="primary", min_width=140
        )
        self._connect_network.setEnabled(False)
        self._connect_network.setVisible(self._presenter is not None)
        self._connect_network.clicked.connect(self._connect_selected)
        actions.addWidget(self._connect_network)
        self._copy_ssid = create_tool_button(
            self._tr("tools_signal_nearby_copy_ssid"),
        )
        self._copy_ssid.setEnabled(False)
        self._copy_ssid.clicked.connect(lambda: self._copy_selected(0))
        actions.addWidget(self._copy_ssid)
        self._copy_bssid = create_tool_button(
            self._tr("tools_signal_nearby_copy_bssid"),
        )
        self._copy_bssid.setEnabled(False)
        self._copy_bssid.clicked.connect(lambda: self._copy_selected(1))
        actions.addWidget(self._copy_bssid)
        root.addLayout(actions)

        self._status = QLabel("")
        self._status.setObjectName("ToolStatus")
        root.addWidget(self._status)

    def _tr(self, key: str) -> str:
        return self._i18n.get(key) if self._i18n else key

    def set_loading(self, loading: bool) -> None:
        self._refresh.setEnabled(not loading)
        if loading:
            key = (
                "tools_signal_nearby_updating"
                if self._networks
                else "tools_signal_nearby_scanning"
            )
            self._status.setStyleSheet("")
            self._status.setText(self._tr(key))

    def set_error(self, message: str) -> None:
        self._refresh.setEnabled(True)
        self._status.setStyleSheet(
            f'color:{semantic_color("STATUS_ERROR")};font-size:11px;'
        )
        if self._networks and self._last_updated is not None:
            template = self._tr("tools_signal_nearby_error_cached")
            if "{message}" in template:
                message = template.format(
                    time=self._last_updated.strftime("%H:%M:%S"),
                    message=message,
                )
            else:
                message = f"{template}: {message}"
        self._status.setText(message)

    def set_networks(self, networks: list, active_bssid: str = "") -> None:
        self._refresh.setEnabled(True)
        self._status.setStyleSheet("")
        self._networks = sorted(
            networks,
            key=lambda network: network.signal_pct,
            reverse=True,
        )
        self._active_bssid = active_bssid.strip().casefold()
        self._last_updated = datetime.datetime.now()
        self._apply_filters()

    @staticmethod
    def _is_open_network(network) -> bool:
        authentication = network.auth.strip().casefold()
        return authentication in {"open", "открытая", "открыто"}

    def _filtered_networks(self) -> list:
        query = self._search.text().strip().casefold()
        band_filter = self._band_filter.currentData()
        security_filter = self._security_filter.currentData()
        result = []
        for network in self._networks:
            if query and query not in network.ssid.casefold() and (
                query not in network.bssid.casefold()
            ):
                continue
            if band_filter == "2.4" and network.freq_ghz >= 3.0:
                continue
            if band_filter == "5" and (
                not network.freq_ghz or network.freq_ghz < 3.0
            ):
                continue
            is_open = self._is_open_network(network)
            if security_filter == "open" and not is_open:
                continue
            if security_filter == "protected" and is_open:
                continue
            result.append(network)
        return result

    def _sort_value(self, network):
        if self._sort_column == 0:
            return (network.ssid or "").casefold()
        if self._sort_column == 1:
            return (network.bssid or "").casefold()
        if self._sort_column == 2:
            return network.signal_pct
        if self._sort_column == 3:
            return network.channel or -1
        if self._sort_column == 4:
            return network.freq_ghz or 0.0
        return (network.auth or "").casefold()

    def _sorted_networks(self, networks: list) -> list:
        ordered = sorted(
            networks,
            key=self._sort_value,
            reverse=self._sort_order == Qt.SortOrder.DescendingOrder,
        )
        # The active connection remains visible at the top independently
        # from the selected column and direction.
        return sorted(
            ordered,
            key=lambda network: not (
                self._active_bssid
                and network.bssid.strip().casefold() == self._active_bssid
            ),
        )

    def _change_sort(self, column: int) -> None:
        if column == self._sort_column:
            self._sort_order = (
                Qt.SortOrder.AscendingOrder
                if self._sort_order == Qt.SortOrder.DescendingOrder
                else Qt.SortOrder.DescendingOrder
            )
        else:
            self._sort_column = column
            self._sort_order = (
                Qt.SortOrder.DescendingOrder
                if column in {2, 3, 4}
                else Qt.SortOrder.AscendingOrder
            )
        self._table.horizontalHeader().setSortIndicator(
            self._sort_column,
            self._sort_order,
        )
        self._apply_filters()

    def _update_copy_buttons(self) -> None:
        has_selection = bool(self._table.selectedItems())
        self._connect_network.setEnabled(has_selection and self._presenter is not None)
        self._copy_ssid.setEnabled(has_selection)
        self._copy_bssid.setEnabled(has_selection)

    def _copy_selected(self, column: int) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        item = self._table.item(row, column)
        if item is None:
            return
        value = item.data(Qt.ItemDataRole.UserRole) or item.text()
        QApplication.clipboard().setText(str(value))
        self._status.setText(
            self._tr("tools_signal_nearby_copied").format(value=value)
        )

    def _apply_filters(self, *_args) -> None:
        visible = self._sorted_networks(self._filtered_networks())
        self._visible_networks = visible
        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(visible))
        for row, network in enumerate(visible):
            is_active = bool(
                self._active_bssid
                and network.bssid.strip().casefold() == self._active_bssid
            )
            band = (
                f"{network.freq_ghz:.3f} GHz"
                if network.freq_ghz
                else "—"
            )
            security = " · ".join(
                part for part in (network.auth, network.cipher) if part
            ) or "—"
            ssid = network.ssid or self._tr("tools_signal_nearby_hidden")
            values = (
                f"●  {ssid}" if is_active else ssid,
                network.bssid or "—",
                f"{network.signal_pct}%",
                str(network.channel or "—"),
                band,
                security,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                center_table_item(item)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, ssid)
                elif column == 1:
                    item.setData(
                        Qt.ItemDataRole.UserRole,
                        network.bssid or "",
                    )
                if is_active and column == 0:
                    item.setForeground(QColor(semantic_color("STATUS_SUCCESS")))
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                if column == 2:
                    item.setData(Qt.ItemDataRole.UserRole, network.signal_pct)
                    if network.signal_pct >= 75:
                        item.setForeground(
                            QColor(semantic_color("STATUS_SUCCESS"))
                        )
                    elif network.signal_pct >= 50:
                        item.setForeground(
                            QColor(semantic_color("STATUS_WARNING"))
                        )
                    else:
                        item.setForeground(
                            QColor(semantic_color("STATUS_ERROR"))
                        )
                self._table.setItem(row, column, item)

        self._table.clearSelection()
        self._update_copy_buttons()
        self._count.setText(
            self._tr("tools_signal_nearby_count_filtered").format(
                visible=len(visible),
                total=len(self._networks),
            )
        )
        if not self._networks:
            self._status.setText(self._tr("tools_signal_nearby_empty"))
        elif not visible:
            self._status.setText(
                self._tr("tools_signal_nearby_no_filter_results")
            )
        elif self._last_updated is not None:
            self._status.setText(
                self._tr("tools_signal_nearby_updated_at").format(
                    time=self._last_updated.strftime("%H:%M:%S")
                )
            )

    def _connect_selected(self) -> None:
        row = self._table.currentRow()
        if self._presenter is None or not 0 <= row < len(self._visible_networks):
            return
        network = self._visible_networks[row]
        if not network.ssid:
            self._status.setText(self._tr("tools_signal_connect_hidden_error"))
            return
        dialog = NetworkConnectDialog(
            network,
            self._presenter,
            i18n=self._i18n,
            parent=self,
            dark=self._dark,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._status.setText(
                self._tr("tools_signal_connect_success").format(ssid=network.ssid)
            )



class SignalMonitorBridge(QObject):
    updated = Signal(dict)   # данные опроса
    roam    = Signal(dict)   # событие роуминга
    stopped = Signal()
    networks_ready = Signal(list)
    networks_failed = Signal(str)


class SignalMonitorPanel(QWidget):

    # Порог «слабый сигнал» для учащения опроса
    _WEAK_DBM = -70.0
    _NEARBY_CACHE_SECONDS = 15.0

    def __init__(self, dark: bool = True, i18n=None, runner=None, container=None) -> None:
        super().__init__()
        self._dark = dark
        self._i18n = i18n
        self._runner = runner
        self._wifi_presenter = WifiPresenter(container) if container is not None else None
        self._running = False
        self._stop_event = threading.Event()
        self._bridge = SignalMonitorBridge()
        self._bridge.updated.connect(self._on_update)
        self._bridge.roam.connect(self._on_roam)
        self._bridge.stopped.connect(self._on_stopped)
        self._bridge.networks_ready.connect(self._on_networks_ready)
        self._bridge.networks_failed.connect(self._on_networks_failed)
        self._metric_cards: list[tuple[QFrame, QLabel, QLabel]] = []
        self._nearby_dialog: NearbyNetworksDialog | None = None
        self._network_scan_running = False
        self._last_connected: bool | None = None

        root = QVBoxLayout(self)
        configure_tool_root(root)

        self._hdr = QLabel(self._tr("tools_signal_title"))
        self._hdr.setObjectName("ToolPanelTitle")
        root.addWidget(self._hdr)

        # ── Управление ───────────────────────────────────────────────
        controls = QFrame()
        controls.setObjectName("SignalControlsCard")
        btn_row = QHBoxLayout(controls)
        btn_row.setContentsMargins(14, 12, 14, 12)
        btn_row.setSpacing(6)
        btn_row.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        _t = lambda k: i18n.get(k) if i18n else k  # noqa: E731
        self._btn_start = create_tool_button(
            _t("tools_signal_btn_start"),
            role="primary",
            min_width=110,
            min_height=40,
        )
        self._btn_start.clicked.connect(self._start)
        self._btn_stop = create_tool_button(
            _t("tools_signal_btn_stop"),
            min_width=100,
            min_height=40,
        )
        self._btn_stop.setEnabled(False)
        self._btn_stop.clicked.connect(self._stop)
        btn_row.addWidget(self._btn_start, 0, Qt.AlignmentFlag.AlignVCenter)
        btn_row.addWidget(self._btn_stop, 0, Qt.AlignmentFlag.AlignVCenter)
        self._connection = QLabel(self._tr("tools_signal_idle"))
        self._connection.setObjectName("SignalConnectionBadge")
        self._connection.setTextFormat(Qt.TextFormat.RichText)
        btn_row.addSpacing(8)
        btn_row.addWidget(self._connection)
        btn_row.addStretch(1)
        self._btn_nearby = create_tool_button(
            self._tr("tools_signal_nearby_button"),
            min_width=120,
            min_height=40,
        )
        self._btn_nearby.clicked.connect(self._show_nearby_networks)
        btn_row.addWidget(self._btn_nearby)
        self._btn_clear = create_tool_button(
            self._tr("tools_signal_btn_clear"),
            min_width=120,
            min_height=40,
        )
        self._btn_clear.clicked.connect(self._clear)
        btn_row.addWidget(self._btn_clear)
        root.addWidget(controls)

        # ── Карточки текущих значений ─────────────────────────────────
        cards_frame = QFrame()
        cards_frame.setObjectName("SignalMetricsGrid")
        cards = QGridLayout(cards_frame)
        cards.setContentsMargins(0, 0, 0, 0)
        cards.setSpacing(10)
        for column in range(4):
            cards.setColumnStretch(column, 1)
        self._lbl_ssid   = self._card("SSID",  "—", cards, 0, 0, 2)
        self._lbl_bssid  = self._card("BSSID", "—", cards, 0, 2, 2)
        self._lbl_dbm    = self._card("dBm", "—", cards, 1, 0)
        self._lbl_pct    = self._card("%",   "—", cards, 1, 1)
        self._lbl_ch     = self._card("CH",   "—", cards, 1, 2)
        self._lbl_band   = self._card("Band", "—", cards, 1, 3)
        self._lbl_rx     = self._card("Rx Mbps", "—", cards, 2, 0, 2)
        self._lbl_tx     = self._card("Tx Mbps", "—", cards, 2, 2, 2)
        root.addWidget(cards_frame)

        # ── График ───────────────────────────────────────────────────
        self._graph = SignalGraph()
        self._graph.set_dark(dark)
        self._graph.set_empty_text(self._tr("tools_signal_graph_empty"))
        root.addWidget(self._graph)

        # ── Лог роуминга ──────────────────────────────────────────────
        self._log_label = QLabel(self._tr("tools_signal_roaming_log"))
        self._log_label.setObjectName("ToolPanelTitle")
        self._log_label.setStyleSheet("font-size: 12px;")
        root.addWidget(self._log_label)
        self._log = QTextEdit()
        self._log.setObjectName("ToolOutput")
        self._log.setReadOnly(True)
        self._log.setFont(QFont("Consolas", 9))
        self._log.setMaximumHeight(160)
        root.addWidget(self._log)

        self._status = QLabel("")
        self._status.setObjectName("ToolStatus")
        root.addWidget(self._status)

    # ── Вспомогательный метод карточки ───────────────────────────────

    def _card(
        self,
        label: str,
        value: str,
        layout: QGridLayout,
        row: int,
        column: int,
        column_span: int = 1,
    ) -> QLabel:
        frame = QFrame()
        frame.setObjectName("SignalCard")
        card_theme = "dark" if self._dark else "light"
        card_prefix = "DARK" if self._dark else "LIGHT"
        bg = color(card_theme, f"{card_prefix}_CUSTOM_SIGNAL_CARD_BG")
        frame.setStyleSheet(
            f"QFrame#SignalCard{{background:{bg};border-radius:8px;}}"
            f"QFrame#SignalCard QLabel{{background:transparent;}}"
        )
        col = QVBoxLayout(frame)
        col.setContentsMargins(10, 8, 10, 8)
        col.setSpacing(3)
        lbl_key = QLabel(label)
        key_color = color(card_theme, f"{card_prefix}_CUSTOM_SIGNAL_CARD_KEY")
        lbl_key.setStyleSheet(f"color:{key_color};font-size:10px;font-weight:600;letter-spacing:0.5px;")
        val_color = color(card_theme, f"{card_prefix}_CUSTOM_SIGNAL_CARD_VALUE")
        val_lbl = QLabel(value)
        val_lbl.setObjectName("SignalCardValue")
        val_lbl.setStyleSheet(f"font-size:17px;font-weight:700;color:{val_color};")
        col.addWidget(lbl_key)
        col.addWidget(val_lbl)
        layout.addWidget(frame, row, column, 1, column_span)
        self._metric_cards.append((frame, lbl_key, val_lbl))
        return val_lbl

    def _tr(self, key: str) -> str:
        return self._i18n.get(key) if self._i18n else key

    def retranslate(self) -> None:
        self._hdr.setText(self._tr("tools_signal_title"))
        self._btn_start.setText(self._tr("tools_signal_btn_start"))
        self._btn_stop.setText(self._tr("tools_signal_btn_stop"))
        self._btn_clear.setText(self._tr("tools_signal_btn_clear"))
        self._btn_nearby.setText(self._tr("tools_signal_nearby_button"))
        self._log_label.setText(self._tr("tools_signal_roaming_log"))
        self._graph.set_empty_text(self._tr("tools_signal_graph_empty"))

    # ── Управление ────────────────────────────────────────────────────


    def _nearby_cache_is_fresh(self) -> bool:
        dialog = self._nearby_dialog
        if (
            dialog is None
            or not dialog._networks
            or dialog._last_updated is None
        ):
            return False
        age = (
            datetime.datetime.now() - dialog._last_updated
        ).total_seconds()
        return age < self._NEARBY_CACHE_SECONDS

    def _show_nearby_networks(self) -> None:
        if self._nearby_dialog is None:
            self._nearby_dialog = NearbyNetworksDialog(
                i18n=self._i18n,
                presenter=self._wifi_presenter,
                parent=self,
                dark=self._dark,
            )
            self._nearby_dialog._refresh.clicked.connect(
                self._scan_nearby_networks
            )
        self._nearby_dialog.show()
        self._nearby_dialog.raise_()
        self._nearby_dialog.activateWindow()
        if not self._nearby_cache_is_fresh():
            self._scan_nearby_networks()

    def _scan_nearby_networks(self) -> None:
        if self._network_scan_running:
            return
        if self._runner is None:
            if self._nearby_dialog is not None:
                self._nearby_dialog.set_error(
                    self._tr("tools_signal_runner_error")
                )
            return
        self._network_scan_running = True
        if self._nearby_dialog is not None:
            self._nearby_dialog.set_loading(True)
        threading.Thread(target=self._nearby_scan_worker, daemon=True).start()

    def _nearby_scan_worker(self) -> None:
        try:
            # A scan request may be rejected while Windows still has a valid
            # WLAN snapshot, so the following read result is authoritative.
            self._runner.run(["netsh", "wlan", "scan"], timeout=8)
            result = self._runner.run(
                ["netsh", "wlan", "show", "networks", "mode=bssid"],
                timeout=15,
            )
            if not result.success:
                detail = (result.stderr or result.stdout or "").strip()
                self._bridge.networks_failed.emit(detail)
                return
            self._bridge.networks_ready.emit(
                parse_networks(result.stdout or "")
            )
        except Exception as exc:
            self._bridge.networks_failed.emit(str(exc))

    def _on_networks_ready(self, networks: list) -> None:
        self._network_scan_running = False
        if self._nearby_dialog is not None:
            active_bssid = self._lbl_bssid.text()
            if active_bssid == "—":
                active_bssid = ""
            self._nearby_dialog.set_networks(networks, active_bssid)

    def _on_networks_failed(self, message: str) -> None:
        self._network_scan_running = False
        if self._nearby_dialog is not None:
            fallback = self._tr("tools_signal_nearby_error")
            detail = message.strip() if message else fallback
            self._nearby_dialog.set_error(detail)

    def _start(self) -> None:
        if self._running:
            return
        if self._runner is None:
            set_tool_status(
                self._status,
                self._tr("tools_signal_runner_error"),
                ToolStatusKind.ERROR,
            )
            return
        self._stop_event.clear()
        self._running = True
        set_tool_busy(
            self._btn_start, True, stop_button=self._btn_stop
        )
        self._log.clear()
        self._graph.clear()
        self._last_connected = None
        self._connection.setText(self._tr("tools_signal_polling"))
        threading.Thread(target=self._poll_loop, daemon=True).start()

    def _stop(self) -> None:
        self._running = False
        self._stop_event.set()

    def _clear(self) -> None:
        self._graph.clear()
        self._log.clear()
        set_tool_status(self._status, "")

    def _set_connection_state(self, connected: bool) -> None:
        """Render the Wi-Fi state with an independently colored status dot."""
        label = self._tr(
            "tools_signal_connected"
            if connected
            else "tools_signal_disconnected"
        )
        dot_color = semantic_color(
            "STATUS_SUCCESS" if connected else "TEXT_MUTED_STRONG"
        )
        self._connection.setText(
            f'<span style="color:{dot_color};">●</span>&nbsp;{escape(label)}'
        )

    def _on_stopped(self) -> None:
        set_tool_busy(
            self._btn_start, False, stop_button=self._btn_stop
        )
        self._connection.setText(self._tr("tools_signal_stopped"))
        set_tool_status(
            self._status,
            self._tr("tools_signal_stopped"),
            ToolStatusKind.NEUTRAL,
        )

    # ── Обновление UI ─────────────────────────────────────────────────

    def _append_connection_event(self, connected: bool, data: dict) -> None:
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        if connected:
            message = self._tr("tools_signal_connection_event").format(
                ts=ts,
                ssid=data.get("ssid") or "—",
                bssid=data.get("bssid") or "—",
                dbm=float(data.get("dbm", -100.0)),
            )
        else:
            message = self._tr("tools_signal_disconnection_event").format(ts=ts)
        self._log.append(message)

    def _on_update(self, d: dict) -> None:
        dbm = d.get("dbm", 0.0)
        pct = d.get("signal", 0)
        connected = bool(d.get("connected", False))
        signal_theme = "dark" if self._dark else "light"
        signal_prefix = "DARK" if self._dark else "LIGHT"
        if dbm <= -75:
            dbm_color = semantic_color("STATUS_ERROR")
        elif dbm <= -65:
            dbm_color = semantic_color("STATUS_WARNING")
        else:
            dbm_color = semantic_color("STATUS_SUCCESS")

        val_color = color(signal_theme, f"{signal_prefix}_CUSTOM_SIGNAL_CARD_VALUE")
        val_style = f"font-size:17px;font-weight:700;color:{val_color};"

        self._lbl_dbm.setText(f"{dbm:.0f}" if connected else "—")
        self._lbl_dbm.setStyleSheet(
            f"font-size:17px;font-weight:700;color:"
            f"{dbm_color if connected else val_color};"
        )
        self._lbl_pct.setText(f"{pct}" if connected else "—")
        self._lbl_pct.setStyleSheet(val_style)
        self._lbl_ssid.setText(d.get("ssid", "—"))
        self._lbl_ssid.setStyleSheet(val_style)
        self._lbl_bssid.setText(d.get("bssid", "—"))
        self._lbl_bssid.setStyleSheet(val_style)
        self._lbl_ch.setText(str(d.get("channel", "—")))
        self._lbl_ch.setStyleSheet(val_style)
        self._lbl_band.setText(d.get("band", "—"))
        self._lbl_band.setStyleSheet(val_style)
        self._lbl_rx.setText(str(d.get("rx", "—")))
        self._lbl_rx.setStyleSheet(val_style)
        self._lbl_tx.setText(str(d.get("tx", "—")))
        self._lbl_tx.setStyleSheet(val_style)
        if connected:
            self._graph.push(dbm)
        elif self._last_connected is True:
            # A stale signal line must not look like a live connection.
            self._graph.clear()

        if self._last_connected is None:
            if connected:
                self._append_connection_event(True, d)
        elif connected != self._last_connected:
            self._append_connection_event(connected, d)
        self._last_connected = connected
        self._set_connection_state(connected)
        interval = "1" if connected and dbm < self._WEAK_DBM else "2"
        set_tool_status(
            self._status,
            self._tr("tools_signal_status").format(
                interval=interval, count=self._graph.count
            ),
            ToolStatusKind.RUNNING,
        )

    def _on_roam(self, d: dict) -> None:
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        old_b = d.get("old_bssid", "?")
        new_b = d.get("new_bssid", "?")
        old_dbm = d.get("old_dbm", 0.0)
        new_dbm = d.get("new_dbm", 0.0)
        ms = d.get("ms", "?")
        self._log.append(
            self._tr("tools_signal_roam_event").format(
                ts=ts,
                old_bssid=old_b,
                new_bssid=new_b,
                old_dbm=old_dbm,
                new_dbm=new_dbm,
                ms=ms,
            )
        )
        self._log.append("")

    # ── Фоновый поток ─────────────────────────────────────────────────

    @staticmethod
    def _parse(output: str) -> dict:
        """Парсит вывод netsh wlan show interfaces построчно (EN + RU)."""
        # Строим словарь: нормализованный_ключ -> значение
        kv: dict[str, str] = {}
        for line in output.splitlines():
            if ":" not in line:
                continue
            idx = line.index(":")
            key = line[:idx].strip().lower()
            val = line[idx + 1:].strip()
            if key and val:
                kv[key] = val

        def v(*keys: str) -> str:
            for k in keys:
                if k in kv:
                    return kv[k]
            return ""

        state = v("state", "состояние")
        state_normalized = state.strip().casefold()
        connected = state_normalized in {
            "connected",
            "подключено",
            "подключен",
            "подключена",
        }

        # SSID — ключ "ssid", но не "bssid"
        ssid = ""
        for line in output.splitlines():
            stripped = line.strip()
            if re.match(r"^SSID\s*:", stripped, re.IGNORECASE) and not re.match(r"^BSSID", stripped, re.IGNORECASE):
                ssid = stripped.split(":", 1)[1].strip()
                break

        signal_raw = v("signal", "сигнал").replace("%", "").strip()
        pct = int(signal_raw) if signal_raw.isdigit() else 0
        dbm = (pct / 2.0) - 100.0

        rx_raw = v("receive rate (mbps)", "скорость получения (мбит/с)",
                   "скорость получени", "скорость приема")
        tx_raw = v("transmit rate (mbps)", "скорость передачи (мбит/с)", "скорость передачи")

        radio = v("radio type", "тип радиосвязи", "тип сети")
        channel_raw = v("channel", "канал")
        try:
            ch_num = int(channel_raw)
        except (ValueError, TypeError):
            ch_num = 0
        band_raw = v("диапазон", "band", "frequency band")
        if "5" in band_raw or ch_num > 14:
            band = "5 GHz"
        else:
            band = "2.4 GHz"

        # BSSID — ищем и "BSSID" и "AP BSSID"
        bssid_m = re.search(r"(?:AP\s+)?BSSID\s*:\s*([0-9a-fA-F]{2}(?:[:\-][0-9a-fA-F]{2}){5})",
                            output, re.IGNORECASE)
        bssid = bssid_m.group(1) if bssid_m else ""

        return {
            "ssid":      ssid,
            "bssid":     bssid,
            "signal":    pct,
            "dbm":       dbm,
            "channel":   channel_raw,
            "band":      band,
            "radio":     radio,
            "rx":        rx_raw.split(".")[0] if rx_raw else "—",
            "tx":        tx_raw.split(".")[0] if tx_raw else "—",
            "state":     state,
            "connected": connected,
        }

    def _poll_loop(self) -> None:
        import time
        last_bssid: str = ""
        last_dbm: float = -100.0
        roam_start_ts: float = 0.0

        while self._running:
            try:
                result = self._runner.run(
                    ["netsh", "wlan", "show", "interfaces"], timeout=5,
                )
                d = self._parse(result.stdout)

                if not d.get("connected", False):
                    self._bridge.updated.emit({
                        "dbm": -100.0, "signal": 0,
                        "ssid": self._tr("tools_signal_no_connection"),
                        "bssid": "—", "channel": "—", "band": "—", "rx": "—", "tx": "—",
                        "connected": False,
                    })
                else:
                    bssid = d.get("bssid", "")
                    dbm   = d.get("dbm", -100.0)

                    # Начало потенциального роуминга
                    if dbm < self._WEAK_DBM and roam_start_ts == 0.0:
                        roam_start_ts = time.monotonic()

                    # Событие роуминга
                    if last_bssid and bssid and bssid != last_bssid:
                        ms = int((time.monotonic() - roam_start_ts) * 1000) if roam_start_ts else "?"
                        self._bridge.roam.emit({
                            "old_bssid": last_bssid,
                            "new_bssid": bssid,
                            "old_dbm":   last_dbm,
                            "new_dbm":   dbm,
                            "ms":        ms,
                        })
                        roam_start_ts = 0.0

                    last_bssid = bssid
                    last_dbm   = dbm
                    self._bridge.updated.emit(d)

                    # Учащаем опрос при слабом сигнале, но не чаще 1с
                    # чтобы не мешать WLAN AutoConfig сервису Windows
                    interval = 1.0 if dbm < self._WEAK_DBM else 2.0
                    self._stop_event.wait(interval)
                    continue

            except Exception:
                self._bridge.updated.emit({
                    "dbm": -100.0, "signal": 0,
                    "ssid": self._tr("tools_signal_poll_error"),
                    "bssid": "—", "channel": "—", "band": "—", "rx": "—", "tx": "—",
                    "connected": False,
                })

            self._stop_event.wait(2.0)

        self._bridge.stopped.emit()

    def refresh_theme(self, dark: bool) -> None:
        self._dark = dark
        if self._nearby_dialog is not None:
            self._nearby_dialog._dark = dark
            QTimer.singleShot(
                0,
                lambda: _apply_windows_titlebar_theme(
                    self._nearby_dialog, self._dark
                ),
            )
        self._graph.set_dark(dark)
        card_theme = "dark" if dark else "light"
        card_prefix = "DARK" if dark else "LIGHT"
        bg = color(card_theme, f"{card_prefix}_CUSTOM_SIGNAL_CARD_BG")
        key_color = color(card_theme, f"{card_prefix}_CUSTOM_SIGNAL_CARD_KEY")
        value_color = color(card_theme, f"{card_prefix}_CUSTOM_SIGNAL_CARD_VALUE")
        for frame, key_label, value_label in self._metric_cards:
            frame.setStyleSheet(
                f"QFrame#SignalCard{{background:{bg};border-radius:8px;}}"
                "QFrame#SignalCard QLabel{background:transparent;}"
            )
            key_label.setStyleSheet(
                f"color:{key_color};font-size:10px;font-weight:600;"
                "letter-spacing:0.5px;"
            )
            if value_label is not self._lbl_dbm:
                value_label.setStyleSheet(
                    f"font-size:17px;font-weight:700;color:{value_color};"
                )
