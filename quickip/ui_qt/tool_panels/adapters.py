"""Network-adapter information panel."""

from __future__ import annotations

import base64
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal, QSize
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
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
from quickip.ui_qt.widgets.copyable_views import CopyableTree


_IPCONFIG_PS = """\
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

function prefix2mask($n) {
    if ($n -lt 0 -or $n -gt 32) { return "" }
    $m = [uint32]0
    for ($i=0; $i -lt $n; $i++) { $m = $m -bor ([uint32]1 -shl (31-$i)) }
    return "{0}.{1}.{2}.{3}" -f ([byte](($m -shr 24) -band 255)),([byte](($m -shr 16) -band 255)),([byte](($m -shr 8) -band 255)),([byte]($m -band 255))
}

$allAdapters = Get-NetAdapter | Sort-Object InterfaceIndex
$allIPs      = Get-NetIPAddress      -EA SilentlyContinue
$allIfs      = Get-NetIPInterface    -EA SilentlyContinue
$allRoutes   = Get-NetRoute          -EA SilentlyContinue | Where-Object { $_.DestinationPrefix -in @('0.0.0.0/0','::0/0') }
$allDns      = Get-DnsClientServerAddress -EA SilentlyContinue

foreach ($a in $allAdapters) {
    $idx = $a.ifIndex
    $if4 = $allIfs | Where-Object { $_.InterfaceIndex -eq $idx -and $_.AddressFamily -eq 'IPv4' } | Select-Object -First 1
    $if6 = $allIfs | Where-Object { $_.InterfaceIndex -eq $idx -and $_.AddressFamily -eq 'IPv6' } | Select-Object -First 1

    $medium = "$($a.NdisPhysicalMediumType)"
    $ifType = if ($medium -match 'NativeWifi|WirelessLan|802[.]11') { "Wireless" } `
              elseif ($medium -match '802[.]3|Ethernet') { "Ethernet" } `
              elseif ($a.InterfaceType -eq 71) { "Wireless" } `
              elseif ($a.InterfaceType -eq 6)  { "Ethernet" } `
              else { $medium }

    Write-Output "ADAPTER_START:$($a.Name)"
    Write-Output "Description=$($a.InterfaceDescription)"
    Write-Output "MAC=$($a.MacAddress)"
    Write-Output "Interface Type=$ifType"
    Write-Output "Enabled=$($a.AdminStatus -eq 'Up')"
    Write-Output "Connected=$($a.MediaConnectionState -eq 'Connected')"
    Write-Output "Speed=$($a.LinkSpeed)"
    Write-Output "Interface Index=$idx"
    Write-Output "MTU=$(if ($if4) { $if4.NlMtu } else { '' })"

    # IPv4
    $ips4 = @($allIPs | Where-Object { $_.InterfaceIndex -eq $idx -and $_.AddressFamily -eq 'IPv4' })
    Write-Output "IPv4 - Enabled=$(if ($if4) { 'True' } else { 'False' })"
    Write-Output "IPv4 - DHCP=$(if ($if4) { $if4.Dhcp } else { '' })"
    foreach ($ip in $ips4) {
        Write-Output "IPv4 - IP=$($ip.IPAddress) : $(prefix2mask([int]$ip.PrefixLength))"
    }
    $gw4 = ($allRoutes | Where-Object { $_.InterfaceIndex -eq $idx -and $_.DestinationPrefix -eq '0.0.0.0/0' } | Select-Object -First 1).NextHop
    Write-Output "IPv4 - Gateway=$(if ($gw4) { $gw4 } else { '' })"
    $dns4 = $allDns | Where-Object { $_.InterfaceIndex -eq $idx -and $_.AddressFamily -eq 2 } | Select-Object -First 1
    Write-Output "IPv4 - DNS=$(if ($dns4 -and $dns4.ServerAddresses) { $dns4.ServerAddresses -join ', ' } else { '' })"
    Write-Output "IPv4 - Metric=$(if ($if4) { $if4.InterfaceMetric } else { '' })"

    # IPv6
    $ips6 = @($allIPs | Where-Object { $_.InterfaceIndex -eq $idx -and $_.AddressFamily -eq 'IPv6' })
    Write-Output "IPv6 - Enabled=$(if ($if6) { 'True' } else { 'False' })"
    Write-Output "IPv6 - DHCP=$(if ($if6) { $if6.Dhcp } else { '' })"
    $v6 = ($ips6 | ForEach-Object { "$($_.IPAddress)/$($_.PrefixLength)" }) -join '; '
    Write-Output "IPv6 - IP=$v6"
    $gw6 = ($allRoutes | Where-Object { $_.InterfaceIndex -eq $idx -and $_.DestinationPrefix -eq '::0/0' } | Select-Object -First 1).NextHop
    Write-Output "IPv6 - Gateway=$(if ($gw6) { $gw6 } else { '' })"
    $dns6 = $allDns | Where-Object { $_.InterfaceIndex -eq $idx -and $_.AddressFamily -eq 23 } | Select-Object -First 1
    Write-Output "IPv6 - DNS=$(if ($dns6 -and $dns6.ServerAddresses) { $dns6.ServerAddresses -join ', ' } else { '' })"
    Write-Output "IPv6 - Metric=$(if ($if6) { $if6.InterfaceMetric } else { '' })"

    Write-Output "ADAPTER_END"
}
"""


