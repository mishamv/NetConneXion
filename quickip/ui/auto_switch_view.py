"""Auto-switch (Wi-Fi) view – CTk widgets implementing AutoSwitchView protocol."""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING, List, Optional

try:
    import customtkinter as ctk
except ImportError:
    ctk = None  # type: ignore

from quickip.ui.dialogs import show_message, ask_yes_no

if TYPE_CHECKING:
    from quickip.presenters.auto_switch_presenter import AutoSwitchPresenter


class AutoSwitchView:
    """
    Builds the Wi-Fi / auto-switch panel and implements the
    :class:`AutoSwitchPresenter.AutoSwitchView` protocol.
    """

    def __init__(self, parent: tk.Widget, colors: dict, root: tk.Widget) -> None:
        self.parent = parent
        self.colors = colors
        self.root = root
        self.presenter: AutoSwitchPresenter | None = None

        self.wifi_auto_apply_var = tk.BooleanVar(value=False)
        self.wifi_mapping_auto_var = tk.BooleanVar(value=True)

        self._build(parent)

    def bind_presenter(self, presenter: "AutoSwitchPresenter") -> None:
        self.presenter = presenter

    # ── Build ────────────────────────────────────────────────────

    def _build(self, parent: tk.Widget) -> None:
        ctk.CTkLabel(parent, text="Wi-Fi сети и привязки", text_color=self.colors["text"],
                      font=ctk.CTkFont(size=20, weight="bold")).pack(anchor="w", padx=16, pady=(16, 8))

        top = ctk.CTkFrame(parent, fg_color="transparent")
        top.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        top.grid_columnconfigure(0, weight=1)
        top.grid_columnconfigure(1, weight=1)
        top.grid_rowconfigure(1, weight=1)

        # ── Left: visible networks ───────────────────────────────
        left_card = ctk.CTkFrame(top, fg_color=self.colors["card"], corner_radius=8,
                                  border_width=1, border_color=self.colors["border"])
        left_card.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0, 8))
        ctk.CTkLabel(left_card, text="Видимые Wi‑Fi сети", text_color=self.colors["text"],
                      font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=10, pady=(10, 6))
        visible_holder = ctk.CTkFrame(left_card, fg_color="transparent")
        visible_holder.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.visible_list = tk.Listbox(
            visible_holder, bg=self.colors["list_bg"], fg=self.colors["text"],
            selectbackground=self.colors["accent"], selectforeground="#FFFFFF",
            font=("Segoe UI", 12), relief="flat", borderwidth=0,
            highlightthickness=0, exportselection=False,
        )
        self.visible_list.pack(side="left", fill="both", expand=True)
        scroll = ctk.CTkScrollbar(visible_holder, orientation="vertical", command=self.visible_list.yview)
        self.visible_list.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.visible_list.bind("<<ListboxSelect>>", self._on_select_visible)

        # ── Right top: input row ─────────────────────────────────
        right_row = ctk.CTkFrame(top, fg_color="transparent")
        right_row.grid(row=0, column=1, sticky="ew")
        right_row.grid_columnconfigure(0, weight=1)

        self.ssid_entry = ctk.CTkEntry(right_row, placeholder_text="SSID", height=34, corner_radius=6,
                                        border_color=self.colors["border"], fg_color=self.colors["input_bg"],
                                        text_color=self.colors["text"])
        self.ssid_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self.profile_combo = ctk.CTkComboBox(
            right_row, state="readonly", values=[""], width=220, height=34,
            corner_radius=6, border_color=self.colors["border"],
            fg_color=self.colors["input_bg"],
            button_color=self.colors["combo_button"],
            button_hover_color=self.colors["combo_button_hover"],
            dropdown_fg_color=self.colors["card"],
            dropdown_hover_color="#EFF6FF",
            dropdown_text_color=self.colors["text"],
            text_color=self.colors["text"],
            text_color_disabled=self.colors["text"],
        )
        self.profile_combo.grid(row=0, column=1, padx=(0, 8))

        self.alias_entry = ctk.CTkEntry(right_row, placeholder_text="Название подключения", width=180, height=34,
                                         corner_radius=6, border_color=self.colors["border"],
                                         fg_color=self.colors["input_bg"], text_color=self.colors["text"])
        self.alias_entry.grid(row=0, column=2, padx=(0, 8))
        self.user_entry = ctk.CTkEntry(right_row, placeholder_text="Пользователь", width=160, height=34,
                                        corner_radius=6, border_color=self.colors["border"],
                                        fg_color=self.colors["input_bg"], text_color=self.colors["text"])
        self.user_entry.grid(row=0, column=3, padx=(0, 8))
        ctk.CTkCheckBox(right_row, text="Авто", variable=self.wifi_mapping_auto_var).grid(row=0, column=4, padx=(0, 8))
        ctk.CTkButton(right_row, text="Добавить", command=self._on_add, height=34).grid(row=0, column=5)

        # ── Right bottom: actions + mappings list ────────────────
        action_area = ctk.CTkFrame(top, fg_color="transparent")
        action_area.grid(row=1, column=1, sticky="nsew", pady=(8, 0))
        action_area.grid_rowconfigure(2, weight=1)
        action_area.grid_columnconfigure(0, weight=1)

        top_actions = ctk.CTkFrame(action_area, fg_color="transparent")
        top_actions.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.current_ssid_label = ctk.CTkLabel(top_actions, text="Текущий SSID: -", text_color=self.colors["text_secondary"])
        self.current_ssid_label.pack(side="left")
        self.auto_check = ctk.CTkCheckBox(top_actions, text="Автоприменение по SSID",
                                           variable=self.wifi_auto_apply_var, command=self._on_toggle_auto)
        self.auto_check.pack(side="left", padx=(12, 0))
        ctk.CTkButton(top_actions, text="Применить выбранную привязку",
                       command=self._on_apply_mapping, height=34).pack(side="right")
        ctk.CTkButton(top_actions, text="Обновить SSID",
                       command=self._on_refresh_ssid, height=34).pack(side="right", padx=(0, 8))
        ctk.CTkButton(top_actions, text="Обновить сети",
                       command=self._on_refresh_visible, height=34).pack(side="right", padx=(0, 8))

        self.auto_status_label = ctk.CTkLabel(action_area, text="Автоприменение: ожидание",
                                               text_color=self.colors["text_secondary"])
        self.auto_status_label.grid(row=1, column=0, sticky="w", pady=(0, 6))

        mappings_holder = ctk.CTkFrame(action_area, fg_color=self.colors["card"], corner_radius=8,
                                        border_width=1, border_color=self.colors["border"])
        mappings_holder.grid(row=2, column=0, sticky="nsew")
        self.mappings_list = tk.Listbox(
            mappings_holder, bg=self.colors["list_bg"], fg=self.colors["text"],
            selectbackground=self.colors["accent"], selectforeground="#FFFFFF",
            font=("Segoe UI", 12), relief="flat", borderwidth=0,
            highlightthickness=0, exportselection=False,
        )
        self.mappings_list.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        m_scroll = ctk.CTkScrollbar(mappings_holder, orientation="vertical", command=self.mappings_list.yview)
        self.mappings_list.configure(yscrollcommand=m_scroll.set)
        m_scroll.pack(side="right", fill="y", padx=8, pady=8)

        ctk.CTkButton(parent, text="Удалить выбранную", command=self._on_remove, height=34).pack(
            anchor="w", padx=16, pady=(0, 16))

    # ── Protocol implementation ──────────────────────────────────

    def show_current_ssid(self, text: str) -> None:
        self.current_ssid_label.configure(text=text)

    def show_auto_status(self, text: str) -> None:
        self.auto_status_label.configure(text=text)

    def show_visible_networks(self, names: List[str]) -> None:
        self.visible_list.delete(0, "end")
        for n in names:
            self.visible_list.insert("end", n)

    def show_mappings(self, lines: List[str]) -> None:
        self.mappings_list.delete(0, "end")
        for line in lines:
            self.mappings_list.insert("end", line)

    def get_ssid_input(self) -> str:
        return self.ssid_entry.get()

    def get_profile_combo(self) -> str:
        return self.profile_combo.get()

    def get_alias_input(self) -> str:
        return self.alias_entry.get()

    def get_username_input(self) -> str:
        return self.user_entry.get()

    def is_auto_enabled(self) -> bool:
        return self.wifi_auto_apply_var.get()

    def is_mapping_auto(self) -> bool:
        return self.wifi_mapping_auto_var.get()

    def get_selected_mapping_index(self) -> Optional[int]:
        sel = self.mappings_list.curselection()
        return sel[0] if sel else None

    def show_message(self, title: str, message: str) -> None:
        show_message(self.root, title, message, self.colors)

    def ask_yes_no(self, title: str, message: str) -> bool:
        return ask_yes_no(self.root, title, message, self.colors)

    def refresh_related_panels(self) -> None:
        pass  # wired by main_window

    def schedule_next_tick(self, interval_ms: int) -> None:
        self.root.after(interval_ms, self._on_tick)

    def set_profile_values(self, names: List[str]) -> None:
        """Update the profile combo values (called from main_window)."""
        self.profile_combo.configure(values=names if names else [""])
        current = self.profile_combo.get()
        if current not in names and names:
            self.profile_combo.set(names[0])

    # ── Event handlers ───────────────────────────────────────────

    def _on_select_visible(self, _event: object) -> None:
        sel = self.visible_list.curselection()
        if sel:
            value = self.visible_list.get(sel[0]).strip()
            if value and not value.startswith("("):
                self.ssid_entry.delete(0, "end")
                self.ssid_entry.insert(0, value)

    def _on_add(self) -> None:
        if self.presenter:
            self.presenter.add_mapping()

    def _on_remove(self) -> None:
        if self.presenter:
            self.presenter.remove_mapping()

    def _on_toggle_auto(self) -> None:
        if self.presenter:
            self.presenter.toggle_auto_apply(self.wifi_auto_apply_var.get())

    def _on_apply_mapping(self) -> None:
        if self.presenter:
            self.presenter.apply_selected_mapping()

    def _on_refresh_ssid(self) -> None:
        if self.presenter:
            self.presenter.refresh_current_ssid()

    def _on_refresh_visible(self) -> None:
        if self.presenter:
            self.presenter.refresh_visible_networks()

    def _on_tick(self) -> None:
        if self.presenter:
            self.presenter.tick()

    def update_colors(self, colors: dict) -> None:
        self.colors = colors
        self.visible_list.configure(bg=colors["list_bg"], fg=colors["text"], selectbackground=colors["accent"])
        self.mappings_list.configure(bg=colors["list_bg"], fg=colors["text"], selectbackground=colors["accent"])
