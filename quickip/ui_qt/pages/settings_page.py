"""Settings page — theme, language, autostart."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from quickip.features.settings.presenter import SettingsPresenter

if TYPE_CHECKING:
    from quickip.app.bootstrap import ServiceContainer

_APP_REG_KEY = "NetConneXion"
_REG_RUN_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"


class SettingsPage(QWidget):
    """Страница настроек: тема, язык, автозапуск."""

    def __init__(self, container: "ServiceContainer") -> None:
        super().__init__()
        self._container = container
        self._presenter = SettingsPresenter(container)
        self._build()
        self._presenter.bind_view(self)
        self._presenter.load_settings()

    # ── Build ─────────────────────────────────────────────────────

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        root.addWidget(scroll)

        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(24, 20, 42, 20)  # 42px справа — отступ под скроллбар
        lay.setSpacing(16)
        scroll.setWidget(body)

        # Внешний вид
        self._card_appearance, self._lbl_sec_appearance = self._card(
            "ВНЕШНИЙ ВИД", [self._theme_row()]
        )
        lay.addWidget(self._card_appearance)

        # Язык
        self._lang_card, self._lbl_sec_language = self._card(
            "ЯЗЫК", [self._lang_row()]
        )
        lay.addWidget(self._lang_card)

        # Wi-Fi
        self._chk_auto_scan = QCheckBox("Автоматическое сканирование при открытии")
        self._chk_auto_scan.setChecked(
            bool(self._container.settings_repo.get("wifi_auto_scan", True))
        )
        self._chk_auto_scan.stateChanged.connect(self._on_auto_scan)

        scan_row = QWidget()
        scan_row.setObjectName("SettingsRow")
        scan_lay = QHBoxLayout(scan_row)
        scan_lay.setContentsMargins(0, 0, 0, 0)
        scan_lay.setSpacing(8)
        self._lbl_scan_interval = QLabel("Интервал авто-обновления (сек)")
        self._lbl_scan_interval.setObjectName("FieldLabel")
        scan_lay.addWidget(self._lbl_scan_interval)
        scan_lay.addStretch(1)
        self._spin_scan_interval = QSpinBox()
        self._spin_scan_interval.setObjectName("SettingsSpinBox")
        self._spin_scan_interval.setRange(10, 600)
        self._spin_scan_interval.setSingleStep(1)
        self._spin_scan_interval.setKeyboardTracking(False)
        val = max(10, min(600, int(self._container.settings_repo.get("wifi_scan_interval", 30))))
        self._spin_scan_interval.setValue(val)
        self._spin_scan_interval.setFixedSize(80, 32)
        self._spin_scan_interval.setToolTip("10 – 600 сек")
        self._spin_scan_interval.valueChanged.connect(self._on_scan_interval)
        scan_lay.addWidget(self._spin_scan_interval, 0, Qt.AlignmentFlag.AlignTop)

        self._lbl_scan_hint = QLabel("10 – 600 сек")
        self._lbl_scan_hint.setObjectName("SettingsHint")
        scan_lay.addWidget(self._lbl_scan_hint, 0, Qt.AlignmentFlag.AlignTop)

        self._card_wifi, self._lbl_sec_wifi = self._card(
            "WI-FI", [self._chk_auto_scan, scan_row]
        )
        lay.addWidget(self._card_wifi)

        # Система
        self._chk_autostart = QCheckBox("Запуск с Windows")
        self._chk_autostart.setChecked(self._get_autostart())
        self._chk_autostart.stateChanged.connect(self._on_autostart)

        self._chk_tray = QCheckBox("Сворачивать в трей вместо закрытия")
        self._chk_tray.setChecked(
            bool(self._container.settings_repo.get("minimize_to_tray", False))
        )
        self._chk_tray.stateChanged.connect(self._on_minimize_to_tray)

        self._chk_start_min = QCheckBox("Запускать свёрнутым в трей")
        self._chk_start_min.setChecked(
            bool(self._container.settings_repo.get("start_minimized", False))
        )
        self._chk_start_min.stateChanged.connect(self._on_start_minimized)

        self._card_system, self._lbl_sec_system = self._card(
            "СИСТЕМА", [self._chk_autostart, self._chk_tray, self._chk_start_min]
        )
        lay.addWidget(self._card_system)

        # О программе
        about_row = QWidget()
        about_row.setObjectName("SettingsRow")
        about_lay = QHBoxLayout(about_row)
        about_lay.setContentsMargins(0, 0, 0, 0)
        about_lay.setSpacing(8)
        self._lbl_version = QLabel("NetConneXion  v2.0.0")
        self._lbl_version.setObjectName("FieldLabel")
        about_lay.addWidget(self._lbl_version)
        about_lay.addStretch(1)
        self._btn_repo = QPushButton("GitHub")
        self._btn_repo.setProperty("role", "action")
        self._btn_repo.setFixedSize(90, 32)
        self._btn_repo.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://github.com/mishamv/NetConneXion"))
        )
        about_lay.addWidget(self._btn_repo, 0, Qt.AlignmentFlag.AlignTop)
        self._card_about, self._lbl_sec_about = self._card("О ПРОГРАММЕ", [about_row])
        lay.addWidget(self._card_about)

        lay.addStretch(1)

    def _card(self, title: str, widgets: list) -> tuple:
        """Returns (card_frame, title_label)."""
        card = QFrame()
        card.setObjectName("SectionCard")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(10)

        hdr = QLabel(title)
        hdr.setObjectName("SectionTitle")
        lay.addWidget(hdr)

        sep = QFrame()
        sep.setObjectName("SectionLine")
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        lay.addWidget(sep)

        for w in widgets:
            lay.addWidget(w)

        return card, hdr

    def _theme_row(self) -> QWidget:
        row = QWidget()
        row.setObjectName("SettingsRow")
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        self._lbl_theme = QLabel("Тема")
        self._lbl_theme.setObjectName("FieldLabel")
        lay.addWidget(self._lbl_theme)
        lay.addStretch(1)

        self._btn_light = QPushButton("Светлая")
        self._btn_dark  = QPushButton("Тёмная")
        for btn in (self._btn_light, self._btn_dark):
            btn.setProperty("role", "action")
            btn.setFixedSize(100, 32)

        self._btn_light.clicked.connect(lambda: self._on_theme("light"))
        self._btn_dark.clicked.connect(lambda: self._on_theme("dark"))

        lay.addWidget(self._btn_light, 0, Qt.AlignmentFlag.AlignTop)
        lay.addWidget(self._btn_dark, 0, Qt.AlignmentFlag.AlignTop)
        return row

    def _lang_row(self) -> QWidget:
        row = QWidget()
        row.setObjectName("SettingsRow")
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        self._lbl_lang = QLabel("Язык / Language")
        self._lbl_lang.setObjectName("FieldLabel")
        lay.addWidget(self._lbl_lang)
        lay.addStretch(1)

        self._btn_ru = QPushButton("Русский")
        self._btn_en = QPushButton("English")
        for btn in (self._btn_ru, self._btn_en):
            btn.setProperty("role", "action")
            btn.setFixedSize(100, 32)

        self._btn_ru.clicked.connect(lambda: self._on_lang("ru"))
        self._btn_en.clicked.connect(lambda: self._on_lang("en"))

        lay.addWidget(self._btn_ru, 0, Qt.AlignmentFlag.AlignTop)
        lay.addWidget(self._btn_en, 0, Qt.AlignmentFlag.AlignTop)
        return row

    # ── Handlers ──────────────────────────────────────────────────

    def _on_theme(self, mode: str) -> None:
        self._presenter.save_theme(mode)
        self._update_theme_btns(mode)

    def _update_theme_btns(self, mode: str) -> None:
        self._btn_light.setProperty("role", "primary" if mode == "light" else "action")
        self._btn_dark.setProperty("role",  "primary" if mode == "dark"  else "action")
        for btn in (self._btn_light, self._btn_dark):
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _on_lang(self, locale: str) -> None:
        self._container.i18n.set_locale(locale)
        self._container.settings_repo.set("ui_locale", locale)
        self._container.settings_repo.save()
        self._update_lang_btns(locale)
        from quickip.core.events.types import LangChanged
        self._container.event_bus.publish(LangChanged(locale=locale))

    def _update_lang_btns(self, locale: str) -> None:
        self._btn_ru.setProperty("role", "primary" if locale == "ru" else "action")
        self._btn_en.setProperty("role", "primary" if locale == "en" else "action")
        for btn in (self._btn_ru, self._btn_en):
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _on_auto_scan(self, state: int) -> None:
        self._container.settings_repo.set("wifi_auto_scan", bool(state))
        self._container.settings_repo.save()

    def _on_scan_interval(self, value: int) -> None:
        self._container.settings_repo.set("wifi_scan_interval", value)
        self._container.settings_repo.save()

    def _on_autostart(self, state: int) -> None:
        self._set_autostart(bool(state))

    def _on_minimize_to_tray(self, state: int) -> None:
        self._container.settings_repo.set("minimize_to_tray", bool(state))
        self._container.settings_repo.save()

    def _on_start_minimized(self, state: int) -> None:
        self._container.settings_repo.set("start_minimized", bool(state))
        self._container.settings_repo.save()

    # ── Windows registry helpers ──────────────────────────────────

    @staticmethod
    def _get_autostart() -> bool:
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, _REG_RUN_PATH, 0, winreg.KEY_READ
            )
            winreg.QueryValueEx(key, _APP_REG_KEY)
            winreg.CloseKey(key)
            return True
        except Exception:
            return False

    @staticmethod
    def _set_autostart(enable: bool) -> None:
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, _REG_RUN_PATH, 0, winreg.KEY_SET_VALUE
            )
            if enable:
                val = f'"{sys.executable}" -m quickip'
                winreg.SetValueEx(key, _APP_REG_KEY, 0, winreg.REG_SZ, val)
            else:
                try:
                    winreg.DeleteValue(key, _APP_REG_KEY)
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except Exception:
            pass

    # ── SettingsViewProtocol ──────────────────────────────────────

    def set_language_value(self, lang: str) -> None:
        self._update_lang_btns(lang)

    def set_theme_value(self, theme: str) -> None:
        self._update_theme_btns(theme)

    def ask_yes_no(self, title: str, message: str) -> bool:
        reply = QMessageBox.question(
            self, title, message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    def show_message(self, title: str, message: str) -> None:
        QMessageBox.information(self, title, message)

    def refresh_theme(self, dark_mode: bool) -> None:
        self._update_theme_btns("dark" if dark_mode else "light")

    # ── i18n ──────────────────────────────────────────────────────

    def _tr(self, key: str) -> str:
        return self._container.i18n.get(key)

    def retranslate(self) -> None:
        """Обновляет все видимые строки при смене языка."""
        self._lbl_sec_appearance.setText(self._tr("section_appearance").upper())
        self._lbl_sec_language.setText(self._tr("section_language").upper())
        self._lbl_sec_wifi.setText(self._tr("section_wifi").upper())
        self._lbl_sec_system.setText(self._tr("section_system").upper())

        self._lbl_theme.setText(self._tr("label_theme"))
        self._btn_light.setText(self._tr("btn_light"))
        self._btn_dark.setText(self._tr("btn_dark"))

        self._chk_auto_scan.setText(self._tr("chk_wifi_auto_scan"))
        self._lbl_scan_interval.setText(self._tr("lbl_scan_interval"))
        self._chk_autostart.setText(self._tr("chk_autostart"))
        self._chk_tray.setText(self._tr("chk_minimize_to_tray"))
        self._chk_start_min.setText(self._tr("chk_start_minimized"))
        self._lbl_sec_about.setText(self._tr("section_about").upper())
        self._lbl_version.setText(f"NetConneXion  v2.0.0")

        # Восстанавливаем активное состояние кнопок языка
        locale = self._container.i18n.get_current_locale()
        self._update_lang_btns(locale)
