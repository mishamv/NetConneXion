"""IPv4 subnet-calculator panel."""

from __future__ import annotations

import ipaddress

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from quickip.ui_qt.palette import semantic_color
from quickip.ui_qt.tool_panels.components import (
    allow_horizontal_shrink,
    create_tool_button,
)
from quickip.ui_qt.tool_panels.layout import configure_tool_root


def prefix_to_mask(prefix: int) -> str:
    """Return the dotted-decimal IPv4 mask for a CIDR prefix."""
    if not 0 <= prefix <= 32:
        raise ValueError("IPv4 prefix must be between 0 and 32")
    return str(ipaddress.IPv4Network(f"0.0.0.0/{prefix}").netmask)


def parse_ipv4_input(address: str, fallback_prefix: int = 24) -> tuple[str, int]:
    """Parse an IPv4 address with an optional CIDR or dotted-decimal mask."""
    text = address.strip()
    if not text:
        raise ValueError("empty address")

    if "/" not in text:
        ip = ipaddress.IPv4Address(text)
        return str(ip), fallback_prefix

    ip_text, mask_text = (part.strip() for part in text.split("/", 1))
    ip = ipaddress.IPv4Address(ip_text)
    if "." in mask_text:
        prefix = ipaddress.IPv4Network(f"0.0.0.0/{mask_text}").prefixlen
    else:
        prefix = int(mask_text)
        if not 0 <= prefix <= 32:
            raise ValueError("IPv4 prefix must be between 0 and 32")
    return str(ip), prefix


def calculate_subnet_details(address: str, prefix: int) -> dict[str, str | int]:
    """Calculate display-ready IPv4 subnet details."""
    ip = ipaddress.IPv4Address(address)
    network = ipaddress.IPv4Network(f"{ip}/{prefix}", strict=False)
    total = network.num_addresses

    if network.prefixlen <= 30:
        first = network.network_address + 1
        last = network.broadcast_address - 1
        usable = total - 2
    else:
        first = network.network_address
        last = network.broadcast_address
        usable = total

    first_octet = int(str(ip).split(".", 1)[0])
    if first_octet <= 127:
        address_class = "A"
    elif first_octet <= 191:
        address_class = "B"
    elif first_octet <= 223:
        address_class = "C"
    elif first_octet <= 239:
        address_class = "D"
    else:
        address_class = "E"

    if ip.is_loopback:
        kind = "loopback"
    elif ip.is_link_local:
        kind = "link_local"
    elif ip.is_multicast:
        kind = "multicast"
    elif ip.is_private:
        kind = "private"
    elif ip.is_reserved:
        kind = "reserved"
    else:
        kind = "public"

    return {
        "ip": str(ip),
        "cidr": f"{network.network_address}/{network.prefixlen}",
        "network": str(network.network_address),
        "mask": str(network.netmask),
        "wildcard": str(network.hostmask),
        "broadcast": str(network.broadcast_address),
        "first": str(first),
        "last": str(last),
        "total": total,
        "hosts": usable,
        "cls": address_class,
        "kind": kind,
        "prefix": network.prefixlen,
    }


