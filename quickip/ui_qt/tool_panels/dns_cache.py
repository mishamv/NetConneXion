"""Windows DNS-cache viewer and flush panel."""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from quickip.ui_qt.tool_panels.components import (
    ToolStatusKind,
    allow_horizontal_shrink,
    center_tree_item,
    configure_tool_tree,
    create_tool_button,
    set_tool_busy,
    set_tool_status,
)
from quickip.ui_qt.tool_panels.layout import configure_tool_root
from quickip.ui_qt.widgets.copyable_views import CopyableTree


_TYPE_NAMES = {
    "1": "A",
    "2": "NS",
    "5": "CNAME",
    "6": "SOA",
    "12": "PTR",
    "15": "MX",
    "16": "TXT",
    "28": "AAAA",
    "33": "SRV",
}
_NAME_KEYS = {"record name", "имя записи"}
_TYPE_KEYS = {"record type", "тип записи"}
_TTL_KEYS = {"time to live", "срок жизни"}
_SKIP_KEYS = {"data length", "длина данных", "section", "раздел"}


@dataclass(frozen=True)
class DnsCacheEntry:
    name: str
    record_type: str
    ttl: int | None
    data: str


def normalize_record_type(value: str) -> str:
    """Convert Windows numeric DNS record types to common names."""
    stripped = value.strip()
    numeric = re.match(r"^(\d+)", stripped)
    if numeric:
        number = numeric.group(1)
        return _TYPE_NAMES.get(number, f"TYPE {number}")
    return stripped.upper() or "—"


def parse_dns_cache(text: str) -> list[DnsCacheEntry]:
    """Parse localized ``ipconfig /displaydns`` output.

    Multiple data values in one Windows cache block are preserved as separate
    rows instead of overwriting one another.
    """
    rows: list[DnsCacheEntry] = []
    name = ""
    record_type = ""
    ttl: int | None = None
    values: list[str] = []

    def flush() -> None:
        nonlocal record_type, ttl, values
        if name:
            normalized_type = normalize_record_type(record_type)
            for value in values:
                if value:
                    rows.append(DnsCacheEntry(name, normalized_type, ttl, value))
        record_type = ""
        ttl = None
        values = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or set(line) <= {"-"}:
            continue
        match = re.match(r"^(.*?)\s+:\s+(.*)$", line)
        if not match:
            continue
        key = match.group(1).rstrip(". ").strip()
        value = match.group(2).strip()
        key_folded = key.casefold()

        if key_folded in _NAME_KEYS:
            flush()
            name = value.rstrip(".")
        elif key_folded in _TYPE_KEYS:
            record_type = value
        elif key_folded in _TTL_KEYS:
            try:
                ttl = int(value)
            except ValueError:
                ttl = None
        elif key_folded not in _SKIP_KEYS and name:
            values.append(value)
    flush()
    return rows


class DnsCacheBridge(QObject):
    rows_ready = Signal(list)
    operation_done = Signal(str, bool, str)


