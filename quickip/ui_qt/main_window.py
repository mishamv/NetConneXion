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

from PySide6.QtCore import Qt, QEvent, QRectF, QSize
from PySide6.QtGui import QColor, QIcon, QPainterPath, QPalette, QPixmap, QRegion
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow,
    QPushButton, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)

from quickip.app.bootstrap import bootstrap
from quickip.core.events.types import ProfileApplied, WifiStatusUpdated
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

        self.setWindowTitle("NetConneXion")
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
        tb.setContentsMargins(18, 0, 14, 0)
        tb.setSpacing(12)
        self._page_title = QLabel("Profiles")
        self._page_title.setObjectName("TopbarTitle")
        tb.addWidget(self._page_title)
        tb.addStretch(1)
        self.btn_theme = QPushButton("Light mode")
        self.btn_theme.setObjectName("ThemeBtn")
        self.btn_theme.setProperty("role", "action")
        self.btn_theme.setMinimumHeight(32)
        tb.addWidget(self.btn_theme)
        right.addWidget(self.topbar)

        # ContentShell
        self.content_shell = QFrame()
        self.content_shell.setObjectName("ContentShell")
        cs = QVBoxLayout(self.content_shell)
        cs.setContentsMargins(0, 0, 0, 0)
        cs.setSpacing(0)
        self.stack = QStackedWidget()
        self.stack.setObjectName("MainStack")
        cs.addWidget(self.stack, 1)
        right.addWidget(self.content_shell, 1)
        self.content_shell.installEventFilter(self)

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
        self._update_status_block()

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

        net_lbl = QLabel("Network")
        net_lbl.setObjectName("NavGroupLabel")
        nav_lay.addWidget(net_lbl)

        for item in [
            _NavItem("profiles", "Profiles", "\u25A3"),
            _NavItem("wifi",     "Wi-Fi",    "",        svg="nav-wifi.svg"),
            _NavItem("tools",    "Tools",    "\u2692"),
        ]:
            b = self._nav_btn(item)
            nav_lay.addWidget(b)
            self.nav_buttons[item.key] = b

        nav_lay.addSpacing(12)
        sys_lbl = QLabel("System")
        sys_lbl.setObjectName("NavGroupLabel")
        nav_lay.addWidget(sys_lbl)

        si = _NavItem("settings", "Settings", "\u2699")
        sb = self._nav_btn(si)
        nav_lay.addWidget(sb)
        self.nav_buttons[si.key] = sb
        nav_lay.addStretch(1)
        sb_lay.addWidget(nav, 1)

        # Status block
        st = QFrame()
        st.setObjectName("StatusBlock")
        st_lay = QVBoxLayout(st)
        st_lay.setContentsMargins(14, 10, 14, 12)
        st_lay.setSpacing(3)
        r1 = QHBoxLayout()
        self._st_dot = QLabel("\u25cf")
        self._st_dot.setObjectName("StatusDot")
        self._st_active = QLabel("\u2014")
        self._st_active.setObjectName("StatusActive")
        r1.addWidget(self._st_dot)
        r1.addWidget(self._st_active, 1)
        st_lay.addLayout(r1)
        r2 = QHBoxLayout()
        ak = QLabel("Adapter")
        ak.setObjectName("StatusKey")
        self._st_adapter = QLabel("\u2014")
        self._st_adapter.setObjectName("StatusValue")
        r2.addWidget(ak)
        r2.addStretch(1)
        r2.addWidget(self._st_adapter)
        st_lay.addLayout(r2)
        self._st_ip = QLabel("\u2014")
        self._st_ip.setObjectName("StatusIP")
        st_lay.addWidget(self._st_ip)
        sb_lay.addWidget(st)

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
            import logging, traceback
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
        idx    = {"profiles": 0, "wifi": 1, "tools": 2, "settings": 3}.get(key, 0)
        labels = {"profiles": "Profiles", "wifi": "Wi-Fi", "tools": "Tools", "settings": "Settings"}
        self.stack.setCurrentIndex(idx)
        self._page_title.setText(labels.get(key, key.capitalize()))
        for k, btn in self.nav_buttons.items():
            btn.setProperty("active", "true" if k == key else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        # Запускаем сканирование при переходе на вкладку Wi-Fi
        if key == "wifi" and hasattr(self.wifi_page, 'trigger_scan'):
            from PySide6.QtCore import QTimer
            QTimer.singleShot(100, self.wifi_page.trigger_scan)  # type: ignore[union-attr]

    # ── Status Block ──────────────────────────────────────────────────

    def _connect_status_events(self) -> None:
        """Подписываемся на события для обновления StatusBlock."""
        bus = self.container.event_bus
        bus.subscribe(ProfileApplied, self._on_profile_applied)  # type: ignore[arg-type]
        bus.subscribe(WifiStatusUpdated, self._on_wifi_status_updated)  # type: ignore[arg-type]

    def _on_profile_applied(self, event) -> None:
        """Обновляем StatusBlock, feedback и историю после применения профиля."""
        from PySide6.QtCore import QTimer
        # Feedback в profiles_page
        success = getattr(event, 'success', True)
        profile_name = getattr(event, 'profile_name', '')
        duration_ms = getattr(event, 'duration_ms', 0)
        if hasattr(self.profiles_page, 'show_apply_result'):
            self.profiles_page.show_apply_result(success, profile_name, duration_ms)
        # Обновляем StatusBlock
        QTimer.singleShot(1500, self._update_status_block)

    def _on_wifi_status_updated(self, event) -> None:
        """Обновляем StatusBlock при изменении Wi-Fi статуса."""
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self._update_status_block)

    def _update_status_block(self) -> None:
        """Читает текущий IP/адаптер и обновляет StatusBlock в sidebar."""
        import threading
        threading.Thread(target=self._fetch_status_worker, daemon=True).start()

    def _fetch_status_worker(self) -> None:
        """Фоновый поток — получает IP и адаптер через netsh."""
        try:
            import re
            runner = self.container.process_runner
            result = runner.run(
                ["netsh", "interface", "ipv4", "show", "config"],
                timeout=8,
            )
            if not result.stdout:
                return

            # Парсим все интерфейсы, ищем подключённый (с IP не 0.0.0.0)
            blocks = re.split(r'Настройка интерфейса|Configuration for interface', result.stdout)
            best = {}
            for block in blocks:
                ip_m = re.search(r'IP.адрес[^:]*:[^\\d]*(\\d+\\.\\d+\\.\\d+\\.\\d+)', block, re.IGNORECASE)
                if not ip_m or ip_m.group(1) == '0.0.0.0':
                    continue
                iface_m = re.search(r'"([^"]+)"', block)
                iface = iface_m.group(1) if iface_m else '—'
                gw_m = re.search(r'Основной шлюз[^:]*:[^\\d]*(\\d+\\.\\d+\\.\\d+\\.\\d+)', block, re.IGNORECASE)
                best = {
                    'ip': ip_m.group(1),
                    'adapter': iface,
                    'connected': bool(gw_m),
                }
                if gw_m:
                    break  # нашли интерфейс со шлюзом — это активное подключение

            if best:
                from PySide6.QtCore import QTimer
                # Переносим обновление в main thread через замыкание
                _info = best
                QTimer.singleShot(0, lambda i=_info: self._apply_status_block(i))
        except Exception:
            pass

    def _apply_status_block(self, info: dict) -> None:
        """Применяет данные к виджетам StatusBlock (main thread)."""
        ip      = info.get('ip', '—')
        adapter = info.get('adapter', '—')
        connected = info.get('connected', False)

        self._st_active.setText(ip)
        self._st_adapter.setText(adapter[:20])
        self._st_ip.setText('')

        self._st_dot.setProperty("connected", "true" if connected else "false")
        self._st_dot.style().unpolish(self._st_dot)
        self._st_dot.style().polish(self._st_dot)

    # ── Theme ─────────────────────────────────────────────────────────

    def _toggle_theme(self) -> None:
        self.theme_mode = "light" if self.theme_mode == "dark" else "dark"
        self.container.settings_repo.set("ui_theme", self.theme_mode)
        self._apply_theme()

    def _apply_theme(self) -> None:
        is_dark = self.theme_mode == "dark"
        self.root.set_theme_mode(self.theme_mode)
        self.setStyleSheet(load_qss(self.theme_mode))
        self.btn_theme.setText("Light mode" if is_dark else "Dark mode")
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

    # ── ContentShell rounded mask ─────────────────────────────────────

    def eventFilter(self, obj, event) -> bool:
        if obj is self.content_shell and event.type() == QEvent.Type.Resize:
            self._apply_shell_mask()
        return super().eventFilter(obj, event)

    def _apply_shell_mask(self) -> None:
        w, h, r = self.content_shell.width(), self.content_shell.height(), 14
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, w, h), r, r)
        self.content_shell.setMask(QRegion(path.toFillPolygon().toPolygon()))


# ── Entry point ───────────────────────────────────────────────────────────────

def _is_admin() -> bool:
    """Проверяет запущено ли приложение от имени администратора."""
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _relaunch_as_admin() -> None:
    """Перезапускает процесс с правами администратора через UAC."""
    import ctypes
    import sys
    from pathlib import Path

    # sys.executable = путь к python.exe в .venv
    # Передаём явный модульный запуск с правильным рабочим каталогом
    project_dir = str(Path(__file__).parent.parent.parent)
    args = f'-m quickip.ui_qt.main_window'

    ret = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, args, project_dir, 1
    )
    if ret > 32:   # успешно запущен новый процесс — завершаем текущий
        sys.exit(0)
    # Если пользователь отклонил UAC (ret <= 32) — продолжаем без прав


def main() -> int:
    app = QApplication.instance() or QApplication([])

    # netsh для изменения сетевых настроек требует прав администратора.
    # Если прав нет — автоматически запускаем UAC и перезапускаем процесс.
    if not _is_admin():
        _relaunch_as_admin()
    w = QtMainWindow()
    w.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
