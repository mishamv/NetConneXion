"""Wi-Fi page — scan networks, connect, manage saved profiles."""

from __future__ import annotations

import threading
from typing import Optional, TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer, Signal, QObject, QRectF, QPoint, QSize
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea, QSizePolicy,
    QApplication, QMenu, QStyledItemDelegate, QTabWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from quickip.features.wifi.presenter import WifiPresenter
from quickip.features.wifi.repository import AUTH_OPTIONS, CIPHER_OPTIONS

if TYPE_CHECKING:
    from quickip.app.bootstrap import ServiceContainer


class _WifiBridge(QObject):
    """Emits signals from background threads into the Qt main thread."""
    scan_done       = Signal(list)
    status_updated  = Signal(dict)
    connect_done    = Signal(bool, str)
    disconnect_done = Signal(bool, str)


class _SignalDelegate(QStyledItemDelegate):
    """Рисует иконку Wi-Fi сигнала (дуги) + процент в ячейке таблицы."""

    def paint(self, painter: QPainter, option, index) -> None:
        pct = index.data(Qt.ItemDataRole.UserRole + 1)
        if pct is None:
            super().paint(painter, option, index)
            return

        from PySide6.QtWidgets import QStyle
        painter.save()
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            # Фон выделения
            if option.state & QStyle.StateFlag.State_Selected:
                painter.fillRect(option.rect, option.palette.highlight())

            cx = option.rect.x() + 20
            cy = option.rect.y() + option.rect.height() - 6

            # Цвет по уровню сигнала
            if pct >= 70:
                color = QColor("#22C55E")
            elif pct >= 45:
                color = QColor("#F59E0B")
            else:
                color = QColor("#EF4444")

            dim = QColor(color)
            dim.setAlpha(45)

            # 4 дуги снаружи внутрь
            arcs = [
                (12, pct >= 70),
                (8,  pct >= 45),
                (5,  pct >= 20),
                (2,  True),
            ]
            for radius, active in arcs:
                pen = QPen(color if active else dim, 1.6)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(pen)
                if radius == 2:
                    painter.setBrush(color if active else dim)
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawEllipse(cx - 2, cy - 2, 4, 4)
                else:
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    rect = QRectF(cx - radius, cy - radius, radius * 2, radius * 2)
                    painter.drawArc(rect, 30 * 16, 120 * 16)

            # Текст %
            painter.setPen(color)
            f = QFont("Segoe UI", 9)
            painter.setFont(f)
            text_rect = option.rect.adjusted(36, 0, 0, 0)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, f"{pct}%")
        finally:
            painter.restore()

    def sizeHint(self, option, index) -> QSize:
        return QSize(72, 34)


