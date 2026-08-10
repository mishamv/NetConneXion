"""Base and simple diagnostic panels used by the Tools page."""

from __future__ import annotations

import ipaddress
import re
import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QFont, QTextCharFormat
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from quickip.ui_qt.tool_panels.components import (
    ToolStatusKind,
    create_tool_button,
    set_tool_busy,
    set_tool_status,
)
from quickip.ui_qt.tool_panels.layout import configure_tool_root
from quickip.ui_qt.palette import semantic_color


class ToolPanelBridge(QObject):
    output        = Signal(str, bool)
    finished      = Signal(bool, str)


class ToolPanel(QWidget):
    def __init__(self, title: str, dark: bool = True, i18n=None, runner=None) -> None:
        super().__init__()
        self._dark = dark
        self._i18n = i18n
        self._runner = runner
        self._bridge = ToolPanelBridge()
        self._running = False
        self._proc = None

        root = QVBoxLayout(self)
        configure_tool_root(root)

        self._hdr = QLabel(title)
        self._hdr.setObjectName("ToolPanelTitle")
        root.addWidget(self._hdr)

        self._form = QHBoxLayout()
        self._form.setSpacing(8)
        self._form.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        root.addLayout(self._form)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        btn_row.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.btn_run = create_tool_button(
            self._tr("tools_btn_run"),
            role="primary",
        )
        self.btn_stop = create_tool_button(
            self._tr("tools_btn_stop"),
        )
        self.btn_stop.setEnabled(False)
        self.btn_clear = create_tool_button(
            self._tr("tools_btn_clear"),
        )
        btn_row.addWidget(self.btn_run, 0, Qt.AlignmentFlag.AlignVCenter)
        btn_row.addWidget(self.btn_stop, 0, Qt.AlignmentFlag.AlignVCenter)
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_clear, 0, Qt.AlignmentFlag.AlignVCenter)
        # Visually centre the action row between the input controls above and
        # the result area below. / Размещаем ряд кнопок визуально посередине
        # между полями ввода сверху и областью результата снизу.
        root.addSpacing(12)
        root.addLayout(btn_row)

        self._output = QTextEdit()
        self._output.setObjectName("ToolOutput")
        self._output.setReadOnly(True)
        self._output.setFont(QFont("Consolas", 10))
        root.addWidget(self._output, 1)

        self._status = QLabel("")
        self._status.setObjectName("ToolStatus")
        root.addWidget(self._status)

        self._bridge.output.connect(self._on_output)
        self._bridge.finished.connect(self._on_finished)
        self.btn_run.clicked.connect(self._on_run)
        self.btn_stop.clicked.connect(self._on_stop)
        self.btn_clear.clicked.connect(self._clear)

    def _tr(self, key: str) -> str:
        return self._i18n.get(key) if self._i18n else key

    def _on_run(self) -> None:
        pass

    def _clear(self) -> None:
        self._output.clear()
        set_tool_status(self._status, "")

    def _on_stop(self) -> None:
        self._running = False
        if self._proc:
            try:
                # cancel(): закрывает stdout, terminate() → wait() → kill() если нужно.
                # Гарантирует отсутствие зомби-процессов (ранее был голый .kill() без wait()).
                self._proc.cancel()
            except Exception:
                pass
        set_tool_busy(self.btn_run, False, stop_button=self.btn_stop)
        set_tool_status(
            self._status,
            self._tr("tools_status_cancelled"),
            ToolStatusKind.NEUTRAL,
        )

    def _set_running(self, running: bool) -> None:
        self._running = running
        set_tool_busy(
            self.btn_run,
            running,
            stop_button=self.btn_stop,
        )

    def _on_output(self, text: str, is_error: bool) -> None:
        if is_error:
            self._output.setTextColor(QColor(semantic_color("STATUS_ERROR")))
            self._output.append(text)
            self._output.setCurrentCharFormat(QTextCharFormat())
        else:
            self._output.setCurrentCharFormat(QTextCharFormat())
            self._output.append(text)
        self._output.verticalScrollBar().setValue(
            self._output.verticalScrollBar().maximum()
        )

    def _on_finished(self, success: bool, summary: str) -> None:
        self._set_running(False)
        set_tool_status(
            self._status,
            summary,
            ToolStatusKind.SUCCESS if success else ToolStatusKind.ERROR,
        )

    def refresh_theme(self, dark: bool) -> None:
        self._dark = dark


