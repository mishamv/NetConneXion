"""TCP port-scanner panel."""

from __future__ import annotations

import queue
import socket
import threading
import time

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from quickip.ui_qt.tool_panels.components import (
    ToolStatusKind,
    allow_horizontal_shrink,
    center_table_item,
    configure_tool_table_alignment,
    create_tool_button,
    set_tool_busy,
    set_tool_status,
)
from quickip.ui_qt.tool_panels.layout import configure_tool_root
from quickip.ui_qt.widgets.copyable_views import CopyableTable


COMMON_PORTS = (
    20, 21, 22, 23, 25, 53, 80, 110, 123, 135, 139, 143, 161, 389,
    443, 445, 465, 500, 587, 636, 993, 995, 1433, 1521, 3306, 3389,
    5432, 5900, 6379, 8080, 8443,
)
WEB_PORTS = (80, 443, 8000, 8080, 8081, 8443, 8888)
MAX_WORKERS = 128


def format_ports(ports: tuple[int, ...] | list[int]) -> str:
    """Return a compact comma-separated port specification."""
    return ", ".join(str(port) for port in ports)


def parse_ports(spec: str) -> list[int]:
    """Parse comma-separated TCP ports and inclusive ranges.

    Examples: ``80``, ``80,443`` and ``20-25,80,443``.
    Invalid or descending ranges are rejected instead of being silently ignored.
    """
    text = spec.strip()
    if not text:
        raise ValueError("empty port specification")

    ports: set[int] = set()
    for raw_part in text.split(","):
        part = raw_part.strip()
        if not part:
            raise ValueError("empty port item")
        if "-" in part:
            if part.count("-") != 1:
                raise ValueError("invalid range")
            low_text, high_text = (value.strip() for value in part.split("-", 1))
            low, high = int(low_text), int(high_text)
            if low > high:
                raise ValueError("descending range")
            if not 1 <= low <= 65535 or not 1 <= high <= 65535:
                raise ValueError("port outside valid range")
            ports.update(range(low, high + 1))
        else:
            port = int(part)
            if not 1 <= port <= 65535:
                raise ValueError("port outside valid range")
            ports.add(port)
    return sorted(ports)


class PortScanBridge(QObject):
    resolved = Signal(str)
    result = Signal(int, str, float)
    progress = Signal(int, int, int)
    finished = Signal(bool, bool, str)


