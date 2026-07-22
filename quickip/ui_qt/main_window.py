"""NetConneXion — main window shell.

Содержит только каркас приложения:
  - BackdropWidget (фон)
  - Sidebar (логотип, навигация, статус)
  - Topbar (заголовок страницы, кнопка темы)
  - ContentShell + QStackedWidget (переключение страниц)

Каждая страница живёт в своём файле:
  - pages/profiles_page.py  <- Profiles
  - pages/wifi_page.py      <- Wi-Fi
  - pages/tools_page.py     <- Tools
  - pages/settings_page.py  <- Settings

Переиспользуемые виджеты:
  - widgets/backdrop.py
  - widgets/elide_label.py
  - widgets/toggle_switch.py
  - widgets/rounded_panel.py
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, QSize
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

        self.root = BackdropWidget()
        self.root.setObjectName("RootWindow")
        self.setCentralWidget(self.root)

        page = QHBoxLayout(self.root)
        page.setContentsMargins(10, 10, 10, 10)
        page.setSpacing(10)

        # Sidebar
        self.sidebar = QFrame()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.sidebar.setFixedWidth(210)
        sb_lay = QVBoxLayout(self.sidebar)
        sb_lay.setContentsMargins(0, 0, 0, 0)
        sb_lay.setSpacing(0)
        page.addWidget(self.sidebar)

        # Right column
        right_widget = QWidget()
        right_widget.setObjectName("RightWidget")
        right_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        right = QVBoxLayout(right_widget)
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(10)
        page.addWidget(right_widget, 1)

        # Topbar
        self.topbar = QFrame()
        self.topbar.setObjectName("Topbar")
        self.topbar.setFixedHeight(52)
        tb = QHBoxLayout(self.topbar)
        tb.setContentsMargins(18, 0, 18, 0)
        tb.setSpacing(12)
        self._page_title = QLabel(self._tr("page_profiles"))
        self._page_title.setObjectName("TopbarTitle")
        tb.addWidget(self._page_title)
        tb.addStretch(1)
        self.btn_theme = QPushButton("Тёмная тема")
        self.btn_theme.setObjectName("ThemeBtn")
        self.btn_theme.setProperty("role", "action")
        self.btn_theme.setFixedHeight(34)
        tb.addWidget(self.btn_theme, 0, Qt.AlignmentFlag.AlignVCenter)
        right.addWidget(self.topbar)

        # ContentShell
        self.content_shell = QFrame()
        self.content_shell.setObjectName("ContentShell")
        cs = QVBoxLayout(self.content_shell)
        cs.setContentsMargins(0, 0, 2, 0)
        cs.setSpacing(0)
        self.stack = QStackedWidget()
        self.stack.setObjectName("MainStack")
        cs.addWidget(self.stack, 1)
        right.addWidget(self.content_shell, 1)

        self._build_sidebar(sb_lay)
        self._build_pages()

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
        # Применяем сохранённый язык ко всем страницам
        if self.container.i18n.get_current_locale() != "ru":
            self._retranslate_ui()

        # ── Elevation warning banner ──────────────────────────────────
        # Создаём баннер заранее (скрытым); показываем через QTimer после show(),
        # чтобы не задерживать появление главного окна.
        self._elevation_banner = self._build_elevation_banner()
        right.addWidget(self._elevation_banner)
        self._elevation_banner.setVisible(False)

        from PySide6.QtCore import QTimer
        if self.container.elevation_warning:
            QTimer.singleShot(800, self._show_elevation_banner)

        # Запустить свёрнутым в трей
        if self.container.settings_repo.get("start_minimized", False):
            self.hide()

    # ── Elevation warning banner ──────────────────────────────────────

    def _build_elevation_banner(self) -> QFrame:
        """Создаёт скрытую жёлтую полосу-предупреждение снизу окна.

        Показывается только если приложение запущено без прав администратора
        (т.е. после того как UAC relaunch был отменён пользователем или
        невозможен по политике).
        """
        banner = QFrame()
        banner.setObjectName("ElevationBanner")
        banner.setFixedHeight(36)
        banner.setStyleSheet(
            "QFrame#ElevationBanner {"
            "  background: #7c5800;"
            "  border-radius: 6px;"
            "  margin: 0 2px 2px 2px;"
            "}"
            "QLabel { color: #ffe08a; font-size: 12px; }"
            "QPushButton {"
            "  color: #ffe08a; background: transparent;"
            "  border: 1px solid #ffe08a; border-radius: 4px;"
            "  padding: 2px 8px; font-size: 11px;"
            "}"
            "QPushButton:hover { background: #a07000; }"
        )
        lay = QHBoxLayout(banner)
        lay.setContentsMargins(12, 0, 8, 0)
        lay.setSpacing(8)

        lbl = QLabel("⚠  Программа запущена без прав администратора — "
                     "изменение IP и Wi-Fi недоступно.")
        lbl.setObjectName("ElevationBannerLabel")
        lay.addWidget(lbl, 1)

        btn_close = QPushButton("✕")
        btn_close.setFixedSize(28, 24)
        btn_close.setToolTip("Скрыть предупреждение")
        btn_close.clicked.connect(lambda: banner.setVisible(False))
        lay.addWidget(btn_close)

        return banner

    def _show_elevation_banner(self) -> None:
        """Показывает баннер, если к этому моменту приложение всё ещё без прав."""
        # Перепроверяем — вдруг relaunch успел отработать в другом потоке
        if not is_elevated():
            self._elevation_banner.setVisible(True)

    # ── Sidebar ───────────────────────────────────────────────────────

    def _build_sidebar(self, sb_lay: QVBoxLayout) -> None:
        # Logo
        logo = QFrame()
        logo.setObjectName("LogoArea")
        logo.setFixedHeight(58)
        logo_lay = QHBoxLayout(logo)
        logo_lay.setContentsMargins(12, 8, 12, 8)
        logo_lay.setSpacing(0)
        self._logo_label = QLabel()
        self._logo_label.setObjectName("LogoImage")
        self._logo_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        logo_lay.addWidget(self._logo_label)
        logo_lay.addStretch(1)
        base = _resource_root() / "data"
        self._logo_path_light = base / "logo_light.png"
        self._logo_path_dark  = base / "logo_dark.png"
        self._update_logo(self.theme_mode)
        sb_lay.addWidget(logo)

        # Nav
        nav = QFrame()
        nav.setObjectName("NavFrame")
        nav_lay = QVBoxLayout(nav)
        nav_lay.setContentsMargins(10, 10, 10, 10)
        nav_lay.setSpacing(0)
        self.nav_buttons: dict[str, QPushButton] = {}

        net_lbl = QLabel(self._tr("nav_group_network"))
        net_lbl.setObjectName("NavGroupLabel")
        self._nav_group_network = net_lbl
        nav_lay.addWidget(net_lbl)

        for item in [
            _NavItem("profiles", self._tr("nav_profiles"), "", svg="nav-profiles.svg"),
            _NavItem("wifi",     "Wi-Fi",                  "",    svg="nav-wifi.svg"),
            _NavItem("tools",    self._tr("nav_tools"),    "\u2692"),
        ]:
            b = self._nav_btn(item)
            nav_lay.addWidget(b)
            self.nav_buttons[item.key] = b

        nav_lay.addSpacing(12)
        sys_lbl = QLabel(self._tr("nav_group_system"))
        sys_lbl.setObjectName("NavGroupLabel")
        self._nav_group_system = sys_lbl
        nav_lay.addWidget(sys_lbl)

        si = _NavItem("settings", self._tr("nav_settings"), "\u2699")
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
                b.setIconSize(QSize(18, 18))
        else:
            b = QPushButton(f"{item.icon}  {item.label}")
        b.setObjectName("NavBtn")
        b.setProperty("active", "false")
        b.setMinimumHeight(44)
        b.clicked.connect(lambda _=False, k=item.key: self._switch_page(k))
        return b

    # ── Pages ─────────────────────────────────────────────────────────

    def _build_pages(self) -> None:
        """Создаёт все страницы.
        Порядок индексов фиксирован — см. _switch_page().
        """
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
            # Заглушка — приложение запустится без Wi-Fi страницы
            from PySide6.QtWidgets import QLabel
            self.wifi_page = QLabel("Wi-Fi unavailable")
        self.stack.addWidget(self.wifi_page)        # 1

        self.tools_page = ToolsPage(self.container)
        self.stack.addWidget(self.tools_page)       # 2

        self.settings_page = SettingsPage(self.container)
        self.stack.addWidget(self.settings_page)    # 3

        self._switch_page("profiles")

    def _switch_page(self, key: str) -> None:
        idx = {"profiles": 0, "wifi": 1, "tools": 2, "settings": 3}.get(key, 0)
        page_keys = {"profiles": "page_profiles", "wifi": "page_wifi",
                     "tools": "page_tools", "settings": "page_settings"}
        self._current_page_key = key
        self.stack.setCurrentIndex(idx)
        self._page_title.setText(self._tr(page_keys.get(key, "page_profiles")))
        for k, btn in self.nav_buttons.items():
            btn.setProperty("active", "true" if k == key else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        # Запускаем сканирование при переходе на вкладку Wi-Fi
        if key == "wifi" and hasattr(self.wifi_page, 'trigger_scan'):
            from PySide6.QtCore import QTimer
            QTimer.singleShot(100, self.wifi_page.trigger_scan)  # type: ignore[union-attr]

    def _connect_status_events(self) -> None:
        bus = self.container.event_bus
        bus.subscribe(ProfileApplied, self._on_profile_applied)  # type: ignore[arg-type]
        bus.subscribe(WifiStatusUpdated, self._on_wifi_status_updated)  # type: ignore[arg-type]
        bus.subscribe(ThemeChanged, self._on_theme_changed)  # type: ignore[arg-type]
        bus.subscribe(LangChanged, self._on_lang_changed)  # type: ignore[arg-type]

    def _on_profile_applied(self, event) -> None:
        success = getattr(event, 'success', True)
        profile_name = getattr(event, 'profile_name', '')
        duration_ms = getattr(event, 'duration_ms', 0)
        if hasattr(self.profiles_page, 'show_apply_result'):
            self.profiles_page.show_apply_result(success, profile_name, duration_ms)

    def _on_theme_changed(self, event) -> None:
        """Обновляем тему при изменении из страницы настроек."""
        from PySide6.QtCore import QTimer
        mode = getattr(event, "theme", "dark")
        if mode != self.theme_mode:
            self.theme_mode = mode
            QTimer.singleShot(0, self._apply_theme)

    def _on_lang_changed(self, event) -> None:
        """Перерисовываем все строки UI при смене языка."""
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self._retranslate_ui)

    def _on_wifi_status_updated(self, event) -> None:
        pass

    # ── Theme ─────────────────────────────────────────────────────────

    def _tr(self, key: str) -> str:
        return self.container.i18n.get(key)

    def _retranslate_ui(self) -> None:
        """Обновляет все строки main_window и всех страниц."""
        # Nav group labels
        self._nav_group_network.setText(self._tr("nav_group_network"))
        self._nav_group_system.setText(self._tr("nav_group_system"))

        # Кнопки навигации
        nav_keys = {"profiles": "nav_profiles", "tools": "nav_tools", "settings": "nav_settings"}
        for key, btn in self.nav_buttons.items():
            tr_key = nav_keys.get(key)
            if tr_key:
                # Сохраняем иконку-префикс
                parts = btn.text().split("  ", 1)
                prefix = parts[0] + "  " if len(parts) == 2 else ""
                btn.setText(prefix + self._tr(tr_key))

        # Заголовок топбара
        page_tr = {"profiles": "page_profiles", "wifi": "page_wifi",
                   "tools": "page_tools", "settings": "page_settings"}
        self._page_title.setText(self._tr(page_tr.get(self._current_page_key, "page_profiles")))

        # Кнопка темы
        is_dark = self.theme_mode == "dark"
        self.btn_theme.setText(self._tr("btn_theme_light") if is_dark else self._tr("btn_theme_dark"))

        # Все страницы
        for pg in (self.profiles_page, self.wifi_page, self.tools_page, self.settings_page):
            if hasattr(pg, "retranslate"):
                pg.retranslate()  # type: ignore[union-attr]

    # ── Tray ──────────────────────────────────────────────────────────

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
        self.btn_theme.setText(self._tr("btn_theme_light") if is_dark else self._tr("btn_theme_dark"))
        self._update_logo(self.theme_mode)
        self._apply_windows_titlebar(is_dark)

        # Передаём тему всем страницам
        for pg in (self.profiles_page, self.wifi_page, self.tools_page, self.settings_page):
            if hasattr(pg, 'refresh_theme'):
                pg.refresh_theme(is_dark)  # type: ignore[union-attr]

        ph = QColor(255, 255, 255, 90) if is_dark else QColor(30, 41, 59, 100)
        pal = self.profiles_page.search.palette()
        pal.setColor(QPalette.ColorRole.PlaceholderText, ph)
        self.profiles_page.search.setPalette(pal)

    def _apply_windows_titlebar(self, dark: bool) -> None:
        """Устанавливает тёмный/светлый title bar через Windows DWM API.
        Работает только на Windows 10 build 19041+ и Windows 11.
        На других ОС — no-op.
        """
        try:
            import ctypes
            import ctypes.wintypes
            hwnd = int(self.winId())
            # DWMWA_USE_IMMERSIVE_DARK_MODE = 20 (Windows 11 / Win10 build 19041+)
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            value = ctypes.c_int(1 if dark else 0)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                DWMWA_USE_IMMERSIVE_DARK_MODE,
                ctypes.byref(value),
                ctypes.sizeof(value),
            )
        except Exception:
            pass  # не Windows или старая версия — игнорируем

    def _update_logo(self, theme: str) -> None:
        path = self._logo_path_dark if theme == "dark" else self._logo_path_light
        if path.exists():
            pix = QPixmap(str(path))
            pix = pix.scaledToHeight(38, Qt.TransformationMode.SmoothTransformation)
            if pix.width() > 178:
                pix = pix.scaledToWidth(178, Qt.TransformationMode.SmoothTransformation)
            self._logo_label.setPixmap(pix)
        else:
            self._logo_label.setText("NetConneXion")


# ── Entry point ───────────────────────────────────────────────────────────────

def _relaunch_as_admin() -> None:
    """Перезапускает процесс с правами администратора через UAC."""
    import ctypes
    import sys

    if getattr(sys, "frozen", False):
        # PyInstaller exe — sys.executable уже и есть NetConneXion.exe
        exe = sys.executable
        args = None
        cwd = str(Path(exe).parent)
    else:
        # Режим разработки — запуск через python -m quickip
        exe = sys.executable
        args = "-m quickip"
        cwd = str(Path(__file__).parent.parent.parent)

    ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, args, cwd, 1)
    if ret > 32:   # успешно запущен новый процесс — завершаем текущий
        sys.exit(0)
    # Пользователь отклонил UAC или политика запрещает elevation — продолжаем без прав


def main() -> int:
    app = QApplication.instance() or QApplication([])

    # netsh для изменения сетевых настроек требует прав администратора.
    # Если прав нет — автоматически запускаем UAC и перезапускаем процесс.
    # Если пользователь отменил UAC — приложение продолжит работу без прав;
    # в этом случае bootstrap() установит elevation_warning и UI покажет баннер.
    if not is_elevated():
        _relaunch_as_admin()
    w = QtMainWindow()
    w.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