class WifiPage(QWidget):
    """Страница Wi-Fi: список сетей слева + менеджер профилей справа."""

    def __init__(self, container: "ServiceContainer") -> None:
        super().__init__()
        self._container = container
        self._presenter = WifiPresenter(container)
        self._bridge = _WifiBridge()
        self._dark_mode = True
        self._selected_profile_id: Optional[str] = None
        self._scanning = False
        self._scan_queued = False
        self._shown_once = False
        self._last_connect_ssid: str = ""
        self._last_connect_password: str = ""
        self._current_ssid: str = ""

        self._status_timer = QTimer(self)
        self._status_timer.setInterval(5000)
        self._status_timer.timeout.connect(self._poll_status)

        self._build_ui()
        self._connect_signals()
        self._poll_status()
        self._status_timer.start()

        # Migrate any legacy b64: profiles to DPAPI/keyring on startup (T1555.004)
        threading.Thread(
            target=self._presenter.migrate_legacy_profiles,
            daemon=True,
            name="wifi_b64_migrate",
        ).start()

    # ── Build UI ──────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._tabs = QTabWidget()
        self._tabs.setObjectName("WifiTabs")
        self._tabs.setDocumentMode(True)
        self._tabs.currentChanged.connect(self._on_tab_changed)

        # Вкладка 1: Networks
        self._left = QFrame()
        self._left.setObjectName("WifiTopPanel")
        self._left.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._build_left()
        self._tabs.addTab(self._left, "Сети")

        # Вкладка 2: Saved profiles
        self._right = QFrame()
        self._right.setObjectName("WifiBottomPanel")
        self._right.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._build_right()
        self._tabs.addTab(self._right, "Сохранённые профили")

        root.addWidget(self._tabs, 1)

    def _build_left(self) -> None:
        lay = QVBoxLayout(self._left)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Header
        hdr = QFrame()
        hdr.setObjectName("PanelHeader")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(13, 10, 13, 8)
        t = QLabel("Wi-Fi сети")
        t.setObjectName("PanelTitle")
        self._lbl_networks_title = t
        hl.addWidget(t)
        hl.addStretch(1)
        self._net_count = QLabel("0")
        self._net_count.setObjectName("CountPill")
        hl.addWidget(self._net_count)
        lay.addWidget(hdr)

        # Status bar
        sf = QFrame()
        sf.setObjectName("WifiStatusBar")
        sv = QVBoxLayout(sf)
        sv.setContentsMargins(13, 8, 13, 8)
        sv.setSpacing(3)
        # Первая строка: dot + SSID
        row1 = QHBoxLayout()
        row1.setSpacing(8)
        row1.setContentsMargins(0, 0, 0, 0)
        self._status_dot = QLabel("\u25cf")
        self._status_dot.setObjectName("StatusDot")
        self._status_dot.setFixedWidth(14)
        row1.addWidget(self._status_dot)
        self._status_label = QLabel("Проверка...")
        self._status_label.setObjectName("WifiStatusLabel")
        row1.addWidget(self._status_label, 1)
        sv.addLayout(row1)
        # Вторая строка: IP, шлюз, DNS
        self._status_details = QLabel("")
        self._status_details.setObjectName("WifiStatusDetails")
        self._status_details.setVisible(False)
        sv.addWidget(self._status_details)
        lay.addWidget(sf)

        # Network table
        self._net_table = QTableWidget()
        self._net_table.setObjectName("WifiNetworkTable")
        self._net_table.setColumnCount(8)
        self._net_table.setHorizontalHeaderLabels(
            ["Сигнал", "SSID", "MAC", "Шифрование", "Канал", "ГГц", "Мбит/с", "Протокол"]
        )
        hh = self._net_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)             # Signal+%
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)           # SSID
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)             # MAC
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Encryption
        hh.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)             # Channel
        hh.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)             # GHz
        hh.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)             # Mbps
        hh.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)  # Protocol
        self._net_table.setColumnWidth(0, 76)   # Signal icon + %
        self._net_table.setColumnWidth(2, 130)  # MAC
        self._net_table.setColumnWidth(4, 60)   # Channel
        self._net_table.setColumnWidth(5, 60)   # GHz
        self._net_table.setColumnWidth(6, 55)   # Mbps
        # Делегат рисует иконку + % в одной колонке
        self._signal_delegate = _SignalDelegate(self._net_table)
        self._net_table.setItemDelegateForColumn(0, self._signal_delegate)
        self._net_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._net_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._net_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._net_table.verticalHeader().setVisible(False)
        self._net_table.setShowGrid(False)
        self._net_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._net_table.setSortingEnabled(True)
        self._net_table.horizontalHeader().setSortIndicatorShown(True)
        self._net_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._net_table.customContextMenuRequested.connect(self._on_network_context_menu)
        self._net_table.setMinimumHeight(160)
        self._net_table.setItemDelegateForColumn(0, _SignalDelegate(self._net_table))
        lay.addWidget(self._net_table, 1)

        # Actions
        actions = QFrame()
        actions.setObjectName("ActionsBlock")
        al = QHBoxLayout(actions)
        al.setContentsMargins(10, 8, 10, 14)
        al.setSpacing(6)
        _f = QFont("Segoe UI", 10)
        _f.setWeight(QFont.Weight.DemiBold)

        self.btn_scan = QPushButton("↺  Сканировать")
        self.btn_scan.setProperty("role", "action")
        self.btn_scan.setFixedHeight(28)
        self.btn_scan.setFont(_f)

        self.btn_connect = QPushButton("▶  Подключить")
        self.btn_connect.setProperty("role", "primary")
        self.btn_connect.setFixedHeight(28)
        self.btn_connect.setFont(_f)

        self.btn_disconnect = QPushButton("■  Отключить")
        self.btn_disconnect.setProperty("role", "action")
        self.btn_disconnect.setFixedHeight(28)
        self.btn_disconnect.setFont(_f)

        al.addWidget(self.btn_scan)
        al.addWidget(self.btn_connect)
        al.addWidget(self.btn_disconnect)
        lay.addWidget(actions)

        # Feedback label для результатов connect/disconnect/scan
        self._net_feedback = QLabel("")
        self._net_feedback.setObjectName("WifiFeedback")
        self._net_feedback.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._net_feedback.setFixedHeight(24)
        lay.addWidget(self._net_feedback)

    def _build_right(self) -> None:
        lay = QVBoxLayout(self._right)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Header with buttons
        # Toolbar с кнопками и счётчиком
        toolbar = QFrame()
        toolbar.setObjectName("WifiProfileToolbar")
        tbl = QHBoxLayout(toolbar)
        tbl.setContentsMargins(14, 8, 14, 8)
        tbl.setSpacing(6)
        tbl.addStretch(1)

        _f = QFont("Segoe UI", 10)
        _f.setWeight(QFont.Weight.DemiBold)

        self.btn_new_profile = QPushButton("＋  Новый")
        self.btn_new_profile.setProperty("role", "primary")
        self.btn_new_profile.setFixedSize(85, 28)
        self.btn_new_profile.setFont(_f)

        self.btn_delete_profile = QPushButton("✕  Удалить")
        self.btn_delete_profile.setProperty("role", "delete")
        self.btn_delete_profile.setFixedSize(90, 28)
        self.btn_delete_profile.setFont(_f)

        self.btn_save_profile = QPushButton("✓  Сохранить")
        self.btn_save_profile.setObjectName("BtnSave")
        self.btn_save_profile.setProperty("role", "action")
        self.btn_save_profile.setFixedSize(120, 28)
        self.btn_save_profile.setFont(_f)

        tbl.addWidget(self.btn_new_profile)
        tbl.addWidget(self.btn_delete_profile)
        tbl.addWidget(self.btn_save_profile)
        lay.addWidget(toolbar)

        # Scrollable content
        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(14, 12, 14, 12)
        cl.setSpacing(12)

        # Saved profiles list
        self._profile_list = QTableWidget()
        self._profile_list.setObjectName("WifiProfileTable")
        self._profile_list.setColumnCount(3)
        self._profile_list.setHorizontalHeaderLabels(["SSID", "Аутентиф.", "Авто"])
        ph = self._profile_list.horizontalHeader()
        ph.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        ph.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        ph.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self._profile_list.setColumnWidth(2, 60)
        self._profile_list.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._profile_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._profile_list.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._profile_list.verticalHeader().setVisible(False)
        self._profile_list.setShowGrid(False)
        self._profile_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        cl.addWidget(self._profile_list)

        # Editor card
        editor = QFrame()
        editor.setObjectName("SectionCard")
        el = QVBoxLayout(editor)
        el.setContentsMargins(18, 14, 18, 16)
        el.setSpacing(10)

        # Section title
        tr = QHBoxLayout()
        tr.setSpacing(8)
        st = QLabel("РЕДАКТОР ПРОФИЛЯ")
        st.setObjectName("SectionTitle")
        self._lbl_editor_title = st
        tr.addWidget(st)
        ln = QFrame()
        ln.setObjectName("SectionLine")
        ln.setFrameShape(QFrame.Shape.HLine)
        tr.addWidget(ln, 1)
        el.addLayout(tr)

        # Fields grid
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(9)
        grid.setColumnMinimumWidth(0, 110)
        grid.setColumnStretch(1, 1)

        def _lbl(text):
            lbl = QLabel(text)
            lbl.setObjectName("FieldLabel")
            return lbl

        self._ed_ssid = QLineEdit()
        self._ed_ssid.setObjectName("EditorField")
        self._ed_ssid.setPlaceholderText("Имя сети")
        self._lbl_wifi_ssid = _lbl("SSID")
        grid.addWidget(self._lbl_wifi_ssid, 0, 0)
        grid.addWidget(self._ed_ssid, 0, 1)

        self._ed_auth = QComboBox()
        self._ed_auth.setObjectName("EditorCombo")
        self._ed_auth.addItems(AUTH_OPTIONS)
        self._ed_auth.setCurrentText("WPA2-Personal")
        self._lbl_wifi_security = _lbl("Безопасность")
        grid.addWidget(self._lbl_wifi_security, 1, 0)
        grid.addWidget(self._ed_auth, 1, 1)

        self._ed_cipher = QComboBox()
        self._ed_cipher.setObjectName("EditorCombo")
        self._ed_cipher.addItems(["AES"])
        self._lbl_wifi_enc = _lbl("Шифрование")
        grid.addWidget(self._lbl_wifi_enc, 2, 0)
        grid.addWidget(self._ed_cipher, 2, 1)

        self._ed_password = QLineEdit()
        self._ed_password.setObjectName("EditorField")
        self._ed_password.setEchoMode(QLineEdit.EchoMode.Password)
        self._ed_password.setPlaceholderText("Введите пароль")
        self._lbl_wifi_password = _lbl("Пароль")
        grid.addWidget(self._lbl_wifi_password, 3, 0)
        grid.addWidget(self._ed_password, 3, 1)

        el.addLayout(grid)

        checks = QHBoxLayout()
        checks.setSpacing(20)
        self._ed_auto = QCheckBox("Авто-подключение")
        self._ed_auto.setChecked(True)
        self._ed_hidden = QCheckBox("Скрытая сеть")
        checks.addWidget(self._ed_auto)
        checks.addWidget(self._ed_hidden)
        checks.addStretch(1)
        el.addLayout(checks)

        cl.addWidget(editor, 1)

        self._feedback = QLabel("")
        self._feedback.setObjectName("WifiFeedback")
        self._feedback.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(self._feedback)

        scroll = QScrollArea()
        scroll.setObjectName("EditorScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        lay.addWidget(scroll, 1)

    # ── Signals ───────────────────────────────────────────────────

    def _connect_signals(self) -> None:
        self.btn_scan.clicked.connect(self._on_scan)
        self.btn_connect.clicked.connect(self._on_connect)
        self.btn_disconnect.clicked.connect(self._on_disconnect)
        self.btn_new_profile.clicked.connect(self._on_new_profile)
        self.btn_save_profile.clicked.connect(self._on_save_profile)
        self.btn_delete_profile.clicked.connect(self._on_delete_profile)
        self._net_table.itemSelectionChanged.connect(self._on_network_selected)
        self._net_table.itemDoubleClicked.connect(self._on_network_double_click)
        self._profile_list.itemSelectionChanged.connect(self._on_profile_selected)
        self._ed_auth.currentTextChanged.connect(self._on_auth_changed)
        self._bridge.scan_done.connect(self._render_networks)
        self._bridge.status_updated.connect(self._render_status)
        self._bridge.connect_done.connect(self._on_connect_result)
        self._bridge.disconnect_done.connect(self._on_disconnect_result)
        self._load_profiles()

    # ── Scan ──────────────────────────────────────────────────────

    def _on_scan(self) -> None:
        if self._scanning:
            return
        self._scanning = True
        self.btn_scan.setEnabled(False)
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _launch_queued_scan(self) -> None:
        """Вызывается таймером после перехода на вкладку Networks."""
        self._scan_queued = False
        self._scanning = False
        self._on_scan()

    def trigger_scan(self) -> None:
        """Запускает сканирование принудительно (вызывается извне)."""
        self._scanning = False  # сбрасываем флаг чтобы не блокировать
        self._on_scan()

    def _scan_worker(self) -> None:
        try:
            nets = self._presenter.scan_networks()
            import logging
            logging.getLogger(__name__).info(f"Scan complete: {len(nets)} networks found")
            self._bridge.scan_done.emit(nets)
        except Exception:
            import traceback
            import logging
            logging.getLogger(__name__).error(f"Scan error: {traceback.format_exc()}")
            self._bridge.scan_done.emit([])

    def _render_networks(self, networks: list) -> None:
        self._scanning = False
        if not getattr(self, "_scan_queued", False):
            self.btn_scan.setText(self._tr("btn_scan"))
            self.btn_scan.setEnabled(True)
        self._net_count.setText(str(len(networks)))
        if not networks:
            self._net_feedback.setText("Сети не найдены")
            self._net_feedback.setStyleSheet("color: #94A3B8; font-size: 12px;")
            QTimer.singleShot(3000, lambda: self._net_feedback.setText(""))
            self._net_table.setRowCount(0)
            return

        sorted_nets = sorted(networks, key=lambda n: -n.signal_pct)

        # Отключаем сортировку на время обновления — без неё нет перестановки строк
        self._net_table.setSortingEnabled(False)

        # Блокируем перерисовку — таблица обновится одним кадром
        self._net_table.setUpdatesEnabled(False)
        try:
            new_count = len(sorted_nets)
            old_count = self._net_table.rowCount()

            # Обновляем существующие строки или добавляем новые
            for r, net in enumerate(sorted_nets):
                if r >= old_count:
                    self._net_table.insertRow(r)
                    self._net_table.setRowHeight(r, 34)

                ssid_text = net.ssid or "(hidden)"
                if net.freq_ghz and net.freq_ghz >= 5.0:
                    ssid_text += "  (5 GHz)"

                enc = f"{net.auth} - {net.cipher}" if net.auth and net.cipher else net.auth or "\u2014"
                auth_lower = (net.auth or "").lower()
                if "open" in auth_lower or "wep" in auth_lower:
                    enc_color = QColor("#EF4444")
                elif "wpa3" in auth_lower:
                    enc_color = QColor("#22C55E")
                else:
                    enc_color = None

                def _item(text, align=None):
                    it = QTableWidgetItem(text)
                    if align:
                        it.setTextAlignment(align)
                    return it

                # Col 0: Signal
                sig = _item("")
                sig.setData(Qt.ItemDataRole.UserRole, net.ssid)
                sig.setData(Qt.ItemDataRole.UserRole + 1, net.signal_pct)
                self._net_table.setItem(r, 0, sig)
                # Col 1: SSID
                si = _item(ssid_text)
                si.setData(Qt.ItemDataRole.UserRole, net.ssid)
                self._net_table.setItem(r, 1, si)
                # Col 2: MAC
                self._net_table.setItem(r, 2, _item(net.bssid or "\u2014"))
                # Col 3: Encryption
                enc_item = _item(enc)
                if enc_color:
                    enc_item.setForeground(enc_color)
                self._net_table.setItem(r, 3, enc_item)
                # Col 4: Channel
                self._net_table.setItem(r, 4, _item(str(net.channel) if net.channel else "\u2014", Qt.AlignmentFlag.AlignCenter))
                # Col 5: GHz
                self._net_table.setItem(r, 5, _item(f"{net.freq_ghz:.3f}" if net.freq_ghz else "\u2014", Qt.AlignmentFlag.AlignCenter))
                # Col 6: Mbps
                self._net_table.setItem(r, 6, _item(str(net.mbps) if net.mbps else "\u2014", Qt.AlignmentFlag.AlignCenter))
                # Col 7: Protocol
                self._net_table.setItem(r, 7, _item(net.protocol or "\u2014"))

            # Удаляем лишние строки снизу (если сетей стало меньше)
            while self._net_table.rowCount() > new_count:
                self._net_table.removeRow(self._net_table.rowCount() - 1)
        finally:
            self._net_table.setUpdatesEnabled(True)
            self._net_table.setSortingEnabled(True)

        # Восстанавливаем подсветку подключённой сети
        if self._current_ssid:
            self._highlight_connected(self._current_ssid)

    # ── Status ────────────────────────────────────────────────────

    def _poll_status(self) -> None:
        if getattr(self, '_status_polling', False):
            return
        self._status_polling = True
        threading.Thread(target=self._status_worker, daemon=True).start()

    def _status_worker(self) -> None:
        try:
            s = self._presenter.get_interface_status()
            self._bridge.status_updated.emit(s)
        except Exception:
            self._bridge.status_updated.emit({})
        finally:
            self._status_polling = False

    def _render_status(self, status: dict) -> None:
        # Обработка деталей IP из _fetch_ip_details
        if "_details" in status:
            self._status_details.setText(status["_details"])
            self._status_details.setVisible(True)
            return
        state = status.get("state", "").lower()
        ssid = status.get("ssid", "")
        signal = status.get("signal", "")
        is_connected = state in ("connected", "подключено")
        if is_connected:
            sig_str = f"  {signal}%" if signal else ""
            connected_str = self._tr("wifi_state_connected")
            label = f"{connected_str}: {ssid}{sig_str}" if ssid else connected_str
            self._status_label.setText(label)
            self._status_dot.setProperty("connected", "true")
            # Запрашиваем IP детали в фоне
            self._current_ssid = ssid
            threading.Thread(target=self._fetch_ip_details, daemon=True).start()
        else:
            self._status_details.setVisible(False)
            if state:
                self._status_label.setText(self._tr("wifi_state_disconnected"))
            else:
                self._status_label.setText(self._tr("wifi_no_adapter"))
            self._status_dot.setProperty("connected", "false")
        self._status_dot.style().unpolish(self._status_dot)
        self._status_dot.style().polish(self._status_dot)
        # Подсвечиваем строку текущей сети
        if ssid:
            self._highlight_connected(ssid)

    def _fetch_ip_details(self) -> None:
        """Получает IP, шлюз, DNS для текущего Wi-Fi адаптера."""
        try:
            import re as _re
            import logging as _log
            _logger = _log.getLogger(__name__)
            result = self._presenter.get_wifi_interface_config(
                self._presenter.get_wifi_interface_name()
            )
            if not result.stdout:
                return
            # Логируем вывод для диагностики
            _logger.info("netsh ipv4 config output:\n%s", result.stdout[:800])
            fields: dict = {}
            dns_list: list = []
            _last_key = None
            _ip_pat = _re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")
            for line in result.stdout.splitlines():
                stripped = line.strip()
                matched = False
                for key, pat in [
                    ("ip",  r"IP.адрес|IP Address"),
                    ("gw",  r"Основной шлюз|Default Gateway|"
                             r"Шлюз по умолчанию(?!\s+(?:Метрика|Metric))"),
                    ("dns", r"DNS-серверы с настройкой через DHCP|"
                             r"Серверы DNS.*?DHCP|DNS Servers.*?DHCP|"
                             r"Стат\.\s*наст\.\s*серверы DNS|Статически настроенный DNS"),
                ]:
                    m = _re.match(rf"^(?:{pat})\s*[:\.]?\s*(.+)$", stripped, _re.IGNORECASE)
                    if m:
                        val = m.group(1).strip().rstrip(".")
                        if val and val not in ("0.0.0.0", "Нет", "No", "-"):
                            if key == "dns":
                                dns_list.append(val)
                            elif key not in fields:
                                fields[key] = val
                        _last_key = key
                        matched = True
                        break
                # continuation line (indented, no label) — дополнительные DNS-адреса
                if not matched and _last_key == "dns" and line and line[0] == " ":
                    val = stripped.rstrip(".")
                    if _ip_pat.match(val):
                        dns_list.append(val)
                    else:
                        _last_key = None
                elif not matched:
                    _last_key = None
            if dns_list:
                fields["dns"] = ", ".join(dns_list)
            _logger.info("Parsed fields: %s", fields)
            if fields:
                parts = []
                if "ip" in fields:
                    parts.append(f"IP: {fields['ip']}")
                if "gw" in fields:
                    parts.append(f"GW: {fields['gw']}")
                if "dns" in fields:
                    parts.append(f"DNS: {fields['dns']}")
                detail_text = "  ·  ".join(parts)
                self._bridge.status_updated.emit({"_details": detail_text})
        except Exception:
            import traceback
            import logging
            logging.getLogger(__name__).error("_fetch_ip_details error: %s", traceback.format_exc())

    def _highlight_connected(self, ssid: str) -> None:
        """Подсвечивает строку текущей подключённой сети.
        Добавляет индикатор ● перед SSID и окрашивает строку.
        """
        self._net_table.setSortingEnabled(False)
        self._net_table.setUpdatesEnabled(False)
        connected_color = QColor(99, 102, 241, 40)
        connected_fg    = QColor("#6366F1")
        try:
            for row in range(self._net_table.rowCount()):
                ssid_item = self._net_table.item(row, 1)
                row_ssid = ssid_item.data(Qt.ItemDataRole.UserRole) if ssid_item else ""
                is_current = (row_ssid == ssid)
                for col in range(self._net_table.columnCount()):
                    cell = self._net_table.item(row, col)
                    if not cell:
                        continue
                    if is_current:
                        cell.setBackground(connected_color)
                    else:
                        cell.setBackground(QColor(0, 0, 0, 0))
                if ssid_item:
                    display = ssid_item.text()
                    if display.startswith("● "):
                        display = display[2:]
                    if is_current:
                        ssid_item.setText("● " + display)
                        ssid_item.setForeground(connected_fg)
                    else:
                        ssid_item.setText(display)
                        ssid_item.setData(Qt.ItemDataRole.ForegroundRole, None)
        finally:
            self._net_table.setUpdatesEnabled(True)
            self._net_table.setSortingEnabled(True)

    # ── Connect ───────────────────────────────────────────────────

    def _on_network_double_click(self, item) -> None:
        """Двойной клик по строке — сразу Connect."""
        self._on_connect()

    def _on_network_selected(self) -> None:
        row = self._net_table.currentRow()
        if row >= 0 and not self._selected_profile_id:
            ssid = self._net_table.item(row, 1).data(Qt.ItemDataRole.UserRole) if self._net_table.item(row, 1) else ""  # type: ignore[union-attr]
            if ssid:
                self._ed_ssid.setText(ssid)

    def _on_connect(self) -> None:
        row = self._net_table.currentRow()
        if row < 0:
            self._show_feedback("Выберите сеть", error=True)
            return
        item = self._net_table.item(row, 1) or self._net_table.item(row, 0)
        ssid = item.data(Qt.ItemDataRole.UserRole) if item else ""
        if not ssid:
            self._show_feedback("Не удалось определить SSID", error=True)
            return

        # Проверяем есть ли сохранённый профиль
        profile = self._presenter.find_wifi_profile_by_ssid(ssid)
        # Определяем тип сети из таблицы
        enc_item = self._net_table.item(row, 3)
        enc = enc_item.text() if enc_item else ""
        is_open = "open" in enc.lower() or "откры" in enc.lower()

        if not profile and not is_open:
            # Показываем диалог ввода пароля
            password = self._ask_password(ssid)
            if password is None:  # отменили
                return
        else:
            password = ""

        self.btn_connect.setEnabled(False)
        self.btn_connect.setText("⟳ ...")
        self._start_spinner()
        self._last_connect_ssid = ssid
        self._last_connect_password = password
        threading.Thread(target=self._connect_worker, args=(ssid, password), daemon=True).start()

    def _ask_password(self, ssid: str) -> Optional[str]:
        """Диалог ввода пароля для неизвестной сети. Возвращает пароль или None."""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton
        dlg = QDialog(self)
        dlg.setWindowTitle(self._tr("dlg_connect_title"))
        dlg.setFixedSize(380, 140)
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(24, 20, 24, 16)
        lay.setSpacing(12)

        lay.addWidget(QLabel(self._tr("dlg_connect_password_label").format(ssid=ssid)))

        pwd_edit = QLineEdit()
        pwd_edit.setEchoMode(QLineEdit.EchoMode.Password)
        pwd_edit.setPlaceholderText(self._tr("wifi_placeholder_password"))
        lay.addWidget(pwd_edit)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch(1)

        btn_cancel = QPushButton(self._tr("btn_cancel"))
        btn_cancel.setProperty("role", "action")
        btn_cancel.setFixedSize(80, 32)
        btn_cancel.clicked.connect(dlg.reject)

        btn_ok = QPushButton(self._tr("btn_connect_action"))
        btn_ok.setProperty("role", "primary")
        btn_ok.setFixedSize(90, 32)
        btn_ok.clicked.connect(dlg.accept)
        btn_ok.setDefault(True)

        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        lay.addLayout(btn_row)

        pwd_edit.returnPressed.connect(dlg.accept)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            return pwd_edit.text()
        return None

    def _connect_worker(self, ssid: str, password: str = "") -> None:
        try:
            import logging
            _log = logging.getLogger(__name__)
            _log.info(f"Connecting to SSID: {ssid!r}")
            profile = self._presenter.find_wifi_profile_by_ssid(ssid)
            _log.info(f"Saved profile found: {profile is not None}")
            if profile:
                result = self._presenter.connect_with_profile(ssid, profile)
            elif password:
                result = self._presenter.connect_with_ssid(ssid, password)
            else:
                result = self._presenter.connect_open_network(ssid)
            _log.info(f"Connect result: success={result.success} msg={result.message!r}")
            self._bridge.connect_done.emit(result.success, result.message)
        except Exception as e:
            import traceback
            import logging
            logging.getLogger(__name__).error(f"Connect error: {traceback.format_exc()}")
            self._bridge.connect_done.emit(False, str(e))

    def _on_connect_result(self, success: bool, message: str) -> None:
        self._stop_spinner()
        self.btn_connect.setEnabled(True)
        self.btn_connect.setText(self._tr("btn_connect"))
        if success:
            self._net_feedback.setText("")
            QTimer.singleShot(1500, self._poll_status)
            if self._last_connect_ssid and self._last_connect_password:
                QTimer.singleShot(1000, self._offer_save_profile)
            else:
                self._clear_connect_context()
        else:
            self._clear_connect_context()
            # Показываем диалог с ошибкой
            from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QHBoxLayout, QPushButton
            dlg = QDialog(self)
            dlg.setWindowTitle(self._tr("dlg_connect_error_title"))
            dlg.setFixedSize(400, 120)
            dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
            lay = QVBoxLayout(dlg)
            lay.setContentsMargins(24, 20, 24, 16)
            lay.setSpacing(16)
            lbl = QLabel(message[:120] if message else self._tr("dlg_connect_error_default"))
            lbl.setWordWrap(True)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(lbl)
            btn_row = QHBoxLayout()
            btn_row.addStretch(1)
            btn_ok = QPushButton(self._tr("btn_ok"))
            btn_ok.setProperty("role", "action")
            btn_ok.setFixedSize(80, 32)
            btn_ok.clicked.connect(dlg.accept)
            btn_row.addWidget(btn_ok)
            lay.addLayout(btn_row)
            dlg.exec()

    def _on_disconnect(self) -> None:
        self.btn_disconnect.setEnabled(False)
        threading.Thread(target=self._disconnect_worker, daemon=True).start()

    def _disconnect_worker(self) -> None:
        try:
            r = self._presenter.disconnect_network()
            self._bridge.disconnect_done.emit(r.success, r.message)
        except Exception as e:
            self._bridge.disconnect_done.emit(False, str(e))

    def _on_disconnect_result(self, success: bool, _: str) -> None:
        self.btn_disconnect.setEnabled(True)
        QTimer.singleShot(1000, self._poll_status)
        if success:
            self._net_feedback.setText("")

    # ── Profiles ──────────────────────────────────────────────────

    def _load_profiles(self) -> None:
        profiles = self._presenter.load_profiles()
        self._profile_list.setRowCount(0)
        for p in profiles:
            r = self._profile_list.rowCount()
            self._profile_list.insertRow(r)
            si = QTableWidgetItem(p.ssid)
            si.setData(Qt.ItemDataRole.UserRole, p.id)
            self._profile_list.setItem(r, 0, si)
            self._profile_list.setItem(r, 1, QTableWidgetItem(p.auth))
            ai = QTableWidgetItem("\u2713" if p.auto_connect else "\u2014")
            ai.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._profile_list.setItem(r, 2, ai)
            self._profile_list.setRowHeight(r, 30)

    def _on_profile_selected(self) -> None:
        row = self._profile_list.currentRow()
        if row < 0:
            return
        pid = self._profile_list.item(row, 0).data(Qt.ItemDataRole.UserRole)  # type: ignore[union-attr]
        self._selected_profile_id = pid
        p = self._presenter.get_wifi_profile(pid)
        if not p:
            return
        self._ed_ssid.setText(p.ssid)
        idx = self._ed_auth.findText(p.auth)
        if idx >= 0:
            self._ed_auth.setCurrentIndex(idx)
        self._on_auth_changed(p.auth)
        idx_c = self._ed_cipher.findText(p.cipher)
        if idx_c >= 0:
            self._ed_cipher.setCurrentIndex(idx_c)
        self._ed_password.clear()
        self._ed_password.setPlaceholderText("Оставьте пустым — пароль сохранится")
        self._ed_auto.setChecked(p.auto_connect)
        self._ed_hidden.setChecked(p.connect_hidden)

    def _on_new_profile(self) -> None:
        self._selected_profile_id = None
        self._profile_list.clearSelection()
        self._ed_ssid.clear()
        self._ed_auth.setCurrentText("WPA2-Personal")
        self._on_auth_changed("WPA2-Personal")
        self._ed_password.clear()
        self._ed_password.setPlaceholderText("Введите пароль")
        self._ed_auto.setChecked(True)
        self._ed_hidden.setChecked(False)
        self._ed_ssid.setFocus()

    def _on_save_profile(self) -> None:
        ssid = self._ed_ssid.text().strip()
        if not ssid:
            self._show_feedback("SSID не может быть пустым", error=True)
            return
        password = self._ed_password.text()
        key_protected = ""
        if password:
            if self._container.vault_available:
                try:
                    from quickip.core.security.vault import protect_text
                    key_protected = protect_text(password)
                except Exception as e:
                    self._show_feedback(f"Encryption error: {e}", error=True)
                    return
            elif self._presenter.keyring_available:
                try:
                    from quickip.core.security.keyring_vault import protect_text as kr_protect
                    key_protected = kr_protect(ssid, password)
                except Exception as e:
                    self._show_feedback(f"Keyring error: {e}", error=True)
                    return
            else:
                self._show_feedback(
                    "Невозможно сохранить пароль: DPAPI и keyring недоступны. "
                    "Установите pywin32 или keyring.",
                    error=True,
                )
                return
        elif self._selected_profile_id:
            existing = self._presenter.get_wifi_profile(self._selected_profile_id)
            key_protected = existing.key_protected if existing else ""

        from quickip.features.wifi.repository import WifiProfile
        import uuid
        p = WifiProfile(
            id=self._selected_profile_id or str(uuid.uuid4()),
            ssid=ssid,
            auth=self._ed_auth.currentText(),
            cipher=self._ed_cipher.currentText(),
            key_protected=key_protected,
            auto_connect=self._ed_auto.isChecked(),
            connect_hidden=self._ed_hidden.isChecked(),
            is_adhoc=False,
        )
        self._presenter.save_wifi_profile_obj(p)
        self._selected_profile_id = p.id
        self._show_feedback(self._tr("feedback_profile_saved"))
        self._load_profiles()
        # Переключаемся на Networks
        QTimer.singleShot(500, lambda: self._tabs.setCurrentIndex(0))

    def _on_delete_profile(self) -> None:
        if not self._selected_profile_id:
            self._show_feedback(self._tr("feedback_select_profile"), error=True)
            return
        reply = QMessageBox.question(
            self, self._tr("dlg_confirm_delete_title"), self._tr("dlg_delete_wifi_q"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._presenter.delete_profile(self._selected_profile_id)
        self._selected_profile_id = None
        self._on_new_profile()
        self._load_profiles()
        self._show_feedback("Профиль удалён")

    def _on_auth_changed(self, auth: str) -> None:
        ciphers = CIPHER_OPTIONS.get(auth, ["AES"])
        self._ed_cipher.blockSignals(True)
        self._ed_cipher.clear()
        self._ed_cipher.addItems(ciphers)
        self._ed_cipher.blockSignals(False)
        self._ed_password.setVisible(auth not in ("Open", "OWE"))

    # ── Feedback ──────────────────────────────────────────────────

    def _show_feedback(self, msg: str, error: bool = False) -> None:
        color = "#EF4444" if error else "#22C55E"
        self._feedback.setText(msg)
        self._feedback.setStyleSheet(f"color: {color}; font-size: 12px;")
        QTimer.singleShot(3000, lambda: self._feedback.setText(""))

    def _clear_connect_context(self) -> None:
        """Зануляет кешированный SSID и пароль после завершения connect-сценария."""
        self._last_connect_password = ""
        self._last_connect_ssid = ""

    def _offer_save_profile(self) -> None:
        """Предлагает сохранить профиль после успешного подключения с паролем."""
        try:
            ssid = self._last_connect_ssid
            if not ssid or self._presenter.find_wifi_profile_by_ssid(ssid):
                return
            msg = QMessageBox(self)
            msg.setWindowTitle(self._tr("dlg_save_profile_title"))
            msg.setText(self._tr("dlg_save_profile_text").format(ssid=ssid))
            msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            msg.setDefaultButton(QMessageBox.StandardButton.Yes)
            if msg.exec() == QMessageBox.StandardButton.Yes:
                self._ed_ssid.setText(ssid)
                # Пароль не подставляем в поле — пользователь вводит сам
                self._tabs.setCurrentIndex(1)
        finally:
            self._clear_connect_context()

    # ── Spinner ──────────────────────────────────────────────────

    def _start_spinner(self) -> None:
        self._spinner_frames = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
        self._spinner_idx = 0
        self._spinner_timer = QTimer(self)
        self._spinner_timer.setInterval(80)
        self._spinner_timer.timeout.connect(self._tick_spinner)
        self._spinner_timer.start()

    def _tick_spinner(self) -> None:
        frame = self._spinner_frames[self._spinner_idx % len(self._spinner_frames)]
        self.btn_connect.setText(f"{frame} ...")
        self._spinner_idx += 1

    def _stop_spinner(self) -> None:
        if hasattr(self, '_spinner_timer') and self._spinner_timer:
            self._spinner_timer.stop()
            self._spinner_timer = None

    # ── Context menu ──────────────────────────────────────────────

    def _on_network_context_menu(self, pos: QPoint) -> None:
        row = self._net_table.rowAt(pos.y())
        if row < 0:
            return
        ssid_item = self._net_table.item(row, 1)
        mac_item  = self._net_table.item(row, 2)
        ssid = ssid_item.data(Qt.ItemDataRole.UserRole) if ssid_item else ""
        mac  = mac_item.text() if mac_item else ""

        menu = QMenu(self)
        act_connect = menu.addAction(self._tr("ctx_connect"))
        menu.addSeparator()
        act_copy_ssid = menu.addAction(self._tr("ctx_copy_ssid"))
        act_copy_mac  = menu.addAction(self._tr("ctx_copy_mac"))
        menu.addSeparator()
        act_forget = menu.addAction(self._tr("ctx_forget"))
        act_forget.setEnabled(bool(self._presenter.find_wifi_profile_by_ssid(ssid)))

        action = menu.exec(self._net_table.viewport().mapToGlobal(pos))
        if action == act_connect:
            self._net_table.selectRow(row)
            self._on_connect()
        elif action == act_copy_ssid and ssid:
            QApplication.clipboard().setText(ssid)
        elif action == act_copy_mac and mac:
            QApplication.clipboard().setText(mac)
        elif action == act_forget and ssid:
            self._delete_profile(ssid)

    def _delete_profile(self, ssid: str) -> None:
        """Удаляет профиль из нашего хранилища и из Windows."""
        reply = QMessageBox.question(
            self, self._tr("dlg_confirm_delete_title"), self._tr("dlg_forget_network_q").format(ssid=ssid),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        profile = self._presenter.find_wifi_profile_by_ssid(ssid)
        if profile:
            self._presenter.delete_profile(profile.id)
        # Удаляем из Windows netsh
        threading.Thread(
            target=lambda: self._presenter.delete_netsh_profile_for_ssid(ssid),
            daemon=True
        ).start()
        self._load_profiles()
        self._net_feedback.setText(f"Deleted: {ssid}")
        self._net_feedback.setStyleSheet("color: #94A3B8; font-size: 12px;")
        QTimer.singleShot(3000, lambda: self._net_feedback.setText(""))

    # ── Theme / lifecycle ─────────────────────────────────────────

    def refresh_theme(self, dark_mode: bool) -> None:
        self._dark_mode = dark_mode

    # ── i18n ──────────────────────────────────────────────────────────

    def _tr(self, key: str) -> str:
        return self._container.i18n.get(key)

    def retranslate(self) -> None:
        """Обновляет все видимые строки при смене языка."""
        # Вкладки
        self._tabs.setTabText(0, self._tr("wifi_tab_networks"))
        self._tabs.setTabText(1, self._tr("wifi_tab_saved"))

        # Заголовок сетей
        self._lbl_networks_title.setText(self._tr("wifi_networks_title"))

        # Заголовки таблицы сетей
        self._net_table.setHorizontalHeaderLabels([
            self._tr("wifi_col_signal"), "SSID",
            self._tr("wifi_col_mac"), self._tr("wifi_col_enc"),
            self._tr("wifi_col_ch"), self._tr("wifi_col_ghz"),
            self._tr("wifi_col_mbps"), self._tr("wifi_col_protocol"),
        ])

        # Заголовки таблицы профилей
        self._profile_list.setHorizontalHeaderLabels([
            "SSID", self._tr("wifi_col_auth"), self._tr("wifi_col_auto"),
        ])

        # Кнопки вкладки Networks
        self.btn_scan.setText(self._tr("btn_scan"))
        self.btn_connect.setText(self._tr("btn_connect"))
        self.btn_disconnect.setText(self._tr("btn_disconnect"))

        # Кнопки вкладки Saved profiles
        self.btn_new_profile.setText(self._tr("btn_new_wifi"))
        self.btn_delete_profile.setText(self._tr("btn_delete_wifi"))
        self.btn_save_profile.setText(self._tr("btn_save_wifi"))

        # Редактор профиля
        self._lbl_editor_title.setText(self._tr("wifi_prof_editor_title").upper())
        self._lbl_wifi_ssid.setText(self._tr("wifi_lbl_ssid"))
        self._lbl_wifi_security.setText(self._tr("wifi_lbl_security"))
        self._lbl_wifi_enc.setText(self._tr("wifi_lbl_enc"))
        self._lbl_wifi_password.setText(self._tr("wifi_lbl_password"))
        self._ed_ssid.setPlaceholderText(self._tr("wifi_placeholder_ssid"))
        self._ed_password.setPlaceholderText(self._tr("wifi_placeholder_password"))

        # Чекбоксы
        self._ed_auto.setText(self._tr("chk_autoconnect"))
        self._ed_hidden.setText(self._tr("chk_hidden_network"))

    def hideEvent(self, event) -> None:
        self._status_timer.stop()
        super().hideEvent(event)

    def _on_tab_changed(self, index: int) -> None:
        """При переходе на вкладку Networks — запускаем сканирование."""
        self._clear_connect_context()
        if index == 0 and self._container.settings_repo.get("wifi_auto_scan", True):
            self._scan_queued = True
            self.btn_scan.setEnabled(False)
            QTimer.singleShot(200, self._launch_queued_scan)

    def showEvent(self, event) -> None:
        self._status_timer.start()
        self._poll_status()
        if not self._shown_once:
            self._shown_once = True
            if self._container.settings_repo.get("wifi_auto_scan", True):
                QTimer.singleShot(300, self._on_scan)
        super().showEvent(event)
