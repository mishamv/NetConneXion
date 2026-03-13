"""Profiles feature view — top-level frame, wires panels and view protocol."""

from __future__ import annotations

import logging
from tkinter import filedialog
from typing import TYPE_CHECKING, List, Optional

import customtkinter as ctk

from quickip.core.ui.theme import get_palette
from quickip.core.ui.dialogs import show_message, ask_yes_no
from quickip.features.profiles._list_panel import ListPanel
from quickip.features.profiles._form_panel import FormPanel

if TYPE_CHECKING:
    from quickip.features.profiles.presenter import ProfilesPresenter

logger = logging.getLogger(__name__)


class ProfilesView(ctk.CTkFrame):
    """Full profiles page: profile list on the left, form on the right.

    Constructor: ProfilesView(parent, presenter) per DI convention.
    Calls presenter.bind_view(self) then presenter.load_initial() on init.
    """

    def __init__(self, parent, presenter: "ProfilesPresenter") -> None:
        super().__init__(parent, fg_color="transparent")
        self._presenter = presenter

        mode = ctk.get_appearance_mode().lower()
        self.colors = get_palette(mode)

        # Root card frame
        self._shadow_frame = ctk.CTkFrame(
            self,
            fg_color=self.colors.get("card_shadow", self.colors["bg"]),
            corner_radius=int(self.colors.get("card_radius", 16)),
        )
        self._shadow_frame.pack(fill="both", expand=True, padx=(1, 0), pady=(1, 0))

        self._root_frame = ctk.CTkFrame(
            self._shadow_frame,
            fg_color=self.colors["card"],
            corner_radius=int(self.colors.get("card_radius", 16)),
            border_width=1,
            border_color=self.colors.get("card_border", self.colors["border"]),
        )
        self._root_frame.pack(fill="both", expand=True)
        self._root_frame.grid_columnconfigure(1, weight=1)
        self._root_frame.grid_rowconfigure(0, weight=1)

        # Left panel — profile list
        self._list = ListPanel(
            self._root_frame,
            self.colors,
            on_select=self._on_row_select,
            on_create=self._on_create,
            on_delete=self._on_delete,
            on_duplicate=self._on_duplicate,
            on_export=self._on_export,
            on_import=self._on_import,
            on_search=self._on_search,
        )
        self._list.grid(row=0, column=0, sticky="nsew")

        # Right panel — form
        self._form = FormPanel(
            self._root_frame,
            self.colors,
            presenter=presenter,
        )
        self._form.grid(row=0, column=1, sticky="nsew", padx=12, pady=12)

        # Register as view and trigger initial load
        presenter.bind_view(self)
        presenter.load_initial()
        logger.debug("ProfilesView initialised")

    # ── View protocol ─────────────────────────────────────────────

    def show_profiles_list(self, names: List[str], selected: Optional[str]) -> None:
        self._list.show_profiles_list(names, selected)

    def load_profile_form(self, profile, focus: bool = False) -> None:
        self._form.load(profile, self._presenter.get_adapters(), focus=focus)

    def show_message(self, title: str, message: str) -> None:
        show_message(self.winfo_toplevel(), title, message, self.colors)

    def ask_yes_no(self, title: str, message: str) -> bool:
        return ask_yes_no(self.winfo_toplevel(), title, message, self.colors)

    def get_adapter_filter(self) -> str:
        return self._list.adapter_filter

    def get_search_query(self) -> str:
        return self._list.search_query

    def update_adapter_filter_values(self, values: List[str]) -> None:
        self._list.update_filter_values(values)

    # ── Color propagation ─────────────────────────────────────────

    def update_colors(self, colors: dict) -> None:
        self.colors = colors
        try:
            self._shadow_frame.configure(
                fg_color=colors.get("card_shadow", colors["bg"]),
                corner_radius=int(colors.get("card_radius", 16)),
            )
            self._root_frame.configure(
                fg_color=colors["card"],
                corner_radius=int(colors.get("card_radius", 16)),
                border_color=colors.get("card_border", colors["border"]),
            )
        except Exception:
            pass
        self._list.update_colors(colors)
        self._form.update_colors(colors)

    # ── Event callbacks from panels ───────────────────────────────

    def _on_row_select(self, name: str) -> None:
        if not self._form.check_unsaved():
            return
        self._presenter.on_select(name)

    def _on_search(self) -> None:
        self._presenter.refresh_list()

    def _on_create(self) -> None:
        if not self._form.check_unsaved():
            return
        self._presenter.create_profile()

    def _on_delete(self) -> None:
        names = self._list.selected_names
        if not names:
            return
        if len(names) == 1:
            msg = f"Удалить профиль «{names[0]}»?"
        else:
            msg = f"Удалить выбранные профили ({len(names)} шт.)?"
        if ask_yes_no(self.winfo_toplevel(), "Удаление", msg, self.colors):
            self._presenter.delete_profiles(names)

    def _on_duplicate(self) -> None:
        name = self._list.selected_name
        if name:
            self._presenter.duplicate_profile(name)

    def _on_export(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON", "*.json")])
        if path:
            self._presenter.export_profiles(path)

    def _on_import(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[("JSON", "*.json"), ("All files", "*.*")])
        if path:
            self._presenter.import_profiles(path)