def _parse_ipconfig(text: str) -> list:
    """Парсит вывод PS-скрипта в список (name, [(key, val), ...])."""
    adapters, current_name, current_props = [], None, []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("ADAPTER_START:"):
            current_name = line[len("ADAPTER_START:"):]
            current_props = []
        elif line == "ADAPTER_END" and current_name is not None:
            adapters.append((current_name, current_props))
            current_name = None
        elif current_name is not None and "=" in line:
            key, _, val = line.partition("=")
            current_props.append((key.strip(), val.strip()))
    return adapters


class IpconfigBridge(QObject):
    done = Signal(list)
    finished = Signal(bool, str)


class IpconfigPanel(QWidget):
    def __init__(self, dark: bool = True, parent=None, i18n=None, runner=None) -> None:
        super().__init__(parent)
        self._dark = dark
        self._i18n = i18n
        self._runner = runner
        self._bridge = IpconfigBridge()
        _t = lambda k: i18n.get(k) if i18n else k  # noqa: E731

        root = QVBoxLayout(self)
        configure_tool_root(root)

        self._hdr = QLabel(_t("tools_ipconfig_title"))
        self._hdr.setObjectName("ToolPanelTitle")
        root.addWidget(self._hdr)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        btn_row.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.btn_run = create_tool_button(
            self._tr("tools_ipconfig_refresh"),
            role="primary",
            min_width=100,
        )
        btn_row.addWidget(self.btn_run, 0, Qt.AlignmentFlag.AlignVCenter)
        btn_row.addStretch(1)
        root.addLayout(btn_row)

        self._tree = CopyableTree(i18n=i18n)
        configure_tool_tree(
            self._tree,
            dark=dark,
            object_name="IpconfigTree",
            root_decorated=True,
        )
        self._tree.setColumnCount(2)
        self._tree.setHeaderLabels([_t("tools_ipconfig_col_param"), _t("tools_ipconfig_col_value")])
        # RU: В двухколоночной таблице обе секции занимают равную долю ширины.
        # EN: Keep both sections of the two-column table equally wide.
        header = self._tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        # RU: Для иерархии адаптеров зебра мешает группировке и в Windows
        # может брать светлый цвет из системной палитры.
        # EN: Zebra rows obscure adapter grouping and may inherit a light
        # system-palette color on Windows.
        self._tree.setAlternatingRowColors(False)
        self._tree.setIndentation(20)
        self._tree.setIconSize(QSize(16, 16))
        root.addWidget(self._tree, 1)

        self._status = QLabel("")
        self._status.setObjectName("ToolStatus")
        root.addWidget(self._status)

        self._bridge.done.connect(self._populate)
        self._bridge.finished.connect(self._on_finished)
        self.btn_run.clicked.connect(self._on_run)

    def _tr(self, key: str) -> str:
        return self._i18n.get(key) if self._i18n else key

    def retranslate(self) -> None:
        self._hdr.setText(self._tr("tools_ipconfig_title"))
        self.btn_run.setText(self._tr("tools_ipconfig_refresh"))
        self._tree.setHeaderLabels([
            self._tr("tools_ipconfig_col_param"),
            self._tr("tools_ipconfig_col_value"),
        ])

    def _on_run(self) -> None:
        self._tree.clear()
        set_tool_busy(self.btn_run, True)
        set_tool_status(
            self._status,
            self._tr("tools_ipconfig_loading"),
            ToolStatusKind.RUNNING,
        )
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self) -> None:
        try:
            encoded = base64.b64encode(_IPCONFIG_PS.encode('utf-16-le')).decode('ascii')
            result = self._runner.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                timeout=30,
            )
            if not result.success:
                raise RuntimeError(
                    (result.stderr or result.stdout).strip()
                    or self._tr("tools_ipconfig_error")
                )
            adapters = _parse_ipconfig(result.stdout)
            self._bridge.done.emit(adapters)
            self._bridge.finished.emit(
                True,
                self._tr("tools_ipconfig_count").format(
                    count=len(adapters)
                ),
            )
        except Exception as exc:
            self._bridge.finished.emit(False, str(exc))

    def _on_finished(self, success: bool, message: str) -> None:
        set_tool_busy(self.btn_run, False)
        set_tool_status(
            self._status,
            message,
            ToolStatusKind.SUCCESS if success else ToolStatusKind.ERROR,
        )

    def _populate(self, adapters: list) -> None:
        assets = Path(__file__).parent.parent / "assets"
        wifi_icon = QIcon(str(assets / "adapter-wifi.svg"))
        net_icon  = QIcon(str(assets / "adapter-network.svg"))

        self._tree.setUpdatesEnabled(False)
        self._tree.clear()
        bold = QFont("Segoe UI", 9)
        bold.setWeight(QFont.Weight.DemiBold)
        small = QFont("Segoe UI", 8)
        tops = []
        for name, props in adapters:
            n_lower = name.lower()
            top = QTreeWidgetItem([name, ""])
            top.setFont(0, bold)
            center_tree_item(top)
            if any(w in n_lower for w in ("wi-fi", "wireless", "wlan", "wifi", "беспроводная")):
                top.setIcon(0, wifi_icon)
            else:
                top.setIcon(0, net_icon)
            for key, val in props:
                child = QTreeWidgetItem(top, [key, val])
                child.setFont(0, small)
                child.setFont(1, small)
                center_tree_item(child)
            tops.append(top)
        self._tree.addTopLevelItems(tops)
        # RU: Название адаптера — заголовок группы на всю ширину таблицы.
        # EN: Render every adapter name as a full-width group heading.
        for row in range(self._tree.topLevelItemCount()):
            self._tree.setFirstColumnSpanned(row, True)
        self._tree.setUpdatesEnabled(True)

    def refresh_theme(self, dark: bool) -> None:
        self._dark = dark
