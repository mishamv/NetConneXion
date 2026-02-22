"""Settings feature view — language, theme, app info."""

from __future__ import annotations

import logging
import sys
import tkinter as tk
from typing import TYPE_CHECKING

import customtkinter as ctk

from quickip.core.ui.theme import get_palette
from quickip.core.ui.dialogs import show_message, ask_yes_no
from quickip.core.events.types import ThemeChanged

if TYPE_CHECKING:
    from quickip.features.settings.presenter import SettingsPresenter

logger = logging.getLogger(__name__)

_LANG_LABELS = {"ru": "Русский", "en": "English"}
_LANG_CODES  = {v: k for k, v in _LANG_LABELS.items()}


def _f(size: int, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(size=size, weight=weight)


def _card(parent, colors: dict) -> ctk.CTkFrame:
    return ctk.CTkFrame(
        parent,
        fg_color=colors.get("card_inner", colors["input_bg"]),
        border_width=1, border_color=colors["border"], corner_radius=10,
    )


class SettingsView(ctk.CTkFrame):
    """Settings page: appearance card, language card, app-info card.

    Constructor: SettingsView(parent, presenter) per DI convention.
    Calls presenter.bind_view(self) then presenter.load_settings() on init.
    """

    def __init__(self, parent, presenter: "SettingsPresenter") -> None:
        super().__init__(parent, fg_color="transparent")
        self._presenter = presenter

        mode = ctk.get_appearance_mode().lower()
        self.colors = get_palette(mode)

        self._theme_var = tk.BooleanVar(value=(mode == "dark"))
        self._lang_var  = tk.StringVar(value="Русский")

        self._build()

        # Subscribe to ThemeChanged to update own colors
        try:
            container = presenter._container
            container.event_bus.subscribe(ThemeChanged, self._on_theme_changed)
        except Exception:
            pass

        presenter.bind_view(self)
        presenter.load_settings()
        logger.debug("SettingsView initialised")

    # ── Layout ────────────────────────────────────────────────────

    def _build(self) -> None:
        c = self.colors

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True)
        scroll.grid_columnconfigure(0, weight=1)
        self._scroll = scroll

        # Page title
        self._title = ctk.CTkLabel(
            scroll, text="Настройки",
            font=_f(20, "bold"), text_color=c["text"], anchor="w",
        )
        self._title.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 4))

        # ── Appearance card ───────────────────────────────────────
        self._app_card = _card(scroll, c)
        self._app_card.grid(row=1, column=0, sticky="ew", padx=20, pady=(10, 0))
        self._app_card.grid_columnconfigure(1, weight=1)

        self._app_title = ctk.CTkLabel(
            self._app_card, text="Внешний вид", font=_f(14, "bold"), text_color=c["text"],
        )
        self._app_title.grid(row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(12, 6))

        self._theme_lbl = ctk.CTkLabel(
            self._app_card, text="Тема оформления", font=_f(13), text_color=c["text"],
        )
        self._theme_lbl.grid(row=1, column=0, sticky="w", padx=14, pady=8)

        self._theme_switch = ctk.CTkSwitch(
            self._app_card, text="Тёмная",
            variable=self._theme_var,
            command=self._on_theme_switch,
            font=_f(13), text_color=c["text"],
        )
        self._theme_switch.grid(row=1, column=1, sticky="e", padx=14, pady=8)

        # ── Language card ─────────────────────────────────────────
        self._lang_card = _card(scroll, c)
        self._lang_card.grid(row=2, column=0, sticky="ew", padx=20, pady=(10, 0))
        self._lang_card.grid_columnconfigure(1, weight=1)

        self._lang_title = ctk.CTkLabel(
            self._lang_card, text="Язык / Language", font=_f(14, "bold"), text_color=c["text"],
        )
        self._lang_title.grid(row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(12, 6))

        self._lang_lbl = ctk.CTkLabel(
            self._lang_card, text="Язык интерфейса", font=_f(13), text_color=c["text"],
        )
        self._lang_lbl.grid(row=1, column=0, sticky="w", padx=14, pady=8)

        self._lang_menu = ctk.CTkOptionMenu(
            self._lang_card,
            values=list(_LANG_LABELS.values()),
            variable=self._lang_var,
            command=self._on_lang_change,
            width=160, height=36, font=_f(13),
            fg_color=c["input_bg"],
            button_color=c["combo_button"], button_hover_color=c["combo_button_hover"],
            dropdown_fg_color=c["card"], dropdown_text_color=c["text"],
            text_color=c["text"],
        )
        self._lang_menu.grid(row=1, column=1, sticky="e", padx=14, pady=8)

        self._lang_hint = ctk.CTkLabel(
            self._lang_card,
            text="Для применения языка требуется перезапуск",
            font=_f(11), text_color=c.get("text_secondary", c["text"]),
        )
        self._lang_hint.grid(row=2, column=0, columnspan=2, sticky="w", padx=14, pady=(0, 10))

        # ── App-info card ─────────────────────────────────────────
        self._info_card = _card(scroll, c)
        self._info_card.grid(row=3, column=0, sticky="ew", padx=20, pady=(10, 20))
        self._info_card.grid_columnconfigure(1, weight=1)

        self._info_title = ctk.CTkLabel(
            self._info_card, text="О приложении", font=_f(14, "bold"), text_color=c["text"],
        )
        self._info_title.grid(row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(12, 6))

        info_rows = [
            ("Приложение", "Quick IP Change"),
            ("Python",     sys.version.split()[0]),
        ]
        for i, (key, val) in enumerate(info_rows, start=1):
            ctk.CTkLabel(self._info_card, text=key, font=_f(13),
                         text_color=c["text"], anchor="w").grid(
                row=i, column=0, sticky="w", padx=14, pady=4)
            ctk.CTkLabel(self._info_card, text=val, font=_f(11),
                         text_color=c.get("text_secondary", c["text"]), anchor="w").grid(
                row=i, column=1, sticky="ew", padx=14, pady=4)
        ctk.CTkLabel(self._info_card, text="").grid(row=len(info_rows) + 1, column=0)

    # ── View protocol ─────────────────────────────────────────────

    def set_language_value(self, lang: str) -> None:
        label = _LANG_LABELS.get(lang, lang)
        self._lang_var.set(label)

    def set_theme_value(self, theme: str) -> None:
        self._theme_var.set(theme == "dark")

    def ask_yes_no(self, title: str, message: str) -> bool:
        return ask_yes_no(self.winfo_toplevel(), title, message, self.colors)

    def show_message(self, title: str, message: str) -> None:
        show_message(self.winfo_toplevel(), title, message, self.colors)

    # ── Event handlers ────────────────────────────────────────────

    def _on_theme_switch(self) -> None:
        mode = "dark" if self._theme_var.get() else "light"
        self._presenter.save_theme(mode)

    def _on_lang_change(self, label: str) -> None:
        code = _LANG_CODES.get(label, "ru")
        self._presenter.save_language(code)

    def _on_theme_changed(self, event: ThemeChanged) -> None:
        """Auto-update own colors when theme changes via EventBus."""
        self.colors = get_palette(event.theme)
        self._theme_var.set(event.theme == "dark")

    # ── Color propagation ─────────────────────────────────────────

    def update_colors(self, colors: dict) -> None:
        self.colors = colors
        c = colors
        card_bg = c.get("card_inner", c["input_bg"])

        def _cfg(w, **kw):
            try:
                w.configure(**kw)
            except Exception:
                pass

        _cfg(self._scroll,    fg_color=c["card"])
        for card in (self._app_card, self._lang_card, self._info_card):
            _cfg(card, fg_color=card_bg, border_color=c["border"])

        text     = c["text"]
        text_sec = c.get("text_secondary", text)
        for lbl in (self._title, self._app_title, self._lang_title,
                    self._info_title, self._theme_lbl, self._lang_lbl):
            _cfg(lbl, text_color=text)

        _cfg(self._lang_hint, text_color=text_sec)
        _cfg(self._theme_switch, text_color=text)
        _cfg(self._lang_menu,
             fg_color=c["input_bg"],
             button_color=c["combo_button"], button_hover_color=c["combo_button_hover"],
             dropdown_fg_color=c["card"], dropdown_text_color=c["text"],
             text_color=text)
