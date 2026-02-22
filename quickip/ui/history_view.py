"""History view – CTk widgets implementing HistoryView protocol."""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING, List

try:
    import customtkinter as ctk
except ImportError:
    ctk = None  # type: ignore

from quickip.ui.dialogs import show_message

if TYPE_CHECKING:
    from quickip.presenters.history_presenter import HistoryPresenter


class HistoryView:
    """
    Builds the history panel widgets and implements the
    :class:`HistoryPresenter.HistoryView` protocol.
    """

    def __init__(self, parent: tk.Widget, colors: dict, root: tk.Widget) -> None:
        self.parent = parent
        self.colors = colors
        self.root = root
        self.presenter: HistoryPresenter | None = None

        self.history_search_var = tk.StringVar(value="")
        self.history_status_filter_var = tk.StringVar(value="Все")

        self._build(parent)

    def bind_presenter(self, presenter: "HistoryPresenter") -> None:
        self.presenter = presenter

    # ── Build ────────────────────────────────────────────────────

    def _build(self, parent: tk.Widget) -> None:
        top = ctk.CTkFrame(parent, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(16, 8))
        ctk.CTkLabel(top, text="История применений", text_color=self.colors["text"],
                      font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkButton(top, text="Обновить", command=self._on_refresh, height=34).pack(side="right")
        ctk.CTkButton(top, text="Откатить последний", command=self._on_rollback, height=34).pack(side="right", padx=(0, 8))

        controls = ctk.CTkFrame(parent, fg_color="transparent")
        controls.pack(fill="x", padx=16, pady=(0, 8))
        self.search_entry = ctk.CTkEntry(
            controls, textvariable=self.history_search_var,
            placeholder_text="Поиск по имени профиля...", height=32, corner_radius=6,
            border_color=self.colors["border"], fg_color=self.colors["input_bg"],
            text_color=self.colors["text"],
        )
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.search_entry.bind("<KeyRelease>", lambda _: self._on_refresh())

        self.status_combo = ctk.CTkComboBox(
            controls, state="readonly", values=["Все", "Успешные", "Ошибки"],
            variable=self.history_status_filter_var, width=170, height=32,
            corner_radius=6, border_color=self.colors["border"],
            fg_color=self.colors["input_bg"],
            button_color=self.colors["combo_button"],
            button_hover_color=self.colors["combo_button_hover"],
            dropdown_fg_color=self.colors["card"],
            dropdown_hover_color="#EFF6FF",
            dropdown_text_color=self.colors["text"],
            text_color=self.colors["text"],
            text_color_disabled=self.colors["text"],
            command=lambda _: self._on_refresh(),
        )
        self.status_combo.pack(side="left")

        self.stats_label = ctk.CTkLabel(parent, text="Статистика: -", text_color=self.colors["text_secondary"])
        self.stats_label.pack(anchor="w", padx=16, pady=(0, 6))

        self.history_text = ctk.CTkTextbox(parent, font=ctk.CTkFont(family="Consolas", size=12))
        self.history_text.pack(fill="both", expand=True, padx=16, pady=(0, 16))

    # ── Protocol implementation ──────────────────────────────────

    def show_history_entries(self, lines: List[str]) -> None:
        self.history_text.delete("1.0", "end")
        self.history_text.insert("end", "\n".join(lines))

    def show_history_stats(self, text: str) -> None:
        self.stats_label.configure(text=text)

    def show_message(self, title: str, message: str) -> None:
        show_message(self.root, title, message, self.colors)

    def get_history_search(self) -> str:
        return self.history_search_var.get()

    def get_history_status_filter(self) -> str:
        return self.history_status_filter_var.get()

    def refresh_related_panels(self) -> None:
        pass  # wired by main_window

    # ── Event handlers ───────────────────────────────────────────

    def _on_refresh(self) -> None:
        if self.presenter:
            self.presenter.refresh()

    def _on_rollback(self) -> None:
        if self.presenter:
            self.presenter.rollback()

    def update_colors(self, colors: dict) -> None:
        self.colors = colors
