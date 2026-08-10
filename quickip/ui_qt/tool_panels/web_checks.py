"""HTTP and TLS diagnostic panels."""

from __future__ import annotations

import datetime
import socket
import ssl
import threading
import time
import urllib.error
import urllib.request

from PySide6.QtWidgets import QLineEdit

from quickip.ui_qt.tool_panels.basic import ToolPanel
from quickip.ui_qt.tool_panels.components import (
    ToolStatusKind,
    set_tool_status,
)


class HttpCheckPanel(ToolPanel):
    def __init__(self, dark: bool = True, i18n=None) -> None:
        super().__init__("HTTP Check", dark, i18n=i18n)
        self._url = QLineEdit()
        self._url.setObjectName("ToolInput")
        self._url.setPlaceholderText("https://example.com")
        self._url.setFixedHeight(28)
        self._url.returnPressed.connect(self._on_run)
        self._form.addWidget(self._url, 1)

    def _on_run(self) -> None:
        url = self._url.text().strip()
        if not url:
            set_tool_status(
                self._status,
                self._tr("tools_validation_url"),
                ToolStatusKind.ERROR,
            )
            return
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
            self._url.setText(url)
        self._output.clear()
        self._set_running(True)
        set_tool_status(
            self._status,
            self._tr("tools_http_running").format(url=url),
            ToolStatusKind.RUNNING,
        )
        threading.Thread(target=self._worker, args=(url,), daemon=True).start()

    def _worker(self, url: str) -> None:
        try:

            ctx = ssl.create_default_context()  # TLS verification enabled by default

            _CONNECT_TIMEOUT = 8   # seconds to establish connection
            _READ_TIMEOUT    = 10  # seconds to read response headers
            _MAX_BODY_BYTES  = 4 * 1024  # read at most 4 KB of body

            self._bridge.output.emit(f"  URL:      {url}", False)
            self._bridge.output.emit("  TLS verify: ON", False)

            redirects = []
            current = url
            for _ in range(10):
                req = urllib.request.Request(current, headers={"User-Agent": "NetConneXion/1.0"})
                t0 = time.monotonic()
                try:
                    with urllib.request.urlopen(
                        req, timeout=_READ_TIMEOUT, context=ctx
                    ) as resp:
                        resp.read(_MAX_BODY_BYTES)  # drain limited body to complete handshake
                        elapsed = int((time.monotonic() - t0) * 1000)
                        status = resp.status
                        final_url = resp.url
                        headers = dict(resp.headers)
                        content_type = headers.get("Content-Type", "—")
                        content_len = headers.get("Content-Length", "—")
                        server = headers.get("Server", "—")

                        if redirects:
                            self._bridge.output.emit(f"\n  Редиректы ({len(redirects)}):", False)
                            for r in redirects:
                                self._bridge.output.emit(f"    → {r}", False)

                        self._bridge.output.emit(f"\n  Статус:       {status}", False)
                        self._bridge.output.emit(f"  Время:        {elapsed} ms", False)
                        self._bridge.output.emit(f"  Финальный URL:{final_url}", False)
                        self._bridge.output.emit(f"  Content-Type: {content_type}", False)
                        self._bridge.output.emit(f"  Content-Len:  {content_len}", False)
                        self._bridge.output.emit(f"  Server:       {server}", False)

                        # TLS info
                        if hasattr(resp, "fp") and hasattr(resp.fp, "raw"):
                            sock = getattr(resp.fp.raw, "_sock", None)
                            if sock and hasattr(sock, "cipher"):
                                cipher = sock.cipher()
                                self._bridge.output.emit(f"  TLS:          {cipher[1]} / {cipher[0]}", False)

                        self._bridge.finished.emit(True, f"HTTP {status} — {elapsed} ms")
                        return
                except urllib.error.HTTPError as e:
                    elapsed = int((time.monotonic() - t0) * 1000)
                    self._bridge.output.emit(f"\n  Статус: {e.code} {e.reason}", True)
                    self._bridge.finished.emit(False, f"HTTP {e.code} — {elapsed} ms")
                    return
                except urllib.error.URLError as e:
                    if hasattr(e, "reason") and "Moved" in str(e.reason):
                        redirects.append(current)
                        current = str(e.reason)
                        continue
                    raise
            self._bridge.finished.emit(
                False,
                self._tr("tools_http_too_many_redirects"),
            )
        except Exception as e:
            self._bridge.finished.emit(False, str(e))