class PortScanPanel(QWidget):
    _PRESETS = (
        ("tools_portscan_preset_basic", format_ports(COMMON_PORTS)),
        ("tools_portscan_preset_extended", "1-1024"),
        ("tools_portscan_preset_all", "1-65535"),
        ("tools_portscan_preset_web", format_ports(WEB_PORTS)),
        ("tools_portscan_preset_manual", ""),
    )

    def __init__(self, dark: bool = True, i18n=None) -> None:
        super().__init__()
        self._dark = dark
        self._i18n = i18n
        self._stop_event = threading.Event()
        self._running = False
        self._bridge = PortScanBridge()

        root = QVBoxLayout(self)
        configure_tool_root(root)
        root.setSpacing(12)

        self._title = QLabel(self._tr("tools_portscan_title"))
        self._title.setObjectName("ToolPanelTitle")
        root.addWidget(self._title)

        input_card = QFrame()
        input_card.setObjectName("PortScanInputCard")
        form = QGridLayout(input_card)
        form.setContentsMargins(16, 14, 16, 16)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(7)
        # Give the ports specification enough room for common port lists.
        # Оставляем списку портов достаточно места для типовых наборов.
        form.setColumnStretch(0, 8)
        form.setColumnStretch(1, 6)
        form.setColumnStretch(2, 10)
        form.setColumnStretch(3, 5)

        self._host_label = self._input_label("tools_portscan_host")
        self._preset_label = self._input_label("tools_portscan_preset")
        self._ports_label = self._input_label("tools_portscan_ports")
        self._timeout_label = self._input_label("tools_portscan_timeout")
        form.addWidget(self._host_label, 0, 0)
        form.addWidget(self._preset_label, 0, 1)
        form.addWidget(self._ports_label, 0, 2)
        form.addWidget(self._timeout_label, 0, 3)

        self._host = QLineEdit()
        self._host.setObjectName("ToolInput")
        self._host.setPlaceholderText(self._tr("tools_portscan_host_placeholder"))
        self._host.setMinimumHeight(40)
        self._host.returnPressed.connect(self._on_run)
        form.addWidget(self._host, 1, 0)

        self._preset = QComboBox()
        self._preset.setObjectName("ToolCombo")
        self._preset.setMinimumHeight(40)
        self._preset.setMaximumWidth(16777215)
        for key, spec in self._PRESETS:
            self._preset.addItem(self._tr(key), spec)
        self._preset.currentIndexChanged.connect(self._on_preset_changed)
        form.addWidget(self._preset, 1, 1)

        self._ports = QLineEdit()
        self._ports.setObjectName("ToolInput")
        self._ports.setPlaceholderText(self._tr("tools_portscan_ports_placeholder"))
        self._ports.setMinimumHeight(40)
        self._ports.setText(self._PRESETS[0][1])
        self._ports.setCursorPosition(0)
        self._ports.setToolTip(self._ports.text())
        self._ports.returnPressed.connect(self._on_run)
        self._ports.textEdited.connect(self._on_ports_edited)
        form.addWidget(self._ports, 1, 2)

        self._timeout = QSpinBox()
        self._timeout.setObjectName("ToolSpinBox")
        self._timeout.setRange(100, 3000)
        self._timeout.setSingleStep(100)
        self._timeout.setValue(500)
        self._timeout.setSuffix(" ms")
        self._timeout.setMinimumHeight(40)
        for widget in (
            self._host_label, self._preset_label,
            self._ports_label, self._timeout_label,
            self._host, self._preset, self._ports,
        ):
            allow_horizontal_shrink(widget)
        form.addWidget(self._timeout, 1, 3)
        root.addWidget(input_card)

        results_section = QFrame()
        results_section.setObjectName("PortScanResultsSection")
        results_section_layout = QVBoxLayout(results_section)
        results_section_layout.setContentsMargins(0, 0, 0, 0)
        results_section_layout.setSpacing(0)

        controls_bar = QFrame()
        controls_bar.setObjectName("PortScanControlsBar")
        controls = QHBoxLayout(controls_bar)
        controls.setContentsMargins(14, 10, 14, 8)
        controls.setSpacing(8)
        self.btn_run = create_tool_button(
            self._tr("tools_portscan_start"),
            role="primary",
            min_width=110,
            min_height=40,
        )
        self.btn_stop = create_tool_button(
            self._tr("tools_portscan_stop"),
            min_width=110,
            min_height=40,
        )
        self.btn_clear = create_tool_button(
            self._tr("tools_portscan_clear"),
            min_width=110,
            min_height=40,
        )
        self.btn_stop.setEnabled(False)
        controls.addWidget(self.btn_run)
        controls.addWidget(self.btn_stop)
        controls.addStretch(1)
        controls.addWidget(self.btn_clear)
        results_section_layout.addWidget(controls_bar)

        progress_frame = QFrame()
        progress_frame.setObjectName("PortScanProgressRow")
        progress_row = QHBoxLayout(progress_frame)
        progress_row.setContentsMargins(14, 0, 14, 10)
        progress_row.setSpacing(12)
        self._progress = QProgressBar()
        self._progress.setObjectName("PortScanProgress")
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(7)
        self._progress_text = QLabel(self._tr("tools_portscan_ready"))
        self._progress_text.setObjectName("PortScanProgressText")
        progress_row.addWidget(self._progress, 1)
        progress_row.addWidget(self._progress_text)
        results_section_layout.addWidget(progress_frame)

        result_card = QFrame()
        result_card.setObjectName("PortScanResultCard")
        result_layout = QVBoxLayout(result_card)
        result_layout.setContentsMargins(0, 0, 0, 0)
        result_layout.setSpacing(0)

        self._table = CopyableTable(0, 4, i18n=i18n)
        self._table.setObjectName("PortScanTable")
        self._table.setHorizontalHeaderLabels(self._header_labels())
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(False)
        self._table.setSortingEnabled(True)
        header = self._table.horizontalHeader()
        configure_tool_table_alignment(self._table)
        # Keep the table geometry stable while scan results are being appended.
        # ResizeToContents recalculates widths for every new row and makes the
        # columns visibly jump during a scan.
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self._table.setColumnWidth(0, 140)
        self._table.setColumnWidth(1, 220)
        self._table.setColumnWidth(3, 150)
        result_layout.addWidget(self._table)
        results_section_layout.addWidget(result_card, 1)
        root.addWidget(results_section, 1)

        self._status = QLabel(self._tr("tools_portscan_hint"))
        self._status.setObjectName("ToolStatus")
        root.addWidget(self._status)

        self.btn_run.clicked.connect(self._on_run)
        self.btn_stop.clicked.connect(self._on_stop)
        self.btn_clear.clicked.connect(self._clear)
        self._bridge.resolved.connect(self._on_resolved)
        self._bridge.result.connect(self._on_result)
        self._bridge.progress.connect(self._on_progress)
        self._bridge.finished.connect(self._on_finished)

    def _tr(self, key: str, **kwargs) -> str:
        return self._i18n.get(key, **kwargs) if self._i18n else key

    def _input_label(self, key: str) -> QLabel:
        label = QLabel(self._tr(key))
        label.setObjectName("PortScanInputLabel")
        return label

    def _header_labels(self) -> list[str]:
        return [
            self._tr("tools_portscan_col_port"),
            self._tr("tools_portscan_col_state"),
            self._tr("tools_portscan_col_service"),
            self._tr("tools_portscan_col_response"),
        ]

    def retranslate(self) -> None:
        self._title.setText(self._tr("tools_portscan_title"))
        for label, key in (
            (self._host_label, "tools_portscan_host"),
            (self._preset_label, "tools_portscan_preset"),
            (self._ports_label, "tools_portscan_ports"),
            (self._timeout_label, "tools_portscan_timeout"),
        ):
            label.setText(self._tr(key))
        self._host.setPlaceholderText(self._tr("tools_portscan_host_placeholder"))
        self._ports.setPlaceholderText(self._tr("tools_portscan_ports_placeholder"))
        for index, (key, _) in enumerate(self._PRESETS):
            self._preset.setItemText(index, self._tr(key))
        self.btn_run.setText(self._tr("tools_portscan_start"))
        self.btn_stop.setText(self._tr("tools_portscan_stop"))
        self.btn_clear.setText(self._tr("tools_portscan_clear"))
        self._table.setHorizontalHeaderLabels(self._header_labels())
        if not self._running:
            self._progress_text.setText(self._tr("tools_portscan_ready"))

    def _on_preset_changed(self, index: int) -> None:
        spec = str(self._preset.itemData(index) or "")
        if spec:
            self._ports.setText(spec)
            self._ports.setCursorPosition(0)
            self._ports.setToolTip(spec)
        elif index == len(self._PRESETS) - 1:
            self._ports.setFocus()

    def _on_ports_edited(self) -> None:
        self._ports.setToolTip(self._ports.text())
        custom_index = len(self._PRESETS) - 1
        if self._preset.currentIndex() != custom_index:
            self._preset.blockSignals(True)
            self._preset.setCurrentIndex(custom_index)
            self._preset.blockSignals(False)

    def _set_running(self, running: bool) -> None:
        self._running = running
        set_tool_busy(self.btn_run, running, stop_button=self.btn_stop)
        self._host.setEnabled(not running)
        self._preset.setEnabled(not running)
        self._ports.setEnabled(not running)
        self._timeout.setEnabled(not running)

    def _set_status(self, text: str, color_key: str | None = None) -> None:
        kind = {
            "STATUS_ERROR": ToolStatusKind.ERROR,
            "STATUS_SUCCESS": ToolStatusKind.SUCCESS,
        }.get(color_key, ToolStatusKind.NEUTRAL)
        if self._running and color_key is None:
            kind = ToolStatusKind.RUNNING
        set_tool_status(self._status, text, kind)

    def _on_run(self) -> None:
        if self._running:
            return
        host = self._host.text().strip()
        if not host:
            self._set_status(
                self._tr("tools_portscan_error_host"), "STATUS_ERROR"
            )
            return
        try:
            ports = parse_ports(self._ports.text())
        except (TypeError, ValueError):
            self._set_status(
                self._tr("tools_portscan_error_ports"), "STATUS_ERROR"
            )
            return

        self._stop_event.clear()
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        self._progress.setValue(0)
        self._set_running(True)
        self._progress_text.setText(
            self._tr("tools_portscan_progress", done=0, total=len(ports))
        )
        self._set_status(
            self._tr("tools_portscan_resolving", host=host), None
        )
        timeout_seconds = self._timeout.value() / 1000.0
        threading.Thread(
            target=self._worker,
            args=(host, ports, timeout_seconds),
            daemon=True,
            name="port-scan",
        ).start()

    def _on_stop(self) -> None:
        if not self._running:
            return
        self._stop_event.set()
        self.btn_stop.setEnabled(False)
        self._set_status(self._tr("tools_portscan_stopping"), None)

    def _clear(self) -> None:
        if self._running:
            return
        self._table.setRowCount(0)
        self._progress.setValue(0)
        self._progress_text.setText(self._tr("tools_portscan_ready"))
        self._set_status(self._tr("tools_portscan_hint"), None)

    def _worker(
        self,
        host: str,
        ports: list[int],
        timeout_seconds: float,
    ) -> None:
        try:
            address_info = socket.getaddrinfo(
                host,
                None,
                type=socket.SOCK_STREAM,
            )
            resolved = address_info[0][4][0]
        except OSError:
            self._bridge.finished.emit(
                False,
                False,
                self._tr("tools_portscan_error_resolve", host=host),
            )
            return

        self._bridge.resolved.emit(resolved)
        work: queue.Queue[int] = queue.Queue()
        for port in ports:
            work.put(port)

        lock = threading.Lock()
        done = 0
        open_count = 0
        total = len(ports)

        def probe() -> None:
            nonlocal done, open_count
            while not self._stop_event.is_set():
                try:
                    port = work.get_nowait()
                except queue.Empty:
                    return

                started = time.perf_counter()
                is_open = False
                try:
                    with socket.create_connection(
                        (host, port),
                        timeout=timeout_seconds,
                    ):
                        is_open = True
                except OSError:
                    pass
                elapsed_ms = (time.perf_counter() - started) * 1000

                service = ""
                if is_open:
                    try:
                        service = socket.getservbyport(port, "tcp")
                    except OSError:
                        service = self._tr("tools_portscan_unknown_service")
                    self._bridge.result.emit(port, service, elapsed_ms)

                with lock:
                    done += 1
                    if is_open:
                        open_count += 1
                    current_done = done
                    current_open = open_count
                self._bridge.progress.emit(current_done, total, current_open)
                work.task_done()

        workers = [
            threading.Thread(target=probe, daemon=True, name=f"port-probe-{i}")
            for i in range(min(MAX_WORKERS, total))
        ]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()

        stopped = self._stop_event.is_set()
        message_key = (
            "tools_portscan_stopped_summary"
            if stopped
            else "tools_portscan_done"
        )
        self._bridge.finished.emit(
            True,
            stopped,
            self._tr(
                message_key,
                done=done,
                total=total,
                open=open_count,
            ),
        )

    def _on_resolved(self, address: str) -> None:
        self._set_status(
            self._tr("tools_portscan_scanning", address=address), None
        )

    def _on_result(self, port: int, service: str, elapsed_ms: float) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        values = (
            str(port),
            self._tr("tools_portscan_open"),
            service or self._tr("tools_portscan_unknown_service"),
            f"{elapsed_ms:.1f} ms",
        )
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            center_table_item(item)
            if column == 0:
                item.setData(Qt.ItemDataRole.UserRole, port)
            self._table.setItem(row, column, item)

    def _on_progress(self, done: int, total: int, open_count: int) -> None:
        percent = min(100, int(done * 100 / total)) if total else 0
        self._progress.setValue(percent)
        self._progress_text.setText(
            self._tr("tools_portscan_progress_open", done=done, total=total, open=open_count)
        )

    def _on_finished(self, success: bool, stopped: bool, message: str) -> None:
        self._set_running(False)
        self._table.setSortingEnabled(True)
        if success and not stopped:
            self._progress.setValue(100)
        color_key = "STATUS_WARNING" if stopped else (
            "STATUS_SUCCESS" if success else "STATUS_ERROR"
        )
        self._set_status(message, color_key)
        if not success:
            self._progress_text.setText(self._tr("tools_portscan_failed"))

    def refresh_theme(self, dark: bool) -> None:
        self._dark = dark
