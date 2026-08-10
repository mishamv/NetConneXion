"""Smoke and geometry contracts for every Tools-page panel."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QLabel

from quickip.ui_qt.tool_panels.adapters import IpconfigPanel
from quickip.ui_qt.tool_panels.basic import DnsPanel, PingPanel, TraceroutePanel
from quickip.ui_qt.tool_panels.dns_cache import DnsCachePanel
from quickip.ui_qt.tool_panels.ip_batch import IpBatchPanel
from quickip.ui_qt.tool_panels.layout import TOOL_PANEL_MARGINS
from quickip.ui_qt.tool_panels.network_tables import ArpPanel, NetstatPanel
from quickip.ui_qt.tool_panels.port_scan import PortScanPanel
from quickip.ui_qt.tool_panels.routes import RouteTablePanel
from quickip.ui_qt.tool_panels.signal_monitor import SignalMonitorPanel
from quickip.ui_qt.tool_panels.subnet import SubnetCalcPanel
from quickip.ui_qt.tool_panels.web_checks import HttpCheckPanel, SslPanel


PANEL_TYPES = (
    PingPanel,
    TraceroutePanel,
    DnsPanel,
    HttpCheckPanel,
    SslPanel,
    IpconfigPanel,
    NetstatPanel,
    ArpPanel,
    RouteTablePanel,
    SignalMonitorPanel,
    PortScanPanel,
    DnsCachePanel,
    SubnetCalcPanel,
    IpBatchPanel,
)


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("panel_type", PANEL_TYPES)
def test_tool_panel_builds_and_switches_theme(
    qt_app: QApplication,
    panel_type: type,
) -> None:
    panel = panel_type()

    panel.refresh_theme(False)
    panel.refresh_theme(True)

    assert panel.layout() is not None
    assert panel.findChild(QLabel, "ToolPanelTitle") is not None
    panel.deleteLater()


@pytest.mark.parametrize("panel_type", PANEL_TYPES)
def test_tool_panel_uses_shared_outer_margins(
    qt_app: QApplication,
    panel_type: type,
) -> None:
    panel = panel_type()
    margins = panel.layout().contentsMargins()

    assert (
        margins.left(),
        margins.top(),
        margins.right(),
        margins.bottom(),
    ) == TOOL_PANEL_MARGINS
    panel.deleteLater()
def test_subnet_helpers_cover_standard_and_point_to_point_networks() -> None:
    from quickip.ui_qt.tool_panels.subnet import (
        calculate_subnet_details,
        parse_ipv4_input,
        prefix_to_mask,
    )

    assert prefix_to_mask(24) == "255.255.255.0"
    assert parse_ipv4_input("192.168.1.42", 24) == ("192.168.1.42", 24)
    assert parse_ipv4_input("10.0.0.5/255.255.0.0") == ("10.0.0.5", 16)

    standard = calculate_subnet_details("192.168.1.42", 24)
    assert standard["cidr"] == "192.168.1.0/24"
    assert standard["broadcast"] == "192.168.1.255"
    assert standard["first"] == "192.168.1.1"
    assert standard["last"] == "192.168.1.254"
    assert standard["hosts"] == 254
    assert standard["kind"] == "private"

    point_to_point = calculate_subnet_details("10.0.0.8", 31)
    assert point_to_point["first"] == "10.0.0.8"
    assert point_to_point["last"] == "10.0.0.9"
    assert point_to_point["hosts"] == 2

    single = calculate_subnet_details("8.8.8.8", 32)
    assert single["first"] == "8.8.8.8"
    assert single["last"] == "8.8.8.8"
    assert single["hosts"] == 1
    assert single["kind"] == "public"


def test_subnet_panel_has_separate_address_and_mask_controls(
    qt_app: QApplication,
) -> None:
    from PySide6.QtWidgets import QComboBox, QLineEdit

    panel = SubnetCalcPanel()
    address = panel.findChild(QLineEdit, "ToolInput")
    mask = panel.findChild(QComboBox, "ToolCombo")

    assert address is not None
    assert mask is not None
    assert mask.count() == 33
    assert mask.currentData() == 24
    panel.deleteLater()
def test_port_scan_parser_accepts_ranges_and_rejects_invalid_values() -> None:
    from quickip.ui_qt.tool_panels.port_scan import parse_ports

    assert parse_ports("443, 80, 80, 1000-1002") == [80, 443, 1000, 1001, 1002]

    for invalid in ("", "0", "65536", "100-90", "80,,443", "abc"):
        with pytest.raises(ValueError):
            parse_ports(invalid)


def test_port_scan_panel_has_structured_controls_and_results(
    qt_app: QApplication,
) -> None:
    from PySide6.QtWidgets import QProgressBar, QTableWidget

    panel = PortScanPanel()

    assert panel.findChild(QTableWidget, "PortScanTable") is not None
    assert panel.findChild(QProgressBar, "PortScanProgress") is not None
    assert panel._preset.count() == 5
    assert panel.btn_stop.isEnabled() is False
    panel.deleteLater()
def test_dns_cache_parser_preserves_multiple_values_and_localized_keys() -> None:
    from quickip.ui_qt.tool_panels.dns_cache import parse_dns_cache

    text = """
    Record Name . . . . . : example.com
    Record Type . . . . . : 1
    Time To Live  . . . . : 120
    Data Length . . . . . : 4
    A (Host) Record . . . : 192.0.2.10
    A (Host) Record . . . : 192.0.2.11

    Имя записи  . . . . . : ipv6.example
    Тип записи  . . . . . : 28
    Срок жизни  . . . . . : 60
    AAAA-запись . . . . . : 2001:db8::1
    """
    rows = parse_dns_cache(text)

    assert [(row.name, row.record_type, row.ttl, row.data) for row in rows] == [
        ("example.com", "A", 120, "192.0.2.10"),
        ("example.com", "A", 120, "192.0.2.11"),
        ("ipv6.example", "AAAA", 60, "2001:db8::1"),
    ]


def test_dns_cache_panel_has_search_type_filter_and_summary(
    qt_app: QApplication,
) -> None:
    from PySide6.QtWidgets import QComboBox, QLineEdit

    panel = DnsCachePanel()

    assert panel.findChild(QLineEdit, "ToolInput") is not None
    assert panel.findChild(QComboBox, "ToolCombo") is not None
    assert panel._type_filter.count() == 9
    assert panel._total_pill.text()
    panel.deleteLater()



def test_ip_batch_file_loader_and_validation_controls(
    qt_app: QApplication, tmp_path
) -> None:
    from PySide6.QtWidgets import QProgressBar, QTableWidget

    csv_path = tmp_path / "hosts.csv"
    csv_path.write_text(
        "name;ip\nrouter;192.168.1.1\nbad;999.1.1.1\n",
        encoding="utf-8",
    )
    rows, headers = IpBatchPanel._load_file(str(csv_path))

    assert headers == ["name", "ip"]
    assert rows[0]["ip"] == "192.168.1.1"

    panel = IpBatchPanel()
    panel._rows = rows
    panel._headers = headers
    panel._ip_col = "ip"
    panel._build_table(rows, headers, "ip")

    assert panel.findChild(QTableWidget, "IpBatchTable") is not None
    assert panel.findChild(QProgressBar, "IpBatchProgress") is not None
    assert panel._result_filter.count() == 5
    assert panel._total_pill.text()
    panel.deleteLater()



def test_signal_monitor_parser_distinguishes_disconnected_state() -> None:
    disconnected = SignalMonitorPanel._parse(
        "State : disconnected\nSignal : 0%\n"
    )
    connected = SignalMonitorPanel._parse(
        "State : connected\nSSID : Office\nBSSID : 00:11:22:33:44:55\n"
        "Signal : 84%\nChannel : 44\n"
    )
    russian = SignalMonitorPanel._parse(
        "Состояние : подключено\nSSID : Дом\n"
        "BSSID : aa:bb:cc:dd:ee:ff\nСигнал : 70%\nКанал : 6\n"
    )

    assert disconnected["connected"] is False
    assert connected["connected"] is True
    assert connected["dbm"] == -58.0
    assert connected["band"] == "5 GHz"
    assert russian["connected"] is True
    assert russian["band"] == "2.4 GHz"


def test_signal_monitor_uses_responsive_metric_grid(qt_app: QApplication) -> None:
    from PySide6.QtWidgets import QGridLayout

    panel = SignalMonitorPanel()

    assert isinstance(panel._lbl_ssid.parent().parent().layout(), QGridLayout)
    assert len(panel._metric_cards) == 8
    assert panel._btn_clear.text()
    panel.deleteLater()


def test_signal_monitor_connection_badge_uses_semantic_dot_color(qt_app) -> None:
    from quickip.ui_qt.palette import semantic_color
    from quickip.ui_qt.tool_panels.signal_monitor import SignalMonitorPanel

    panel = SignalMonitorPanel()
    panel._set_connection_state(True)
    connected_markup = panel._connection.text()
    assert semantic_color("STATUS_SUCCESS") in connected_markup
    assert "●" in connected_markup

    panel._set_connection_state(False)
    disconnected_markup = panel._connection.text()
    assert semantic_color("TEXT_MUTED_STRONG") in disconnected_markup
    assert semantic_color("STATUS_SUCCESS") not in disconnected_markup


def test_signal_monitor_records_connection_transitions(qt_app) -> None:
    class TranslationStub:
        _values = {
            "tools_signal_connection_event":
                "[{ts}] Connected: {ssid} · {bssid} · {dbm:.0f} dBm",
            "tools_signal_disconnection_event":
                "[{ts}] Wi-Fi connection lost",
        }

        def get(self, key: str) -> str:
            return self._values.get(key, key)

    panel = SignalMonitorPanel(i18n=TranslationStub())
    connected = {
        "connected": True,
        "ssid": "Office",
        "bssid": "00:11:22:33:44:55",
        "dbm": -58.0,
        "signal": 84,
        "channel": "44",
        "band": "5 GHz",
        "rx": "300",
        "tx": "300",
    }
    panel._on_update(connected)
    assert panel._graph.count == 1
    assert "Office" in panel._log.toPlainText()

    panel._on_update({
        "connected": False,
        "ssid": "—",
        "bssid": "—",
        "dbm": -100.0,
        "signal": 0,
        "channel": "—",
        "band": "—",
        "rx": "—",
        "tx": "—",
    })
    assert panel._graph.count == 0
    assert panel._last_connected is False
    assert panel._log.toPlainText().count("\n") >= 1
    panel.deleteLater()


def test_signal_monitor_graph_has_localizable_empty_state(qt_app) -> None:
    panel = SignalMonitorPanel()
    assert panel._graph._empty_text
    panel.deleteLater()


def test_nearby_networks_dialog_sorts_by_signal(qt_app) -> None:
    from quickip.features.wifi.repository import WifiNetworkSnapshot
    from quickip.ui_qt.tool_panels.signal_monitor import NearbyNetworksDialog

    dialog = NearbyNetworksDialog()
    dialog.set_networks([
        WifiNetworkSnapshot("Weak", "00:00:00:00:00:01", 35, "Open", "None", 1, 2.412, 54, "802.11g"),
        WifiNetworkSnapshot("Strong", "00:00:00:00:00:02", 91, "WPA2-Personal", "CCMP", 44, 5.220, 867, "802.11ac"),
    ])

    assert dialog._table.rowCount() == 2
    assert dialog._table.item(0, 0).text() == "Strong"
    assert dialog._table.item(0, 2).text() == "91%"
    assert dialog._refresh.isEnabled()
    dialog.deleteLater()


def test_signal_monitor_exposes_nearby_networks_button(qt_app) -> None:
    panel = SignalMonitorPanel()
    assert panel._btn_nearby.text()
    panel.deleteLater()


def test_nearby_networks_dialog_marks_active_bssid(qt_app) -> None:
    from quickip.features.wifi.repository import WifiNetworkSnapshot
    from quickip.ui_qt.palette import semantic_color
    from quickip.ui_qt.tool_panels.signal_monitor import NearbyNetworksDialog

    network = WifiNetworkSnapshot(
        "Office",
        "aa:bb:cc:dd:ee:ff",
        88,
        "WPA2-Personal",
        "CCMP",
        44,
        5.220,
        867,
        "802.11ac",
    )
    dialog = NearbyNetworksDialog()
    dialog.set_networks([network], active_bssid="AA:BB:CC:DD:EE:FF")

    assert dialog._table.item(0, 0).text().startswith("●")
    assert dialog._table.item(0, 0).foreground().color().name().casefold() == (
        semantic_color("STATUS_SUCCESS").casefold()
    )
    dialog.deleteLater()


def test_nearby_networks_dialog_filters_without_rescanning(qt_app) -> None:
    from quickip.features.wifi.repository import WifiNetworkSnapshot
    from quickip.ui_qt.tool_panels.signal_monitor import NearbyNetworksDialog

    dialog = NearbyNetworksDialog()
    networks = [
        WifiNetworkSnapshot(
            "Cafe", "00:00:00:00:00:01", 70, "Open", "None",
            6, 2.437, 54, "802.11g",
        ),
        WifiNetworkSnapshot(
            "Office", "AA:BB:CC:DD:EE:02", 90, "WPA2-Personal", "CCMP",
            44, 5.220, 867, "802.11ac",
        ),
    ]
    dialog.set_networks(networks)
    assert dialog._table.rowCount() == 2
    assert dialog._last_updated is not None

    dialog._search.setText("aa:bb")
    assert dialog._table.rowCount() == 1
    assert dialog._table.item(0, 0).text() == "Office"

    dialog._search.clear()
    dialog._band_filter.setCurrentIndex(
        dialog._band_filter.findData("2.4")
    )
    assert dialog._table.rowCount() == 1
    assert dialog._table.item(0, 0).text() == "Cafe"

    dialog._band_filter.setCurrentIndex(
        dialog._band_filter.findData("all")
    )
    dialog._security_filter.setCurrentIndex(
        dialog._security_filter.findData("protected")
    )
    assert dialog._table.rowCount() == 1
    assert dialog._table.item(0, 0).text() == "Office"
    dialog.deleteLater()


def test_nearby_networks_dialog_pins_active_and_sorts_columns(qt_app) -> None:
    from quickip.features.wifi.repository import WifiNetworkSnapshot
    from quickip.ui_qt.tool_panels.signal_monitor import NearbyNetworksDialog

    dialog = NearbyNetworksDialog()
    networks = [
        WifiNetworkSnapshot(
            "Zulu", "00:00:00:00:00:01", 95, "Open", "None",
            1, 2.412, 54, "802.11g",
        ),
        WifiNetworkSnapshot(
            "Active", "00:00:00:00:00:02", 45, "WPA2-Personal", "CCMP",
            44, 5.220, 867, "802.11ac",
        ),
        WifiNetworkSnapshot(
            "Alpha", "00:00:00:00:00:03", 70, "WPA2-Personal", "CCMP",
            6, 2.437, 54, "802.11g",
        ),
    ]
    dialog.set_networks(networks, active_bssid="00:00:00:00:00:02")

    assert dialog._table.item(0, 0).text().startswith("●  Active")
    dialog._change_sort(0)
    assert dialog._table.item(0, 0).text().startswith("●  Active")
    assert dialog._table.item(1, 0).text() == "Alpha"
    assert dialog._table.item(2, 0).text() == "Zulu"
    dialog.deleteLater()


def test_nearby_networks_dialog_copies_raw_ssid_and_bssid(qt_app) -> None:
    from PySide6.QtWidgets import QApplication
    from quickip.features.wifi.repository import WifiNetworkSnapshot
    from quickip.ui_qt.tool_panels.signal_monitor import NearbyNetworksDialog

    dialog = NearbyNetworksDialog()
    dialog.set_networks([
        WifiNetworkSnapshot(
            "Office", "AA:BB:CC:DD:EE:FF", 88,
            "WPA2-Personal", "CCMP", 44, 5.220, 867, "802.11ac",
        ),
    ], active_bssid="aa:bb:cc:dd:ee:ff")
    dialog._table.selectRow(0)
    assert dialog._copy_ssid.isEnabled()
    assert dialog._copy_bssid.isEnabled()

    dialog._copy_selected(0)
    assert QApplication.clipboard().text() == "Office"
    dialog._copy_selected(1)
    assert QApplication.clipboard().text() == "AA:BB:CC:DD:EE:FF"
    dialog.deleteLater()


def test_nearby_networks_dialog_keeps_cached_rows_on_error(qt_app) -> None:
    from quickip.features.wifi.repository import WifiNetworkSnapshot
    from quickip.ui_qt.tool_panels.signal_monitor import NearbyNetworksDialog

    dialog = NearbyNetworksDialog()
    dialog.set_networks([
        WifiNetworkSnapshot(
            "Office", "AA:BB:CC:DD:EE:FF", 88,
            "WPA2-Personal", "CCMP", 44, 5.220, 867, "802.11ac",
        ),
    ])
    dialog.set_error("netsh failed")

    assert dialog._table.rowCount() == 1
    assert dialog._table.item(0, 0).text() == "Office"
    assert "netsh failed" in dialog._status.text()
    assert dialog._refresh.isEnabled()
    dialog.deleteLater()


def test_signal_monitor_recognizes_fresh_nearby_cache(qt_app) -> None:
    import datetime
    from quickip.features.wifi.repository import WifiNetworkSnapshot
    from quickip.ui_qt.tool_panels.signal_monitor import (
        NearbyNetworksDialog,
        SignalMonitorPanel,
    )

    panel = SignalMonitorPanel()
    panel._nearby_dialog = NearbyNetworksDialog(parent=panel)
    panel._nearby_dialog.set_networks([
        WifiNetworkSnapshot(
            "Office", "AA:BB:CC:DD:EE:FF", 88,
            "WPA2-Personal", "CCMP", 44, 5.220, 867, "802.11ac",
        ),
    ])
    assert panel._nearby_cache_is_fresh()

    panel._nearby_dialog._last_updated = (
        datetime.datetime.now()
        - datetime.timedelta(seconds=panel._NEARBY_CACHE_SECONDS + 1)
    )
    assert not panel._nearby_cache_is_fresh()
    panel.deleteLater()


def test_shared_tool_button_contract(qt_app) -> None:
    from PySide6.QtWidgets import QSizePolicy
    from quickip.ui_qt.tool_panels.components import (
        TOOL_BUTTON_HEIGHT,
        TOOL_BUTTON_MIN_WIDTH,
        create_tool_button,
    )

    button = create_tool_button("Run", role="primary")
    assert button.objectName() == "ToolBtn"
    assert button.property("role") == "primary"
    assert button.minimumWidth() == TOOL_BUTTON_MIN_WIDTH
    assert button.minimumHeight() == TOOL_BUTTON_HEIGHT
    assert button.sizePolicy().horizontalPolicy() == (
        QSizePolicy.Policy.Preferred
    )
    button.deleteLater()


@pytest.mark.parametrize(
    "panel_type",
    (
        PingPanel,
        IpconfigPanel,
        NetstatPanel,
        ArpPanel,
        RouteTablePanel,
        SignalMonitorPanel,
        PortScanPanel,
        DnsCachePanel,
        SubnetCalcPanel,
    ),
)
def test_migrated_panels_use_shared_button_geometry(
    qt_app,
    panel_type,
) -> None:
    from PySide6.QtWidgets import QPushButton
    from quickip.ui_qt.tool_panels.components import TOOL_BUTTON_HEIGHT

    panel = panel_type()
    buttons = panel.findChildren(QPushButton, "ToolBtn")
    assert buttons
    assert all(
        button.minimumHeight() == TOOL_BUTTON_HEIGHT
        for button in buttons
    )
    panel.deleteLater()


def test_copyable_table_has_shared_read_only_defaults(qt_app) -> None:
    from PySide6.QtWidgets import QAbstractItemView
    from quickip.ui_qt.widgets.copyable_views import CopyableTable

    table = CopyableTable(0, 2)
    assert table.selectionBehavior() == (
        QAbstractItemView.SelectionBehavior.SelectRows
    )
    assert table.selectionMode() == (
        QAbstractItemView.SelectionMode.ExtendedSelection
    )
    assert table.editTriggers() == (
        QAbstractItemView.EditTrigger.NoEditTriggers
    )
    assert table.alternatingRowColors()
    assert not table.showGrid()
    assert table.verticalHeader().isHidden()
    table.deleteLater()


def test_copyable_views_localize_context_action_labels(qt_app) -> None:
    from quickip.ui_qt.widgets.copyable_views import _copy_action_text

    class I18n:
        def get(self, key):
            return {"ui_copy_cell": "Localized cell"}.get(key, key)

    assert _copy_action_text(I18n(), "ui_copy_cell") == "Localized cell"
    assert _copy_action_text(None, "ui_copy_row") == "Copy row"


def test_shared_tool_components_configure_busy_state_and_tree(qt_app) -> None:
    from PySide6.QtWidgets import QPushButton, QTreeWidget
    from quickip.ui_qt.tool_panels.components import (
        configure_tool_tree,
        set_tool_busy,
    )

    run = QPushButton()
    stop = QPushButton()
    set_tool_busy(run, True, stop_button=stop)
    assert not run.isEnabled()
    assert stop.isEnabled()
    set_tool_busy(run, False, stop_button=stop)
    assert run.isEnabled()
    assert not stop.isEnabled()

    tree = QTreeWidget()
    configure_tool_tree(tree, dark=True, object_name="ContractTree")
    assert tree.objectName() == "ContractTree"
    assert tree.uniformRowHeights()
    assert not tree.rootIsDecorated()


def test_table_panels_capture_filters_before_worker_thread(qt_app) -> None:
    netstat = NetstatPanel()
    netstat._filter.setCurrentIndex(1)
    netstat._runner = object()
    netstat._on_run = netstat._on_run
    netstat._filter_mode = (
        netstat._filter.currentIndex(),
        netstat._filter.currentText(),
    )
    assert netstat._filter_mode == (1, "TCP")

    routes = RouteTablePanel()
    routes._filter.setCurrentIndex(2)
    routes._filter_index = routes._filter.currentIndex()
    assert routes._filter_index == 2
    netstat.deleteLater()
    routes.deleteLater()


def test_basic_panels_use_shared_semantic_statuses(qt_app) -> None:
    from quickip.ui_qt.tool_panels.components import ToolStatusKind

    panels = (PingPanel(), TraceroutePanel(), DnsPanel(), HttpCheckPanel(), SslPanel())
    for panel in panels:
        panel._on_run()
        assert panel._status.property("statusKind") == ToolStatusKind.ERROR.value
        assert panel._status.text()
        panel.deleteLater()


def test_dns_lookup_command_uses_selected_dns_server() -> None:
    assert DnsPanel._build_lookup_command("example.com", "AAAA", "1.1.1.1") == [
        "nslookup",
        "-type=AAAA",
        "example.com",
        "1.1.1.1",
    ]
    assert DnsPanel._build_lookup_command("example.com", "A") == [
        "nslookup",
        "-type=A",
        "example.com",
    ]


def test_dns_panel_extracts_system_resolver() -> None:
    assert DnsPanel._extract_system_dns("192.168.16.20\r\n") == "192.168.16.20"
    assert DnsPanel._extract_system_dns(
        "Server:  UnKnown\r\n"
        "Address:  192.168.16.20\r\n\r\n"
        "Name:    localhost\r\n"
        "Addresses:  ::1\r\n          127.0.0.1\r\n"
    ) == "192.168.16.20"


def test_tool_panel_clear_resets_output_and_status(qt_app) -> None:
    panel = PingPanel()
    panel._output.setPlainText("old output")
    panel._status.setText("old status")
    panel._clear()
    assert not panel._output.toPlainText()
    assert not panel._status.text()
    panel.deleteLater()


def test_remaining_panels_use_shared_semantic_statuses(qt_app) -> None:
    from quickip.ui_qt.tool_panels.components import ToolStatusKind

    port = PortScanPanel()
    port._on_run()
    assert port._status.property("statusKind") == ToolStatusKind.ERROR.value

    dns = DnsCachePanel()
    dns._refresh()
    assert dns._status.property("statusKind") == ToolStatusKind.ERROR.value

    signal = SignalMonitorPanel()
    signal._start()
    assert signal._status.property("statusKind") == ToolStatusKind.ERROR.value

    for panel in (port, dns, signal):
        panel.deleteLater()


def test_remaining_panel_clear_resets_semantic_status(qt_app) -> None:
    from quickip.ui_qt.tool_panels.components import ToolStatusKind

    port = PortScanPanel()
    port._status.setText("old")
    port._clear()
    assert port._status.property("statusKind") == ToolStatusKind.NEUTRAL.value

    signal = SignalMonitorPanel()
    signal._status.setText("old")
    signal._clear()
    assert not signal._status.text()
    assert signal._status.property("statusKind") == ToolStatusKind.NEUTRAL.value


@pytest.mark.parametrize("panel_type", PANEL_TYPES)
@pytest.mark.parametrize("dark", (False, True))
@pytest.mark.parametrize("size", ((760, 600), (1240, 780)))
def test_tool_panel_lays_out_at_supported_sizes(
    qt_app: QApplication,
    panel_type: type,
    dark: bool,
    size: tuple[int, int],
) -> None:
    """Every tool must complete layout at compact and normal sizes."""
    panel = panel_type(dark=dark)
    panel.refresh_theme(dark)
    panel.resize(*size)
    if panel.layout() is not None:
        panel.layout().setGeometry(panel.rect())
        panel.layout().activate()

    assert panel.width() == size[0]
    assert panel.height() == size[1]
    assert panel.layout() is not None
    assert panel.layout().geometry().width() == size[0]
    assert panel.layout().geometry().height() == size[1]

    panel.deleteLater()


def test_dns_cache_toolbar_has_stable_visual_order(qt_app) -> None:
    from PySide6.QtCore import QPoint

    panel = DnsCachePanel()
    panel.resize(1220, 900)
    panel.show()
    qt_app.processEvents()

    positions = {
        name: getattr(panel, name).mapTo(panel, QPoint(0, 0))
        for name in ("_search", "_type_filter", "_btn_ref", "_btn_flush")
    }
    assert positions["_search"].y() < positions["_type_filter"].y()
    assert (
        positions["_type_filter"].y()
        == positions["_btn_ref"].y()
        == positions["_btn_flush"].y()
    )
    assert (
        positions["_type_filter"].x()
        < positions["_btn_ref"].x()
        < positions["_btn_flush"].x()
    )
    panel.close()
    panel.deleteLater()


def test_ip_batch_controls_have_stable_visual_order(qt_app) -> None:
    panel = IpBatchPanel()
    panel.resize(1220, 900)
    panel.show()
    qt_app.processEvents()

    assert (
        panel._btn_open.y()
        == panel._col_combo.y()
        == panel._ed_timeout.y()
        == panel._ed_workers.y()
    )
    assert panel._btn_open.x() < panel._col_combo.x() < panel._ed_timeout.x()
    assert panel._ed_timeout.x() < panel._ed_workers.x()
    assert panel.btn_run.y() == panel.btn_stop.y() == panel._search.y()
    assert panel._search.y() == panel._result_filter.y()
    assert panel.btn_run.x() < panel.btn_stop.x() < panel._search.x()
    assert panel._search.x() < panel._result_filter.x()
    panel.close()
    panel.deleteLater()


@pytest.mark.parametrize(
    ("panel_type", "control_names"),
    (
        (DnsCachePanel, ("_search", "_type_filter", "_btn_ref", "_btn_flush")),
        (
            IpBatchPanel,
            (
                "_btn_open", "_col_combo", "_ed_timeout", "_ed_workers",
                "btn_run", "btn_stop", "_search", "_result_filter",
            ),
        ),
    ),
)
def test_compact_toolbar_controls_stay_inside_right_edge(
    qt_app, panel_type, control_names
) -> None:
    from PySide6.QtCore import QPoint

    panel = panel_type(dark=True)
    panel.resize(1220, 900)
    panel.show()
    qt_app.processEvents()

    rectangles = {}
    for name in control_names:
        control = getattr(panel, name)
        top_left = control.mapTo(panel, QPoint(0, 0))
        left = top_left.x()
        assert left >= 0, name
        assert left + control.width() <= panel.width(), name
        rectangles[name] = control.geometry().translated(top_left - control.pos())

    if panel_type is IpBatchPanel:
        assert not rectangles["btn_run"].intersects(rectangles["btn_stop"])

    panel.close()
    panel.deleteLater()


def test_adapters_refresh_button_has_localized_user_facing_label(qt_app) -> None:
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    for locale, expected in (("ru", "Обновить список"), ("en", "Refresh list")):
        data = json.loads(
            (root / "data" / "locales" / f"{locale}.json").read_text(
                encoding="utf-8"
            )
        )
        label = data["tools_ipconfig_refresh"]
        assert expected in label
        assert not label.startswith("tools_")