class SslPanel(ToolPanel):
    def __init__(self, dark: bool = True, i18n=None) -> None:
        super().__init__("SSL Certificate", dark, i18n=i18n)
        self._host = QLineEdit()
        self._host.setObjectName("ToolInput")
        self._host.setPlaceholderText(self._tr("tools_placeholder_ssl"))
        self._host.setFixedHeight(28)
        self._host.returnPressed.connect(self._on_run)
        self._form.addWidget(self._host, 1)

    def retranslate(self) -> None:
        self._host.setPlaceholderText(self._tr("tools_placeholder_ssl"))

    def _on_run(self) -> None:
        host = self._host.text().strip().removeprefix("https://").removeprefix("http://").rstrip("/")
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
            self._tr("tools_ssl_running").format(host=host),
            ToolStatusKind.RUNNING,
        )
        threading.Thread(target=self._worker, args=(host,), daemon=True).start()

    def _worker(self, host: str) -> None:
        try:
            if ":" in host:
                hostname, port_s = host.rsplit(":", 1)
                port = int(port_s)
            else:
                hostname, port = host, 443

            ctx = ssl.create_default_context()
            with socket.create_connection((hostname, port), timeout=8) as sock:
                with ctx.wrap_socket(sock, server_hostname=hostname) as ssock:
                    cert = ssock.getpeercert()
                    cipher = ssock.cipher()

            if cert is None:
                self._bridge.finished.emit(
                    False,
                    self._tr("tools_ssl_not_received"),
                )
                return

            def fmt_name(fields) -> str:
                return ", ".join(f"{k}={v}" for rdn in (fields or []) for k, v in rdn)

            subject    = fmt_name(cert.get("subject"))
            issuer     = fmt_name(cert.get("issuer"))
            not_before = str(cert.get("notBefore", "—"))
            not_after  = str(cert.get("notAfter",  "—"))

            days_left: int | None = None
            try:
                exp = datetime.datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z")
                days_left = (exp - datetime.datetime.utcnow()).days
                expiry_str = f"{not_after}  ({days_left} дн.)"
            except Exception:
                expiry_str = not_after

            san_raw  = cert.get("subjectAltName") or []
            san_list = [str(v) for t, v in san_raw if t == "DNS"]

            tls_ver = cipher[1] if cipher else "—"
            tls_alg = cipher[0] if cipher else "—"

            lines = [
                f"  {'Хост':<18} {hostname}:{port}",
                f"  {'Subject':<18} {subject}",
                f"  {'Issuer':<18} {issuer}",
                f"  {'Valid From':<18} {not_before}",
                f"  {'Valid To':<18} {expiry_str}",
                f"  {'TLS версия':<18} {tls_ver}",
                f"  {'Шифр':<18} {tls_alg}",
                "",
                f"  SAN ({len(san_list)}):",
            ]
            for s in san_list:
                lines.append(f"    • {s}")

            for line in lines:
                self._bridge.output.emit(line, False)

            if days_left is None:
                self._bridge.finished.emit(
                    True,
                    self._tr("tools_ssl_received"),
                )
            elif days_left < 0:
                self._bridge.finished.emit(
                    False,
                    self._tr("tools_ssl_expired").format(
                        days=-days_left
                    ),
                )
            elif days_left <= 30:
                self._bridge.finished.emit(
                    False,
                    self._tr("tools_ssl_expires_soon").format(
                        days=days_left
                    ),
                )
            else:
                self._bridge.finished.emit(
                    True,
                    self._tr("tools_ssl_valid").format(days=days_left),
                )
        except ssl.SSLCertVerificationError as exc:
            self._bridge.finished.emit(
                False,
                self._tr("tools_ssl_verify_error").format(error=exc),
            )
        except Exception as e:
            self._bridge.finished.emit(False, str(e))