class SubnetCalcPanel(QWidget):
    _NETWORK_ROWS = (
        ("tools_subnet_ip", "ip"),
        ("tools_subnet_cidr", "cidr"),
        ("tools_subnet_network", "network"),
        ("tools_subnet_mask", "mask"),
        ("tools_subnet_wildcard", "wildcard"),
        ("tools_subnet_broadcast", "broadcast"),
    )
    _RANGE_ROWS = (
        ("tools_subnet_first", "first"),
        ("tools_subnet_last", "last"),
        ("tools_subnet_total", "total"),
        ("tools_subnet_hosts", "hosts"),
        ("tools_subnet_cls", "cls"),
        ("tools_subnet_type", "kind"),
    )
    _KIND_KEYS = {
        "private": "tools_subnet_type_private",
        "public": "tools_subnet_type_public",
        "loopback": "tools_subnet_type_loopback",
        "link_local": "tools_subnet_type_link_local",
        "multicast": "tools_subnet_type_multicast",
        "reserved": "tools_subnet_type_reserved",
    }

    def __init__(self, dark: bool = True, i18n=None) -> None:
        super().__init__()
        self._dark = dark
        self._i18n = i18n
        root = QVBoxLayout(self)
        configure_tool_root(root)
        root.setSpacing(16)

        self._title = QLabel(self._tr("tools_subnet_title"))
        self._title.setObjectName("ToolPanelTitle")
        root.addWidget(self._title)

        input_card = QFrame()
        input_card.setObjectName("SubnetInputCard")
        input_layout = QGridLayout(input_card)
        input_layout.setContentsMargins(18, 16, 18, 18)
        input_layout.setHorizontalSpacing(12)
        input_layout.setVerticalSpacing(8)
        input_layout.setColumnStretch(0, 5)
        input_layout.setColumnStretch(1, 4)
        input_layout.setColumnStretch(2, 2)

        self._ip_label = QLabel(self._tr("tools_subnet_ip_label"))
        self._ip_label.setObjectName("SubnetInputLabel")
        self._mask_label = QLabel(self._tr("tools_subnet_mask_label"))
        self._mask_label.setObjectName("SubnetInputLabel")
        input_layout.addWidget(self._ip_label, 0, 0)
        input_layout.addWidget(self._mask_label, 0, 1)

        self._address = QLineEdit()
        self._address.setObjectName("ToolInput")
        self._address.setPlaceholderText(self._tr("tools_subnet_placeholder"))
        self._address.setText("192.168.1.1")
        self._address.setMinimumHeight(42)
        self._address.returnPressed.connect(self._calc)
        input_layout.addWidget(self._address, 1, 0)

        self._mask = QComboBox()
        self._mask.setObjectName("ToolCombo")
        self._mask.setMinimumHeight(42)
        self._mask.setMaxVisibleItems(12)
        for prefix in range(32, -1, -1):
            self._mask.addItem(f"/{prefix}  ({prefix_to_mask(prefix)})", prefix)
        self._mask.setCurrentIndex(32 - 24)
        input_layout.addWidget(self._mask, 1, 1)

        self._btn_calc = create_tool_button(
            self._tr("tools_subnet_btn_calc"),
            role="primary",
            min_width=130,
            min_height=40,
        )
        self._btn_calc.clicked.connect(self._calc)
        for widget in (
            self._ip_label, self._mask_label,
            self._address, self._mask, self._btn_calc,
        ):
            allow_horizontal_shrink(widget)
        input_layout.addWidget(self._btn_calc, 1, 2)
        root.addWidget(input_card)

        self._results_title = QLabel(self._tr("tools_subnet_results"))
        self._results_title.setObjectName("SubnetResultsTitle")
        root.addWidget(self._results_title)

        results = QHBoxLayout()
        results.setSpacing(12)
        self._fields: dict[str, QLabel] = {}
        self._row_labels: dict[str, QLabel] = {}
        self._network_title, network_card = self._build_result_card(
            self._tr("tools_subnet_network_group"), self._NETWORK_ROWS
        )
        self._range_title, range_card = self._build_result_card(
            self._tr("tools_subnet_range_group"), self._RANGE_ROWS
        )
        results.addWidget(network_card, 1)
        results.addWidget(range_card, 1)
        root.addLayout(results)

        self._status = QLabel(self._tr("tools_subnet_hint"))
        self._status.setObjectName("ToolStatus")
        root.addWidget(self._status)
        root.addStretch(1)

        self._calc()

    def _build_result_card(
        self,
        title: str,
        rows: tuple[tuple[str, str], ...],
    ) -> tuple[QLabel, QFrame]:
        card = QFrame()
        card.setObjectName("SubnetResultCard")
        allow_horizontal_shrink(card)
        layout = QGridLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setHorizontalSpacing(18)
        layout.setVerticalSpacing(10)
        # Keep captions readable and separate from their values.
        # Сохраняем полные подписи и отделяем их от значений.
        layout.setColumnMinimumWidth(0, 210)
        layout.setColumnStretch(1, 1)

        title_label = QLabel(title)
        title_label.setObjectName("SubnetCardTitle")
        allow_horizontal_shrink(title_label)
        layout.addWidget(title_label, 0, 0, 1, 2)

        for row_number, (i18n_key, field_key) in enumerate(rows, start=1):
            label = QLabel(self._tr(i18n_key))
            label.setObjectName("SubnetLabel")
            label.setMinimumWidth(210)
            value = QLabel("—")
            value.setObjectName("SubnetValue")
            allow_horizontal_shrink(value)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(label, row_number, 0)
            layout.addWidget(value, row_number, 1)
            self._row_labels[field_key] = label
            self._fields[field_key] = value
        return title_label, card

    def _tr(self, key: str, **kwargs) -> str:
        return self._i18n.get(key, **kwargs) if self._i18n else key

    @staticmethod
    def _format_count(value: int) -> str:
        return f"{value:,}".replace(",", "\u202f")

    def retranslate(self) -> None:
        self._title.setText(self._tr("tools_subnet_title"))
        self._ip_label.setText(self._tr("tools_subnet_ip_label"))
        self._mask_label.setText(self._tr("tools_subnet_mask_label"))
        self._btn_calc.setText(self._tr("tools_subnet_btn_calc"))
        self._address.setPlaceholderText(self._tr("tools_subnet_placeholder"))
        self._results_title.setText(self._tr("tools_subnet_results"))
        self._network_title.setText(self._tr("tools_subnet_network_group"))
        self._range_title.setText(self._tr("tools_subnet_range_group"))
        for i18n_key, field_key in self._NETWORK_ROWS + self._RANGE_ROWS:
            self._row_labels[field_key].setText(self._tr(i18n_key))
        self._calc()

    def _set_status(self, text: str, color_key: str) -> None:
        self._status.setText(text)
        self._status.setStyleSheet(
            f'color: {semantic_color(color_key)}; font-size: 12px;'
        )

    def _calc(self) -> None:
        try:
            selected_prefix = int(self._mask.currentData())
            address, prefix = parse_ipv4_input(
                self._address.text(),
                selected_prefix,
            )
            details = calculate_subnet_details(address, prefix)

            if prefix != selected_prefix:
                index = self._mask.findData(prefix)
                if index >= 0:
                    self._mask.setCurrentIndex(index)
            self._address.setText(address)

            for key in ("ip", "cidr", "network", "mask", "wildcard", "broadcast", "first", "last", "cls"):
                self._fields[key].setText(str(details[key]))
            self._fields["total"].setText(self._format_count(int(details["total"])))
            self._fields["hosts"].setText(self._format_count(int(details["hosts"])))
            self._fields["kind"].setText(
                self._tr(self._KIND_KEYS[str(details["kind"])])
            )
            self._set_status(
                self._tr(
                    "tools_subnet_status",
                    prefix=prefix,
                    hosts=self._format_count(int(details["hosts"])),
                ),
                "STATUS_SUCCESS",
            )
        except (ipaddress.AddressValueError, ipaddress.NetmaskValueError, ValueError):
            self._set_status(
                self._tr("tools_subnet_error_invalid"),
                "STATUS_ERROR",
            )

    def refresh_theme(self, dark: bool) -> None:
        self._dark = dark
