"""Settings feature presenter — language and theme management."""

from __future__ import annotations

import logging
import os
import sys
from typing import TYPE_CHECKING, Optional, Protocol

import customtkinter as ctk

from quickip.core.events.types import ThemeChanged
from quickip.features.settings.repository import SettingsRepository

if TYPE_CHECKING:
    from quickip.app.bootstrap import ServiceContainer

logger = logging.getLogger(__name__)

_LANG_LABELS = {"ru": "Русский", "en": "English"}


# ── View protocol ─────────────────────────────────────────────────

class SettingsViewProtocol(Protocol):
    def set_language_value(self, lang: str) -> None: ...
    def set_theme_value(self, theme: str) -> None: ...
    def ask_yes_no(self, title: str, message: str) -> bool: ...
    def show_message(self, title: str, message: str) -> None: ...


# ── Presenter ─────────────────────────────────────────────────────

class SettingsPresenter:
    """Handles language and theme settings.

    Language change requires restart — prompts user and restarts via os.execv.
    Theme change is applied immediately via ctk and published via EventBus.
    """

    def __init__(self, container: "ServiceContainer") -> None:
        self._container = container
        self._repo = SettingsRepository(container)
        self._view: Optional[SettingsViewProtocol] = None

    def bind_view(self, view: SettingsViewProtocol) -> None:
        self._view = view

    # ── Load ──────────────────────────────────────────────────────

    def load_settings(self) -> None:
        """Push current settings to the view."""
        if self._view is None:
            return
        self._view.set_language_value(self._repo.get_language())
        self._view.set_theme_value(self._repo.get_theme())

    # ── Save language ─────────────────────────────────────────────

    def save_language(self, lang: str) -> None:
        """Save language; prompt for restart. On Yes: restart the process."""
        if self._view is None:
            return
        self._repo.set_language(lang)
        self._container.i18n.set_locale(lang)
        restart = self._view.ask_yes_no(
            "Перезапуск",
            "Для применения языка требуется перезапуск.\nПерезапустить сейчас?",
        )
        if restart:
            logger.info("Restarting application for language change to '%s'", lang)
            os.execv(sys.executable, [sys.executable] + sys.argv)

    # ── Save theme ────────────────────────────────────────────────

    def save_theme(self, theme: str) -> None:
        """Save theme; apply immediately via ctk; publish ThemeChanged event."""
        if self._view is None:
            return
        mode = "dark" if theme == "dark" else "light"
        self._repo.set_theme(mode)
        ctk.set_appearance_mode(mode)
        self._container.event_bus.publish(ThemeChanged(theme=mode))
        logger.info("Theme changed to '%s'", mode)
