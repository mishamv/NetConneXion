"""History feature view — displays apply history with filters and stats."""

from __future__ import annotations

import logging
import tkinter as tk
from typing import TYPE_CHECKING, List

import customtkinter as ctk

from quickip.core.ui.theme import get_palette
from quickip.core.ui.dialogs import show_message

if TYPE_CHECKING:
    from quickip.features.history.presenter import HistoryPresenter

logger = logging.getLogger(__name__)


class HistoryView(ctk.CTkFrame):
    """History page: filter controls, stats label, scrollable log textbox.

    Constructor: HistoryView(parent, presenter) per DI convention.
    Calls presenter.bind_view(self) then presenter.refresh() on init.
    """

    def __init__(self, parent, presenter: "HistoryPresenter") -> None:
        super().__init__(parent, fg_color="transparent")
        self._presenter = presenter

        mode = ctk.get_appearance_mode().lower()
        self.colors = get_palette(mode)

        self._search_var = tk.StringVar(value="")
        self._status_var = tk.StringVar(value="Все")

        self._build()
        presenter.bind_view(self)
        presenter.refresh()
        logger.debug("HistoryView initialised")

    # ── Layout ────────────────────────────────────────────────────

    def _build(self) -> None:
        c = self.colors

        # Title bar
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(16, 8))

        self._title_lbl = ctk.CTkLabel(
            top, text="История применений",
            font=ctk.CTkFont(size=20, weight="bold"), text_color=c["text"],
        )
        self._title_lbl.pack(side="left")

        ctk.CTkButton(top, text="Обновить", height=34,
                      text_color="#FFFFFF",
                      command=self._on_refresh).pack(side="right")
        ctk.CTkButton(top, text="Откатить последний", height=34,
                      text_color="#FFFFFF",
                      command=self._on_rollback).pack(side="right", padx=(0, 8))

        # Search + status filter
        controls = ctk.CTkFrame(self, fg_color="transparent")
        controls.pack(fill="x", padx=16, pady=(0, 8))

        self._search = ctk.CTkEntry(
            controls, textvariable=self._search_var,
            placeholder_text="Поиск по имени профиля...",
            height=32, corner_radius=6,
            border_color=c["border"], fg_color=c["input_bg"], text_color=c["text"],
        )
        self._search.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._search.bind("<KeyRelease>", lambda _: self._on_refresh())

        self._status_combo = ctk.CTkComboBox(
            controls, state="readonly",
            values=["Все", "Успешные", "Ошибки"],
            variable=self._status_var,
            width=170, height=32, corner_radius=6,
            border_color=c["border"], fg_color=c["input_bg"],
            button_color=c["combo_button"], button_hover_color=c["combo_button_hover"],
            dropdown_fg_color=c["card"], dropdown_text_color=c["text"],
            text_color=c["text"], text_color_disabled=c["text"],
            command=lambda _: self._on_refresh(),
        )
        self._status_combo.pack(side="left")

        # Stats label
        self._stats_lbl = ctk.CTkLabel(
            self, text="Статистика: —",
            text_color=c.get("text_secondary", c["text"]),
        )
        self._stats_lbl.pack(anchor="w", padx=16, pady=(0, 6))

        # Log textbox
        self._log = ctk.CTkTextbox(
            self, font=ctk.CTkFont(family="Consolas", size=12),
        )
        self._log.pack(fill="both", expand=True, padx=16, pady=(0, 16))

    # ── View protocol ─────────────────────────────────────────────

    def show_history_entries(self, lines: List[str]) -> None:
        self._log.delete("1.0", "end")
        self._log.insert("end", "\n".join(lines))

    def show_history_stats(self, text: str) -> None:
        self._stats_lbl.configure(text=text)

    def show_message(self, title: str, message: str) -> None:
        show_message(self.winfo_toplevel(), title, message, self.colors)

    def get_history_search(self) -> str:
        return self._search_var.get()

    def get_history_status_filter(self) -> str:
        return self._status_var.get()

    # ── Color propagation ─────────────────────────────────────────

    def update_colors(self, colors: dict) -> None:
        self.colors = colors
        c = colors

        def _cfg(w, **kw):
            try:
                w.configure(**kw)
            except Exception:
                pass

        _cfg(self._title_lbl, text_color=c["text"])
        _cfg(self._search,
             fg_color=c["input_bg"], border_color=c["border"], text_color=c["text"])
        _cfg(self._status_combo,
             fg_color=c["input_bg"], border_color=c["border"],
             button_color=c["combo_button"], button_hover_color=c["combo_button_hover"],
             dropdown_fg_color=c["card"], dropdown_text_color=c["text"],
             text_color=c["text"], text_color_disabled=c["text"])
        _cfg(self._stats_lbl, text_color=c.get("text_secondary", c["text"]))

    # ── Button handlers ───────────────────────────────────────────

    def _on_refresh(self) -> None:
        self._presenter.refresh()

    def _on_rollback(self) -> None:
        self._presenter.rollback()
