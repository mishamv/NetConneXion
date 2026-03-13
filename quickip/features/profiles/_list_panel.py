"""Left panel — profile list, search, adapter filter, CRUD buttons."""

from __future__ import annotations

import tkinter as tk
from typing import Callable, List, Optional, Set

import customtkinter as ctk


def _f(size: int, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(size=size, weight=weight)


_ICON_DEFAULT = "⊙"

class _ProfileRow(ctk.CTkFrame):
    """Single clickable row in the profile list."""

    def __init__(
        self,
        parent: tk.Widget,
        name: str,
        colors: dict,
        selected: bool,
        on_click: Callable[[str, bool], None],
    ) -> None:
        bg = colors.get("panel_row_selected", colors["sidebar_selected"]) if selected else colors.get("panel_row_bg", colors["card"])
        super().__init__(parent, fg_color=bg, corner_radius=10, cursor="hand2", border_width=1,
                         border_color=colors.get("card_border", colors["border"]))
        self.grid_columnconfigure(1, weight=1)
        self._colors = colors
        self._name = name
        self._on_click = on_click
        self._selected = selected

        self._icon_lbl = ctk.CTkLabel(
            self, text=_ICON_DEFAULT, width=28,
            font=_f(16), text_color=colors["accent"],
        )
        self._icon_lbl.grid(row=0, column=0, padx=(8, 2), pady=6)

        self._name_lbl = ctk.CTkLabel(
            self, text=name, anchor="w",
            font=_f(13, "bold" if selected else "normal"),
            text_color=colors["text"],
        )
        self._name_lbl.grid(row=0, column=1, sticky="ew", padx=(2, 8), pady=6)

        for w in (self, self._icon_lbl, self._name_lbl):
            w.bind("<Button-1>", self._click)

    def _click(self, event=None) -> None:
        ctrl = bool(event and (event.state & 0x4))
        self._on_click(self._name, ctrl)

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self.configure(
            fg_color=self._colors.get("panel_row_selected", self._colors["sidebar_selected"]) if selected
            else self._colors.get("panel_row_bg", self._colors["card"])
        )
        self._name_lbl.configure(font=_f(13, "bold" if selected else "normal"))

    def update_colors(self, colors: dict) -> None:
        self._colors = colors
        try:
            self.configure(
                fg_color=colors.get("panel_row_selected", colors["sidebar_selected"]) if self._selected
                else colors.get("panel_row_bg", colors["card"])
            )
        except Exception:
            pass
        try:
            self._icon_lbl.configure(text_color=colors["accent"])
        except Exception:
            pass
        try:
            self.configure(border_color=colors.get("card_border", colors["border"]))
        except Exception:
            pass
        try:
            self._name_lbl.configure(text_color=colors["text"])
        except Exception:
            pass


class ListPanel(ctk.CTkFrame):
    """Left panel containing the profile list and CRUD/import/export buttons."""

    def __init__(
        self,
        parent: tk.Widget,
        colors: dict,
        on_select: Callable[[str], None],
        on_create: Callable[[], None],
        on_delete: Callable[[], None],
        on_duplicate: Callable[[], None],
        on_export: Callable[[], None],
        on_import: Callable[[], None],
        on_search: Callable[[], None],
    ) -> None:
        super().__init__(
            parent,
            fg_color=colors.get("panel_bg", colors["card"]),
            width=280,
            corner_radius=int(colors.get("card_radius", 16)),
            border_width=1,
            border_color=colors.get("card_border", colors["border"]),
        )
        self.grid_propagate(False)
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._colors = colors
        self._on_select = on_select
        self._on_search = on_search

        self._selected_name: Optional[str] = None
        self._selected_names: Set[str] = set()
        self._rows: dict[str, _ProfileRow] = {}

        # Search & filter vars
        self._search_var = tk.StringVar(value="")
        self._filter_var = tk.StringVar(value="Все адаптеры")

        self._build(on_create, on_delete, on_duplicate, on_export, on_import)

    def _build(self, on_create, on_delete, on_duplicate, on_export, on_import) -> None:
        c = self._colors

        # Search bar: icon + entry in a single styled frame
        self._search_bar = ctk.CTkFrame(
            self, fg_color=c["input_bg"], corner_radius=int(c.get("input_radius", 10)),
            border_width=1, border_color=c["border"],
        )
        self._search_bar.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        self._search_bar.grid_columnconfigure(1, weight=1)

        self._search_icon = ctk.CTkLabel(
            self._search_bar, text="🔍", width=24,
            font=_f(14), text_color=c.get("text_secondary", c["text"]),
            fg_color="transparent",
        )
        self._search_icon.grid(row=0, column=0, padx=(8, 2), pady=0)

        self._search = ctk.CTkEntry(
            self._search_bar, textvariable=self._search_var,
            placeholder_text="Поиск...",
            height=32, corner_radius=0, font=_f(13),
            border_width=0, fg_color="transparent", text_color=c["text"],
            placeholder_text_color=c.get("input_placeholder", c.get("text_secondary", c["text"])),
        )
        self._search.grid(row=0, column=1, sticky="ew", padx=(0, 6), pady=1)
        self._search.bind("<KeyRelease>", lambda _: self._on_search())

        # Adapter filter combo
        self._filter_combo = ctk.CTkComboBox(
            self, state="readonly", values=["Все адаптеры"],
            variable=self._filter_var,
            height=34, font=_f(13), corner_radius=int(c.get("input_radius", 10)),
            border_color=c["border"], fg_color=c["input_bg"],
            button_color=c["combo_button"], button_hover_color=c["combo_button_hover"],
            dropdown_fg_color=c["card"], dropdown_text_color=c["text"],
            text_color=c["text"], text_color_disabled=c["text"],
            command=lambda _: self._on_search(),
        )
        self._filter_combo.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 6))

        # Card frame around the scrollable list
        self._list_card = ctk.CTkFrame(
            self, fg_color=c["bg"], corner_radius=12,
            border_width=1, border_color=c.get("card_border", c["border"]),
        )
        self._list_card.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 6))
        self._list_card.grid_columnconfigure(0, weight=1)
        self._list_card.grid_rowconfigure(0, weight=1)

        # Scrollable list area
        self._scroll = ctk.CTkScrollableFrame(self._list_card, fg_color="transparent", corner_radius=0)
        self._scroll.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        self._scroll.grid_columnconfigure(0, weight=1)

        # Separator
        ctk.CTkFrame(self, height=1, fg_color=c["border"]).grid(
            row=3, column=0, sticky="ew")

        # Bottom CRUD buttons
        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.grid(row=4, column=0, sticky="ew", padx=10, pady=10)
        btns.grid_columnconfigure(0, weight=1)
        self._btn_create = ctk.CTkButton(
            btns, text="✚  Новый", height=40, font=_f(13, "bold"), command=on_create,
        )
        self._btn_create.grid(row=0, column=0, sticky="ew", pady=2)

        self._btn_duplicate = ctk.CTkButton(
            btns, text="⊕  Копировать", height=36, font=_f(13), command=on_duplicate,
        )
        self._btn_duplicate.grid(row=1, column=0, sticky="ew", pady=2)

        self._btn_export = ctk.CTkButton(
            btns, text="↑  Экспорт", height=36, font=_f(13), command=on_export,
        )
        self._btn_export.grid(row=2, column=0, sticky="ew", pady=2)

        self._btn_import = ctk.CTkButton(
            btns, text="↓  Импорт", height=36, font=_f(13), command=on_import,
        )
        self._btn_import.grid(row=3, column=0, sticky="ew", pady=2)

        self._btn_delete = ctk.CTkButton(
            btns, text="✖  Удалить", height=36, font=_f(13), command=on_delete,
        )
        self._btn_delete.grid(row=4, column=0, sticky="ew", pady=2)

        self._style_action_buttons()

    def _style_action_buttons(self) -> None:
        c = self._colors
        self._btn_create.configure(
            fg_color=c.get("btn_primary_bg", c["accent"]),
            hover_color=c.get("btn_primary_hover", c["hover"]),
            text_color=c.get("btn_primary_text", "#FFFFFF"),
            corner_radius=10,
        )
        self._btn_duplicate.configure(
            fg_color=c.get("btn_outline_bg", c["input_bg"]),
            hover_color=c["bg"],
            text_color=c.get("btn_outline_text", c["text"]),
            border_width=1,
            border_color=c.get("btn_outline_border", c["border"]),
            corner_radius=10,
        )
        self._btn_export.configure(
            fg_color=c.get("btn_soft_bg", c["bg"]),
            hover_color="#E2ECFF",
            text_color=c.get("btn_soft_text_blue", c["accent"]),
            corner_radius=10,
            border_width=0,
        )
        self._btn_import.configure(
            fg_color=c.get("btn_soft_bg_purple", c.get("btn_soft_bg", c["bg"])),
            hover_color="#ECE3FF",
            text_color=c.get("btn_soft_text_purple", c.get("btn_soft_text_blue", c["accent"])),
            corner_radius=10,
            border_width=0,
        )
        self._btn_delete.configure(
            fg_color=c.get("btn_danger_bg", "#FFF1F1"),
            hover_color="#FFE6E6",
            text_color=c.get("btn_danger_text", "#E05252"),
            border_width=1,
            border_color=c.get("btn_danger_border", "#FFD0D0"),
            corner_radius=10,
        )

    # ── Public interface ──────────────────────────────────────────

    @property
    def selected_name(self) -> Optional[str]:
        return self._selected_name

    @property
    def selected_names(self) -> List[str]:
        return list(self._selected_names)

    @property
    def search_query(self) -> str:
        return self._search_var.get()

    @property
    def adapter_filter(self) -> str:
        return self._filter_var.get()

    def show_profiles_list(self, names: List[str], selected: Optional[str]) -> None:
        self._selected_name = selected
        self._selected_names = {selected} if selected else set()
        for w in self._scroll.winfo_children():
            w.destroy()
        self._rows.clear()
        for i, name in enumerate(names):
            row = _ProfileRow(self._scroll, name, self._colors, name == selected,
                              on_click=self._row_click)
            row.grid(row=i, column=0, sticky="ew", pady=2, padx=4)
            self._rows[name] = row

    def update_filter_values(self, values: List[str]) -> None:
        current = self._filter_var.get()
        self._filter_combo.configure(values=values)
        if current not in values:
            current = "Все адаптеры"
            self._filter_var.set(current)
        self._filter_combo.set(current)

    def update_colors(self, colors: dict) -> None:
        self._colors = colors
        c = colors
        try:
            self.configure(
                fg_color=c.get("panel_bg", c["card"]),
                border_color=c.get("card_border", c["border"]),
                corner_radius=int(c.get("card_radius", 16)),
            )
            self._scroll.configure(fg_color="transparent")
            self._list_card.configure(
                fg_color=c["bg"],
                border_color=c.get("card_border", c["border"]),
            )
        except Exception:
            pass
        try:
            self._search_bar.configure(fg_color=c["input_bg"], border_color=c["border"])
            self._search_icon.configure(text_color=c.get("text_secondary", c["text"]))
            self._search.configure(
                text_color=c["text"],
                placeholder_text_color=c.get("input_placeholder", c.get("text_secondary", c["text"])),
            )
        except Exception:
            pass
        try:
            self._filter_combo.configure(
                fg_color=c["input_bg"], border_color=c["border"],
                button_color=c["combo_button"], button_hover_color=c["combo_button_hover"],
                dropdown_fg_color=c["card"], dropdown_text_color=c["text"],
                text_color=c["text"], text_color_disabled=c["text"])
        except Exception:
            pass
        for row in self._rows.values():
            row.update_colors(c)
        self._style_action_buttons()

    # ── Internals ─────────────────────────────────────────────────

    def _row_click(self, name: str, ctrl: bool = False) -> None:
        if ctrl:
            if name in self._selected_names:
                self._selected_names.discard(name)
            else:
                self._selected_names.add(name)
                self._selected_name = name
        else:
            self._selected_names = {name}
            self._selected_name = name
            self._on_select(name)
        for n, row in self._rows.items():
            row.set_selected(n in self._selected_names)