class PingPanel(ToolPanel):
    def __init__(self, dark: bool = True, i18n=None, runner=None) -> None:
        super().__init__("Ping", dark, i18n=i18n, runner=runner)
        self._host = QLineEdit()
        self._host.setObjectName("ToolInput")
        self._host.setPlaceholderText(self._tr("tools_ping_placeholder"))
        self._host.setFixedHeight(28)
        self._host.returnPressed.connect(self._on_run)
        self._form.addWidget(self._host, 1)

        self._count_label = QLabel(self._tr("tools_ping_count"))
        self._count_label.setObjectName("FieldLabel")
        self._count = QSpinBox()
        self._count.setObjectName("ToolSpinBox")
        self._count.setRange(1, 100)
        self._count.setValue(3)
        self._count.setFixedWidth(50)
        self._count.setFixedHeight(28)
        self._count.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self._form.addWidget(self._count_label)
        self._form.addWidget(self._count)

    def retranslate(self) -> None:
        self._host.setPlaceholderText(self._tr("tools_ping_placeholder"))
        self._count_label.setText(self._tr("tools_ping_count"))

    def _on_run(self) -> None:
        host = self._host.text().strip()
        if not host:
            set_tool_status(
                self._status,
                self._tr("tools_validation_host"),
                ToolStatusKind.ERROR,
            )
            return
        self._output.clear()
        self._set_running(True)
        set_tool_status(
            self._status,
            self._tr("tools_ping_running").format(host=host),
            ToolStatusKind.RUNNING,
        )
        threading.Thread(target=self._worker, args=(host, self._count.value()), daemon=True).start()

    def _worker(self, host: str, count: int) -> None:
        try:
            cmd = ["ping", "-n", str(count), host]
            self._proc = self._runner.popen(cmd, encoding="cp866", errors="replace")
            times: list = []
            success_count = 0
            try:
                for line in self._proc.stdout or []:  # type: ignore[union-attr]
                    if not self._running:
                        break
                    line = line.rstrip()
                    self._bridge.output.emit(line, False)
                    m = re.search(r"[=<](\d+)\s*мс|time[=<](\d+)\s*ms", line, re.IGNORECASE)
                    if m:
                        ms = float(m.group(1) or m.group(2))
                        times.append(ms)
                        success_count += 1
                    elif re.search(r"timeout|\u043d\u0435\u0434\u043e\u0441\u0442\u0438\u0436\u0438\u043c|timed out", line, re.IGNORECASE):
                        times.append(0)
            finally:
                if self._proc.stdout:
                    self._proc.stdout.close()
                self._proc.wait()
            valid = [t for t in times if t > 0]
            if valid:
                avg = sum(valid) / len(valid)
                if not self._running:
                    return
                self._bridge.finished.emit(
                    success_count > 0,
                    self._tr("tools_ping_summary").format(
                        sent=len(times),
                        received=success_count,
                        average=avg,
                    ),
                )
            elif self._running:
                self._bridge.finished.emit(
                    False,
                    self._tr("tools_ping_timeout_all"),
                )
        except Exception as e:
            self._bridge.finished.emit(False, str(e))

    def refresh_theme(self, dark: bool) -> None:
        super().refresh_theme(dark)


class TraceroutePanel(ToolPanel):
    def __init__(self, dark: bool = True, i18n=None, runner=None) -> None:
        super().__init__("Traceroute", dark, i18n=i18n, runner=runner)
        self._host = QLineEdit()
        self._host.setObjectName("ToolInput")
        self._host.setPlaceholderText(self._tr("tools_placeholder_host"))
        self._host.setFixedHeight(28)
        self._host.returnPressed.connect(self._on_run)
        self._form.addWidget(self._host, 1)

    def retranslate(self) -> None:
        self._host.setPlaceholderText(self._tr("tools_placeholder_host"))

    def _on_run(self) -> None:
        host = self._host.text().strip()
        if not host:
            set_tool_status(
                self._status,
                self._tr("tools_validation_host"),
                ToolStatusKind.ERROR,
            )
            return
        self._output.clear()
        self._set_running(True)
        set_tool_status(
            self._status,
            self._tr("tools_trace_running").format(host=host),
            ToolStatusKind.RUNNING,
        )
        threading.Thread(target=self._worker, args=(host,), daemon=True).start()

    def _worker(self, host: str) -> None:
        try:
            cmd = ["tracert", "-d", "-w", "2000", host]
            self._proc = self._runner.popen(cmd, encoding="cp866", errors="replace")
            hops = 0
            try:
                for line in self._proc.stdout or []:  # type: ignore[union-attr]
                    if not self._running:
                        break
                    line = line.rstrip()
                    self._bridge.output.emit(line, False)
                    if re.match(r"\s*\d+\s", line):
                        hops += 1
            finally:
                if self._proc.stdout:
                    self._proc.stdout.close()
                self._proc.wait()
            if self._running:
                self._bridge.finished.emit(
                    True,
                    self._tr("tools_trace_summary").format(hops=hops),
                )
        except Exception as e:
            self._bridge.finished.emit(False, str(e))


