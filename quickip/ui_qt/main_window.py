"""NetConneXion — main window shell.

Layout (flat design, matches design handoff):

  ┌─────────────────────────────────────────────────────┐
  │  TOPBAR  56px  (#181b28)  logo · name · page · btn  │
  ├──────────┬──────────────────────────────────────────┤
  │ SIDEBAR  │  QStackedWidget (pages)                  │
  │  220px   │                                          │
  │ (#161927)│  (#12141c)                               │
  └──────────┴──────────────────────────────────────────┘

Pages live in separate files:
  - pages/profiles_page.py
  - pages/wifi_page.py
  - pages/tools_page.py
  - pages/settings_page.py
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QColor, QIcon, QPalette, QPixmap
from PySide6 import QtSvg as _QtSvg  # noqa: F401 — registers the SVG image plugin
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow,
    QMenu, QPushButton, QSizePolicy, QStackedWidget, QSystemTrayIcon,
    QVBoxLayout, QWidget,
)

from quickip.app.bootstrap import bootstrap
from quickip.core.events.types import LangChanged, ProfileApplied, ThemeChanged, WifiStatusUpdated
from quickip.shared.privilege_check import is_elevated
from quickip.ui_qt.adapters.profiles_facade import ProfilesFacade
from quickip.ui_qt.theme import load_qss, _resource_root
from quickip.ui_qt.palette import color, semantic_color
from quickip.ui_qt.widgets.backdrop import BackdropWidget
from quickip.ui_qt.pages.profiles_page import ProfilesPage
from quickip.ui_qt.pages.tools_page import ToolsPage
from quickip.ui_qt.pages.settings_page import SettingsPage


@dataclass
class _NavItem:
    key: str
    label: str
    icon: str
    svg: str = ""


class QtMainWindow(QMainWindow):

    def __init__(self) -> None:
        super().__init__()
        self.container = bootstrap()
        self.theme_mode = str(self.container.settings_repo.get("ui_theme", "dark")).lower()
        self._current_page_key = "profiles"

        self.setWindowTitle("NetConneXion")
        _icon_path = _resource_root() / "data" / "logo_tray.png"
        if _icon_path.exists():
            self.setWindowIcon(QIcon(str(_icon_path)))
        self.resize(1240, 780)
        self.setMinimumSize(900, 600)

        # ── Root widget (BackdropWidget handles bg color) ──────────
        self.root = BackdropWidget()
        self.root.setObjectName("RootWindow")
        self.setCentralWidget(self.root)

        root_lay = QVBoxLayout(self.root)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)

        # ── TOPBAR (full-width, 56px) ──────────────────────────────
        self.topbar = QFrame()
        self.topbar.setObjectName("Topbar")
        self.topbar.setFixedHeight(56)
        tb = QHBoxLayout(self.topbar)
        tb.setContentsMargins(20, 0, 16, 0)
        tb.setSpacing(0)

        # Logo area: icon square + app name
        self._logo_icon = QLabel("N")
        self._logo_icon.setObjectName("LogoIcon")
        self._logo_icon.setFixedSize(26, 26)
        self._logo_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._logo_label = QLabel()          # PNG logo (if file exists)
        self._logo_label.setObjectName("LogoImage")
        self._logo_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )

        self._logo_name = QLabel("NetConneXion")
        self._logo_name.setObjectName("LogoName")

        base = _resource_root() / "data"
        self._logo_path_light = base / "logo_light.png"
        self._logo_path_dark  = base / "logo_dark.png"

        tb.addWidget(self._logo_icon)
        tb.addSpacing(10)
        tb.addWidget(self._logo_label)
        tb.addWidget(self._logo_name)

        tb.addStretch(1)

        # Theme toggle
        self.btn_theme = QPushButton()
        self.btn_theme.setObjectName("ThemeBtn")
        self.btn_theme.setProperty("role", "action")
        self.btn_theme.setFixedHeight(34)
        tb.addWidget(self.btn_theme, 0, Qt.AlignmentFlag.AlignVCenter)

        root_lay.addWidget(self.topbar)

        # ── BODY (sidebar + stack) ─────────────────────────────────
        body = QWidget()
        body.setObjectName("Body")
        body_lay = QHBoxLayout(body)
        body_lay.setContentsMargins(0, 0, 0, 0)
        body_lay.setSpacing(0)

        # Sidebar
        self.sidebar = QFrame()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding
        )
        self.sidebar.setFixedWidth(220)
        sb_lay = QVBoxLayout(self.sidebar)
        sb_lay.setContentsMargins(0, 0, 0, 0)
        sb_lay.setSpacing(0)
        body_lay.addWidget(self.sidebar)

        # Main content stack
        self.stack = QStackedWidget()
        self.stack.setObjectName("MainStack")
        body_lay.addWidget(self.stack, 1)

        root_lay.addWidget(body, 1)

        # ── Elevation warning banner (below body) ──────────────────
        self._elevation_banner = self._build_elevation_banner()
        root_lay.addWidget(self._elevation_banner)
        self._elevation_banner.setVisible(False)

        # ── Build content ──────────────────────────────────────────
        self._build_sidebar(sb_lay)
        self._build_pages()

        # ── Connections ────────────────────────────────────────────
        self.btn_theme.clicked.connect(self._toggle_theme)
        self.profiles_page.btn_apply.clicked.connect(
            lambda: self.facade.apply_profile(self.profiles_page.collect_form_data())
        )
        self.profiles_page.btn_save.clicked.connect(
            lambda: self.facade.save_profile(self.profiles_page.collect_form_data())
        )

        self._apply_theme()
        self.facade.bootstrap()
        self._connect_status_events()
        self._setup_tray()

        if self.container.i18n.get_current_locale() != "ru":
            self._retranslate_ui()

        if self.container.elevation_warning:
            QTimer.singleShot(800, self._show_elevation_banner)

        if self.container.settings_repo.get("start_minimized", False):
            self.hide()

    # ── Elevation banner ──────────────────────────────────────────

    def _build_elevation_banner(self) -> QFrame:
        banner = QFrame()
        banner.setObjectName("ElevationBanner")
        banner.setFixedHeight(36)
        banner.setStyleSheet(
            "QFrame#ElevationBanner {"
            f"  background: {semantic_color('ELEVATION_BG')};"
            "  border-radius: 0;"
            "}"
            f"QLabel {{ color: {semantic_color('ELEVATION_TEXT')}; font-size: 12px; }}"
            "QPushButton {"
            f"  color: {semantic_color('ELEVATION_TEXT')}; background: transparent;"
            f"  border: 1px solid {semantic_color('ELEVATION_TEXT')}; border-radius: 4px;"
            "  padding: 2px 8px; font-size: 11px;"
            "}"
            f"QPushButton:hover {{ background: {semantic_color('ELEVATION_BG_HOVER')}; }}"
        )
        lay = QHBoxLayout(banner)
        lay.setContentsMargins(16, 0, 8, 0)
        lay.setSpacing(8)
        lbl = QLabel(
            "⚠  Программа запущена без прав администратора — "
            "изменение IP и Wi-Fi недоступно."
        )
        lbl.setObjectName("ElevationBannerLabel")
        lay.addWidget(lbl, 1)
        btn_close = QPushButton("✕")
        btn_close.setFixedSize(28, 24)
        btn_close.setToolTip("Скрыть предупреждение")
        btn_close.clicked.connect(lambda: banner.setVisible(False))
        lay.addWidget(btn_close)
        return banner

    def _show_elevation_banner(self) -> None:
        if not is_elevated():
            self._elevation_banner.setVisible(True)

    # ── Sidebar ───────────────────────────────────────────────────

    def _build_sidebar(self, sb_lay: QVBoxLayout) -> None:
        nav = QFrame()
        nav.setObjectName("NavFrame")
        nav_lay = QVBoxLayout(nav)
        nav_lay.setContentsMargins(12, 20, 12, 20)
        nav_lay.setSpacing(2)
        self.nav_buttons: dict[str, QPushButton] = {}

        # Group: СЕТЬ
        net_lbl = QLabel(self._tr("nav_group_network"))
        net_lbl.setObjectName("NavGroupLabel")
        self._nav_group_network = net_lbl
        nav_lay.addWidget(net_lbl)

        for item in [
            _NavItem("profiles", self._tr("nav_profiles"), "", svg="nav-profiles.svg"),
            _NavItem("wifi",     "Wi-Fi",                  "",    svg="nav-wifi.svg"),
            _NavItem("tools",    self._tr("nav_tools"),    "⚒"),
        ]:
            b = self._nav_btn(item)
            nav_lay.addWidget(b)
            self.nav_buttons[item.key] = b

        # Group: СИСТЕМА
        nav_lay.addSpacing(8)
        sys_lbl = QLabel(self._tr("nav_group_system"))
        sys_lbl.setObjectName("NavGroupLabel")
        sys_lbl.setContentsMargins(0, 10, 0, 0)
        self._nav_group_system = sys_lbl
        nav_lay.addWidget(sys_lbl)

        si = _NavItem("settings", self._tr("nav_settings"), "⚙")
        sb = self._nav_btn(si)
        nav_lay.addWidget(sb)
        self.nav_buttons[si.key] = sb

        nav_lay.addStretch(1)
        sb_lay.addWidget(nav, 1)

    def _nav_btn(self, item: _NavItem) -> QPushButton:
        if item.svg:
            b = QPushButton(f"  {item.label}")
            svg_path = _resource_root() / "quickip" / "ui_qt" / "assets" / item.svg
            if svg_path.exists():
                b.setIcon(QIcon(str(svg_path)))
                b.setIconSize(QSize(16, 16))
        else:
            b = QPushButton(f"{item.icon}  {item.label}")
        b.setObjectName("NavBtn")
        b.setProperty("active", "false")
        b.setMinimumHeight(40)
        b.clicked.connect(lambda _=False, k=item.key: self._switch_page(k))
        return b

    # ── Pages ─────────────────────────────────────────────────────

    def _build_pages(self) -> None:
        self.facade = ProfilesFacade(self.container, self)
        self.profiles_page = ProfilesPage(self.facade)
        self.stack.addWidget(self.profiles_page)   # 0

        try:
            from quickip.ui_qt.pages.wifi_page import WifiPage
            self.wifi_page = WifiPage(self.container)
        except Exception:
            import logging
            import traceback
            logging.getLogger(__name__).error(
                "WifiPage init failed:\n%s", traceback.format_exc()
            )
            self.wifi_page = QLabel("Wi-Fi unavailable")
        self.stack.addWidget(self.wifi_page)        # 1

        self.tools_page = ToolsPage(self.container)
        self.stack.addWidget(self.tools_page)       # 2

        self.settings_page = SettingsPage(self.container)
        self.stack.addWidget(self.settings_page)    # 3

        self._switch_page("profiles")

    def _switch_page(self, key: str) -> None:
        idx = {"profiles": 0, "wifi": 1, "tools": 2, "settings": 3}.get(key, 0)
        self._current_page_key = key
        self.stack.setCurrentIndex(idx)
        # page title is now shown inside each page's own header
        for k, btn in self.nav_buttons.items():
            btn.setProperty("active", "true" if k == key else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        if key == "wifi" and hasattr(self.wifi_page, "trigger_scan"):
            QTimer.singleShot(100, self.wifi_page.trigger_scan)  # type: ignore[union-attr]

    def _connect_status_events(self) -> None:
        bus = self.container.event_bus
        bus.subscribe(ProfileApplied, self._on_profile_applied)          # type: ignore
        bus.subscribe(WifiStatusUpdated, self._on_wifi_status_updated)   # type: ignore
        bus.subscribe(ThemeChanged, self._on_theme_changed)              # type: ignore
        bus.subscribe(LangChanged, self._on_lang_changed)                # type: ignore

    def _on_profile_applied(self, event) -> None:
        if hasattr(self.profiles_page, "show_apply_result"):
            self.profiles_page.show_apply_result(
                getattr(event, "success", True),
                getattr(event, "profile_name", ""),
                getattr(event, "duration_ms", 0),
            )

    def _on_theme_changed(self, event) -> None:
        mode = getattr(event, "theme", "dark")
        if mode != self.theme_mode:
            self.theme_mode = mode
            QTimer.singleShot(0, self._apply_theme)

    def _on_lang_changed(self, event) -> None:
        QTimer.singleShot(0, self._retranslate_ui)

    def _on_wifi_status_updated(self, event) -> None:
        pass

    # ── Theme ─────────────────────────────────────────────────────

    def _tr(self, key: str) -> str:
        return self.container.i18n.get(key)

    def _retranslate_ui(self) -> None:
        self._nav_group_network.setText(self._tr("nav_group_network"))
        self._nav_group_system.setText(self._tr("nav_group_system"))
        nav_keys = {
            "profiles": "nav_profiles", "tools": "nav_tools", "settings": "nav_settings",
        }
        for key, btn in self.nav_buttons.items():
            tr_key = nav_keys.get(key)
            if tr_key:
                parts = btn.text().split("  ", 1)
                prefix = parts[0] + "  " if len(parts) == 2 else ""
                btn.setText(prefix + self._tr(tr_key))
        # page title is now shown inside each page's own header
        is_dark = self.theme_mode == "dark"
        self.btn_theme.setText(
            self._tr("btn_theme_light") if is_dark else self._tr("btn_theme_dark")
        )
        for pg in (self.profiles_page, self.wifi_page, self.tools_page, self.settings_page):
            if hasattr(pg, "retranslate"):
                pg.retranslate()  # type: ignore[union-attr]

    # ── Tray ──────────────────────────────────────────────────────

    def _setup_tray(self) -> None:
        icon = self._make_tray_icon()
        self._tray = QSystemTrayIcon(icon, self)
        self._tray.setToolTip("NetConneXion")
        menu = QMenu()
        self._tray_action_show = menu.addAction(self._tr("tray_show"))
        menu.addSeparator()
        self._tray_action_quit = menu.addAction(self._tr("tray_quit"))
        self._tray_action_show.triggered.connect(self._tray_restore)
        self._tray_action_quit.triggered.connect(QApplication.quit)
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    @staticmethod
    def _make_tray_icon() -> QIcon:
        icon_path = _resource_root() / "data" / "logo_tray.png"
        if icon_path.exists():
            return QIcon(str(icon_path))
        return QIcon()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._tray_restore()

    def _tray_restore(self) -> None:
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.container.settings_repo.get("minimize_to_tray", False):
            event.ignore()
            self.hide()
        else:
            self._tray.hide()
            event.accept()

    def _toggle_theme(self) -> None:
        self.theme_mode = "light" if self.theme_mode == "dark" else "dark"
        self.container.settings_repo.set("ui_theme", self.theme_mode)
        self._apply_theme()

    def _apply_theme(self) -> None:
        is_dark = self.theme_mode == "dark"
        self.root.set_theme_mode(self.theme_mode)
        self.setStyleSheet(load_qss(self.theme_mode))
        self.btn_theme.setText(
            self._tr("btn_theme_light") if is_dark else self._tr("btn_theme_dark")
        )
        self._update_logo(self.theme_mode)
        self._apply_windows_titlebar(is_dark)

        for pg in (self.profiles_page, self.wifi_page, self.tools_page, self.settings_page):
            if hasattr(pg, "refresh_theme"):
                pg.refresh_theme(is_dark)  # type: ignore[union-attr]

        placeholder_theme = "dark" if is_dark else "light"
        placeholder_prefix = "DARK" if is_dark else "LIGHT"
        ph = QColor(
            color(
                placeholder_theme,
                f"{placeholder_prefix}_CUSTOM_TOPBAR_PLACEHOLDER",
            )
        )
        ph.setAlpha(70 if is_dark else 100)
        pal = self.profiles_page.search.palette()
        pal.setColor(QPalette.ColorRole.PlaceholderText, ph)
        self.profiles_page.search.setPalette(pal)

    def _apply_windows_titlebar(self, dark: bool) -> None:
        try:
            import ctypes
            import ctypes.wintypes
            hwnd = int(self.winId())
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            value = ctypes.c_int(1 if dark else 0)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
                ctypes.byref(value), ctypes.sizeof(value),
            )
        except Exception:
            pass

    def _update_logo(self, theme: str) -> None:
        """Show PNG logo if available, else show 'N' icon square + app name."""
        path = self._logo_path_dark if theme == "dark" else self._logo_path_light
        if path.exists():
            pix = QPixmap(str(path))
            pix = pix.scaledToHeight(30, Qt.TransformationMode.SmoothTransformation)
            if pix.width() > 160:
                pix = pix.scaledToWidth(160, Qt.TransformationMode.SmoothTransformation)
            self._logo_label.setPixmap(pix)
            self._logo_icon.setVisible(False)
            self._logo_name.setVisible(False)
            self._logo_label.setVisible(True)
        else:
            self._logo_label.setVisible(False)
            self._logo_icon.setVisible(True)
            self._logo_name.setVisible(True)


# ── Entry point ───────────────────────────────────────────────────────────────

def _relaunch_as_admin() -> None:
    import ctypes
    import sys
    if getattr(sys, "frozen", False):
        exe = sys.executable
        args = None
        cwd = str(Path(exe).parent)
    else:
        exe = sys.executable
        args = "-m quickip"
        cwd = str(Path(__file__).parent.parent.parent)
    ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, args, cwd, 1)
    if ret > 32:
        sys.exit(0)


def main() -> int:
    app = QApplication.instance() or QApplication([])
    if not is_elevated():
        _relaunch_as_admin()
    w = QtMainWindow()
    w.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