class DnsCachePanel(QWidget):
    _FILTERS = ("ALL", "A", "AAAA", "CNAME", "PTR", "MX", "SRV", "TXT", "OTHER")

    def __init__(self, dark: bool = True, i18n=None, runner=None) -> None:
        super().__init__()
        self._dark = dark
        self._i18n = i18n
        self._runner = runner
        self._bridge = DnsCacheBridge()
        self._entries: list[DnsCacheEntry] = []
        self._busy = False

        root = QVBoxLayout(self)
        configure_tool_root(root)
        root.setSpacing(12)

        self._title = QLabel(self._tr("tools_dns_cache_title"))
        self._title.setObjectName("ToolPanelTitle")
        root.addWidget(self._title)

        toolbar_card = QFrame()
        toolbar_card.setObjectName("DnsCacheToolbarCard")
        toolbar = QVBoxLayout(toolbar_card)
        toolbar.setContentsMargins(16, 14, 16, 16)
        toolbar.setSpacing(8)

        self._search_label = self._toolbar_label("tools_dns_cache_search")
        self._type_label = self._toolbar_label("tools_dns_cache_type_filter")
        toolbar.addWidget(self._search_label)

        self._search = QLineEdit()
        self._search.setObjectName("ToolInput")
        self._search.setPlaceholderText(self._tr("tools_dns_cache_search_placeholder"))
        self._search.setClearButtonEnabled(True)
        self._search.setMinimumHeight(40)
        toolbar.addWidget(self._search)

        self._type_filter = QComboBox()
        self._type_filter.setObjectName("ToolCombo")
        self._type_filter.setMinimumHeight(40)
        self._type_filter.setMinimumWidth(240)
        self._type_filter.setMaximumWidth(340)
        for value in self._FILTERS:
            self._type_filter.addItem(self._filter_text(value), value)

        self._btn_ref = create_tool_button(
            self._tr("tools_dns_cache_btn_refresh"),
            role="primary",
            min_width=170,
            min_height=40,
        )
        self._btn_flush = create_tool_button(
            self._tr("tools_dns_cache_btn_flush"),
            min_width=170,
            min_height=40,
        )
        self._btn_ref.setMaximumWidth(190)
        self._btn_flush.setMaximumWidth(190)
        for widget in (
            self._search_label, self._type_label,
            self._search, self._type_filter,
        ):
            allow_horizontal_shrink(widget)

        controls_bar = QWidget(toolbar_card)
        controls_bar.setObjectName("DnsCacheControlsBar")
        controls = QHBoxLayout(controls_bar)
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(12)
        filter_group = QVBoxLayout()
        filter_group.setSpacing(6)
        filter_group.addWidget(self._type_label)
        filter_group.addWidget(self._type_filter)
        controls.addLayout(filter_group)
        controls.addStretch(2)
        controls.addWidget(self._btn_ref, 0, Qt.AlignmentFlag.AlignBottom)
        controls.addWidget(self._btn_flush, 0, Qt.AlignmentFlag.AlignBottom)
        toolbar.addWidget(controls_bar)
        root.addWidget(toolbar_card)

        results_section = QFrame()
        results_section.setObjectName("DnsCacheResultsSection")
        results_layout = QVBoxLayout(results_section)
        results_layout.setContentsMargins(0, 0, 0, 0)
        results_layout.setSpacing(0)

        summary_bar = QFrame()
        summary_bar.setObjectName("DnsCacheSummaryBar")
        summary = QHBoxLayout(summary_bar)
        summary.setContentsMargins(14, 10, 14, 10)
        summary.setSpacing(8)
        self._total_pill = self._summary_pill()
        self._visible_pill = self._summary_pill()
        summary.addWidget(self._total_pill)
        summary.addWidget(self._visible_pill)
        summary.addStretch(1)
        results_layout.addWidget(summary_bar)

        table_card = QFrame()
        table_card.setObjectName("DnsCacheResultCard")
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(0, 0, 0, 0)

        self._tree = CopyableTree(i18n=i18n)
        configure_tool_tree(
            self._tree, dark=dark, object_name="DnsCacheTable"
        )
        self._tree.setHeaderLabels(self._header_labels())
        self._align_table_headers()
        self._tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._tree.header().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._tree.setAlternatingRowColors(True)
        self._tree.setRootIsDecorated(False)
        self._tree.setSortingEnabled(True)
        self._tree.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        table_layout.addWidget(self._tree)
        results_layout.addWidget(table_card, 1)
        root.addWidget(results_section, 1)

        self._status = QLabel(self._tr("tools_dns_cache_hint"))
        self._status.setObjectName("ToolStatus")
        root.addWidget(self._status)

        self._search.textChanged.connect(self._apply_filter)
        self._type_filter.currentIndexChanged.connect(self._apply_filter)
        self._btn_ref.clicked.connect(self._refresh)
        self._btn_flush.clicked.connect(self._flush)
        self._bridge.rows_ready.connect(self._on_rows_ready)
        self._bridge.operation_done.connect(self._on_operation_done)
        self._update_summary(0)
    def _tr(self, key: str, **kwargs) -> str:
        return self._i18n.get(key, **kwargs) if self._i18n else key

    def _toolbar_label(self, key: str) -> QLabel:
        label = QLabel(self._tr(key))
        label.setObjectName("DnsCacheToolbarLabel")
        return label

    @staticmethod
    def _summary_pill() -> QLabel:
        label = QLabel()
        label.setObjectName("DnsCacheSummaryPill")
        return label

    def _header_labels(self) -> list[str]:
        return [
            self._tr("tools_dns_cache_col_name"),
            self._tr("tools_dns_cache_col_type"),
            self._tr("tools_dns_cache_col_ttl"),
            self._tr("tools_dns_cache_col_data"),
        ]

    def _filter_text(self, value: str) -> str:
        if value == "ALL":
            return self._tr("tools_dns_cache_filter_all")
        if value == "OTHER":
            return self._tr("tools_dns_cache_filter_other")
        return value

    def retranslate(self) -> None:
        self._title.setText(self._tr("tools_dns_cache_title"))
        self._search_label.setText(self._tr("tools_dns_cache_search"))
        self._type_label.setText(self._tr("tools_dns_cache_type_filter"))
        self._search.setPlaceholderText(self._tr("tools_dns_cache_search_placeholder"))
        self._btn_ref.setText(self._tr("tools_dns_cache_btn_refresh"))
        self._btn_flush.setText(self._tr("tools_dns_cache_btn_flush"))
        for index, value in enumerate(self._FILTERS):
            self._type_filter.setItemText(index, self._filter_text(value))
        self._tree.setHeaderLabels(self._header_labels())
        self._align_table_headers()
        self._apply_filter()

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        set_tool_busy(self._btn_ref, busy)
        self._btn_flush.setEnabled(not busy)

    def _set_status(self, text: str, color_key: str | None = None) -> None:
        kind = {
            "STATUS_ERROR": ToolStatusKind.ERROR,
            "STATUS_SUCCESS": ToolStatusKind.SUCCESS,
        }.get(color_key, ToolStatusKind.NEUTRAL)
        if self._busy and color_key is None:
            kind = ToolStatusKind.RUNNING
        set_tool_status(self._status, text, kind)

    def _refresh(self) -> None:
        if self._busy:
            return
        if self._runner is None:
            self._set_status(
                self._tr("tools_dns_cache_error_runner"), "STATUS_ERROR"
            )
            return
        self._set_busy(True)
        self._set_status(self._tr("tools_dns_cache_loading"), None)
        threading.Thread(
            target=self._refresh_worker,
            daemon=True,
            name="dns-cache-refresh",
        ).start()

    def _refresh_worker(self) -> None:
        try:
            result = self._runner.run(["ipconfig", "/displaydns"], timeout=15)
            if not result.success:
                message = result.stderr.strip() or self._tr("tools_dns_cache_error_read")
                self._bridge.operation_done.emit("refresh", False, message)
                return
            rows = parse_dns_cache(result.stdout)
            self._bridge.rows_ready.emit(rows)
            self._bridge.operation_done.emit(
                "refresh",
                True,
                self._tr("tools_dns_cache_loaded", count=len(rows)),
            )
        except Exception:
            self._bridge.operation_done.emit(
                "refresh",
                False,
                self._tr("tools_dns_cache_error_read"),
            )

    def _flush(self) -> None:
        if self._busy:
            return
        reply = QMessageBox.question(
            self,
            self._tr("dlg_dns_flush_title"),
            self._tr("dlg_dns_flush_text"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        if self._runner is None:
            self._set_status(
                self._tr("tools_dns_cache_error_runner"), "STATUS_ERROR"
            )
            return
        self._set_busy(True)
        self._set_status(self._tr("tools_dns_cache_flushing"), None)
        threading.Thread(
            target=self._flush_worker,
            daemon=True,
            name="dns-cache-flush",
        ).start()

    def _flush_worker(self) -> None:
        try:
            result = self._runner.run(["ipconfig", "/flushdns"], timeout=8)
            if result.success:
                self._bridge.operation_done.emit(
                    "flush",
                    True,
                    self._tr("tools_dns_cache_flushed"),
                )
            else:
                message = result.stderr.strip() or self._tr("tools_dns_cache_error_flush")
                self._bridge.operation_done.emit("flush", False, message)
        except Exception:
            self._bridge.operation_done.emit(
                "flush",
                False,
                self._tr("tools_dns_cache_error_flush"),
            )

    def _on_rows_ready(self, rows: list[DnsCacheEntry]) -> None:
        self._entries = list(rows)
        self._apply_filter()

    def _matches_type(self, entry: DnsCacheEntry, selected: str) -> bool:
        if selected == "ALL":
            return True
        known = {"A", "AAAA", "CNAME", "PTR", "MX", "SRV", "TXT"}
        if selected == "OTHER":
            return entry.record_type not in known
        return entry.record_type == selected

    def _apply_filter(self) -> None:
        query = self._search.text().strip().casefold()
        selected = str(self._type_filter.currentData() or "ALL")
        visible = [
            entry
            for entry in self._entries
            if self._matches_type(entry, selected)
            and (
                not query
                or query in entry.name.casefold()
                or query in entry.data.casefold()
            )
        ]
        self._populate(visible)
        self._update_summary(len(visible))

    def _populate(self, rows: list[DnsCacheEntry]) -> None:
        self._tree.setSortingEnabled(False)
        self._tree.clear()
        left_alignment = (
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        for entry in rows:
            ttl_text = "—" if entry.ttl is None else str(entry.ttl)
            item = QTreeWidgetItem(
                self._tree,
                [entry.name, entry.record_type, ttl_text, entry.data],
            )
            center_tree_item(item)
            item.setTextAlignment(0, left_alignment)
            item.setTextAlignment(3, left_alignment)
            item.setData(2, Qt.ItemDataRole.UserRole, entry.ttl or -1)
        self._tree.setSortingEnabled(True)

    def _align_table_headers(self) -> None:
        """Align record names and values to the left in both themes.

        Выравнивает имена и значения DNS-записей по левому краю
        в обеих темах.
        """
        header_item = self._tree.headerItem()
        if header_item is None:
            return
        center_alignment = (
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
        )
        left_alignment = (
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        for column in range(self._tree.columnCount()):
            header_item.setTextAlignment(column, center_alignment)
        header_item.setTextAlignment(0, left_alignment)
        header_item.setTextAlignment(3, left_alignment)

    def _update_summary(self, visible_count: int) -> None:
        self._total_pill.setText(
            self._tr("tools_dns_cache_total", count=len(self._entries))
        )
        self._visible_pill.setText(
            self._tr("tools_dns_cache_visible", count=visible_count)
        )

    def _on_operation_done(self, operation: str, success: bool, message: str) -> None:
        self._set_busy(False)
        if success and operation == "flush":
            self._entries = []
            self._apply_filter()
        self._set_status(
            message,
            "STATUS_SUCCESS" if success else "STATUS_ERROR",
        )

    def refresh_theme(self, dark: bool) -> None:
        self._dark = dark
        configure_tool_tree(
            self._tree, dark=dark, object_name="DnsCacheTable"
        )