class DnsPanel(ToolPanel):
    system_dns_ready = Signal(str)

    def __init__(self, dark: bool = True, i18n=None, runner=None) -> None:
        super().__init__("DNS Lookup", dark, i18n=i18n, runner=runner)
        self._server_user_edited = False

        self._host = QLineEdit()
        self._host.setObjectName("ToolInput")
        self._host.setPlaceholderText(self._tr("tools_placeholder_domain"))
        self._host.setFixedHeight(28)
        self._host.returnPressed.connect(self._on_run)
        self._form.addWidget(self._host, 1)

        self._server_label = QLabel(self._tr("tools_dns_server"))
        self._server_label.setObjectName("FieldLabel")
        self._server = QLineEdit()
        self._server.setObjectName("ToolInput")
        self._server.setPlaceholderText(self._tr("tools_dns_system_auto"))
        self._server.setToolTip(self._tr("tools_dns_server_hint"))
        self._server.setFixedWidth(175)
        self._server.setFixedHeight(28)
        self._server.returnPressed.connect(self._on_run)
        self._server.textEdited.connect(self._mark_server_edited)
        self._form.addWidget(self._server_label)
        self._form.addWidget(self._server)

        self._type_label = QLabel(self._tr("tools_dns_type"))
        self._type_label.setObjectName("FieldLabel")
        self._type = QComboBox()
        self._type.setObjectName("ToolCombo")
        self._type.addItems(["A", "AAAA", "MX", "NS", "PTR", "TXT", "SOA", "CNAME", "SRV"])
        self._type.setFixedWidth(90)
        self._type.setFixedHeight(28)
        self._form.addWidget(self._type_label)
        self._form.addWidget(self._type)

        self.system_dns_ready.connect(self._set_detected_system_dns)
        if self._runner is not None:
            threading.Thread(target=self._detect_system_dns, daemon=True).start()

    def retranslate(self) -> None:
        self._host.setPlaceholderText(self._tr("tools_placeholder_domain"))
        self._server_label.setText(self._tr("tools_dns_server"))
        self._server.setPlaceholderText(self._tr("tools_dns_system_auto"))
        self._server.setToolTip(self._tr("tools_dns_server_hint"))
        self._type_label.setText(self._tr("tools_dns_type"))

    def _mark_server_edited(self, _text: str) -> None:
        self._server_user_edited = True

    def _set_detected_system_dns(self, address: str) -> None:
        if address and not self._server_user_edited and not self._server.text().strip():
            self._server.setText(address)

    def _detect_system_dns(self) -> None:
        """Read the primary DNS server of the active Windows interface."""
        script = (
            "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false);"
            "$route=Get-NetRoute -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' "
            "-ErrorAction SilentlyContinue | Where-Object {$_.NextHop -ne '0.0.0.0'} | "
            "Sort-Object RouteMetric,InterfaceMetric | Select-Object -First 1;"
            "$dns=@();"
            "if($route){$dns=@((Get-DnsClientServerAddress -InterfaceIndex "
            "$route.InterfaceIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue).ServerAddresses)};"
            "if(-not $dns){$dns=@((Get-DnsClientServerAddress -AddressFamily IPv4 "
            "-ErrorAction SilentlyContinue | ForEach-Object {$_.ServerAddresses}))};"
            "$dns | Where-Object {$_} | Select-Object -First 1"
        )
        candidate = ""
        try:
            result = self._runner.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                timeout=8,
            )
            candidate = self._extract_system_dns(result.stdout or "")
        except Exception:
            pass

        # Some Windows configurations deny Get-DnsClientServerAddress to a
        # non-elevated process.  nslookup still reports the resolver it uses,
        # so keep it as a safe, read-only fallback.
        if not candidate:
            try:
                result = self._runner.run(["nslookup", "localhost"], timeout=5)
                candidate = self._extract_system_dns(result.stdout or "")
            except Exception:
                pass

        if candidate:
            self.system_dns_ready.emit(candidate)

    @staticmethod
    def _extract_system_dns(output: str) -> str:
        """Extract a resolver address from PowerShell or nslookup output."""
        lines = output.splitlines()

        # PowerShell normally returns just one bare address.
        for line in lines:
            candidate = line.strip()
            if not candidate:
                continue
            try:
                return str(ipaddress.ip_address(candidate))
            except ValueError:
                break

        # In nslookup output the resolver is the first Address/Адрес before
        # the queried host's Name/Имя section.
        for line in lines:
            text = line.strip()
            if re.match(r"^(?:Name|Имя)\s*:", text, re.IGNORECASE):
                break
            match = re.match(r"^(?:Address|Адрес)\s*:\s*(.+)$", text, re.IGNORECASE)
            if not match:
                continue
            candidate = match.group(1).strip().split("#", 1)[0]
            try:
                return str(ipaddress.ip_address(candidate))
            except ValueError:
                continue
        return ""

    def _on_run(self) -> None:
        host = self._host.text().strip()
        if not host:
            set_tool_status(
                self._status,
                self._tr("tools_validation_domain"),
                ToolStatusKind.ERROR,
            )
            return
        dns_server = self._server.text().strip()
        if dns_server:
            try:
                ipaddress.ip_address(dns_server)
            except ValueError:
                set_tool_status(
                    self._status,
                    self._tr("tools_validation_dns_server"),
                    ToolStatusKind.ERROR,
                )
                return
        self._output.clear()
        self._set_running(True)
        set_tool_status(
            self._status,
            self._tr("tools_dns_running").format(host=host),
            ToolStatusKind.RUNNING,
        )
        _ALLOWED_QTYPES = {"A", "AAAA", "MX", "NS", "PTR", "TXT", "SOA", "CNAME", "SRV"}
        qtype = self._type.currentText()
        if qtype not in _ALLOWED_QTYPES:
            qtype = "A"
        threading.Thread(
            target=self._worker,
            args=(host, qtype, dns_server),
            daemon=True,
        ).start()

    @staticmethod
    def _build_lookup_command(host: str, qtype: str, dns_server: str = "") -> list[str]:
        command = ["nslookup", f"-type={qtype}", host]
        if dns_server:
            command.append(dns_server)
        return command

    @staticmethod
    def _decode_line(raw: bytes) -> str:
        # Try UTF-8 first (modern Windows with UTF-8 locale)
        try:
            return raw.decode("utf-8").rstrip()
        except UnicodeDecodeError:
            pass
        # CP1251 uses 0xC0–0xDF for Cyrillic uppercase (А–Я)
        # CP866  uses 0x80–0x9F for Cyrillic uppercase (А–Я)
        # Count bytes in each range to pick the right encoding
        cp1251_score = sum(1 for b in raw if 0xC0 <= b <= 0xDF)
        cp866_score  = sum(1 for b in raw if 0x80 <= b <= 0x9F)
        enc = "cp1251" if cp1251_score >= cp866_score else "cp866"
        return raw.decode(enc, errors="replace").rstrip()

    def _worker(self, host: str, qtype: str, dns_server: str = "") -> None:
        try:
            cmd = self._build_lookup_command(host, qtype, dns_server)
            self._proc = self._runner.popen(cmd)
            lines = []
            try:
                for raw_line in iter(self._proc.stdout.readline, b""):  # type: ignore[union-attr]
                    line = self._decode_line(raw_line)
                    lines.append(line)
                    self._bridge.output.emit(line, False)
            finally:
                if self._proc.stdout:
                    self._proc.stdout.close()
                self._proc.wait()
            ok = any(
                "Address" in line
                or "Name" in line
                or "Адрес" in line
                for line in lines
            )
            if self._running:
                self._bridge.finished.emit(
                    ok,
                    self._tr(
                        "tools_dns_ready"
                        if ok
                        else "tools_dns_not_found"
                    ),
                )
        except Exception as e:
            self._bridge.finished.emit(False, str(e))
