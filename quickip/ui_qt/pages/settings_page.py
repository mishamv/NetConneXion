"""Settings page — theme, language, autostart."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget,
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

        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(16)

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

        # Сеть
        self._chk_auto = QCheckBox("Авто-переключение профиля по Wi-Fi SSID")
        self._chk_auto.setChecked(
            bool(self._container.settings_repo.get("auto_switch_enabled", False))
        )
        self._chk_auto.stateChanged.connect(self._on_auto_switch)
        self._card_network, self._lbl_sec_network = self._card("СЕТЬ", [self._chk_auto])
        lay.addWidget(self._card_network)

        # Система
        self._chk_autostart = QCheckBox("Запуск с Windows")
        self._chk_autostart.setChecked(self._get_autostart())
        self._chk_autostart.stateChanged.connect(self._on_autostart)
        self._card_system, self._lbl_sec_system = self._card("СИСТЕМА", [self._chk_autostart])
        lay.addWidget(self._card_system)

        lay.addStretch(1)
        scroll.setWidget(body)
        root.addWidget(scroll)

    def _card(self, title: str, widgets: list) -> tuple:
        """Returns (card_frame, title_label)."""
        card = QFrame()
        card.setObjectName("SectionCard")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 12, 16, 14)
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
            btn.setMinimumWidth(100)
            btn.setMaximumWidth(160)
            btn.setFixedHeight(34)

        self._btn_light.clicked.connect(lambda: self._on_theme("light"))
        self._btn_dark.clicked.connect(lambda: self._on_theme("dark"))

        lay.addWidget(self._btn_light)
        lay.addWidget(self._btn_dark)
        return row

    def _lang_row(self) -> QWidget:
        row = QWidget()
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
            btn.setMinimumWidth(100)
            btn.setMaximumWidth(160)
            btn.setFixedHeight(34)

        self._btn_ru.clicked.connect(lambda: self._on_lang("ru"))
        self._btn_en.clicked.connect(lambda: self._on_lang("en"))

        lay.addWidget(self._btn_ru)
        lay.addWidget(self._btn_en)
        return row

    # ── Handlers ──────────────────────────────────────────────────

    def _on_theme(self, mode: str) -> None:
        self._presenter.save_theme(mode)
        self._update_theme_btns(mode)

    def _update_theme_btns(self, mode: str) -> None:
        self._btn_light.setProperty("role", "primary" if mode == "light" else "")
        self._btn_dark.setProperty("role",  "primary" if mode == "dark"  else "")
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
        self._btn_ru.setProperty("role", "primary" if locale == "ru" else "")
        self._btn_en.setProperty("role", "primary" if locale == "en" else "")
        for btn in (self._btn_ru, self._btn_en):
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _on_auto_switch(self, state: int) -> None:
        self._container.settings_repo.set("auto_switch_enabled", bool(state))
        self._container.settings_repo.save()

    def _on_autostart(self, state: int) -> None:
        self._set_autostart(bool(state))

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
        self._lbl_sec_network.setText(self._tr("section_network_cfg").upper())
        self._lbl_sec_system.setText(self._tr("section_system").upper())

        self._lbl_theme.setText(self._tr("label_theme"))
        self._btn_light.setText(self._tr("btn_light"))
        self._btn_dark.setText(self._tr("btn_dark"))

        self._chk_auto.setText(self._tr("chk_auto_switch"))
        self._chk_autostart.setText(self._tr("chk_autostart"))

        # Восстанавливаем активное состояние кнопок языка
        locale = self._container.i18n.get_current_locale()
        self._update_lang_btns(locale)
