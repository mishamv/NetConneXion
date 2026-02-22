"""Profiles view – CTk widgets implementing ProfilesView protocol."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog
from typing import TYPE_CHECKING, List, Optional

try:
    import customtkinter as ctk
except ImportError:
    ctk = None  # type: ignore

from quickip.domain.models import Profile, IPMode, DNSMode
from quickip.ui.dialogs import show_message, ask_yes_no, ask_rename_action

if TYPE_CHECKING:
    from quickip.presenters.profiles_presenter import ProfilesPresenter


class ProfilesView:
    """
    Builds the network-profile tab widgets and implements the
    :class:`ProfilesPresenter.ProfilesView` protocol.
    """

    def __init__(self, parent: tk.Widget, colors: dict, root: tk.Widget) -> None:
        self.parent = parent
        self.colors = colors
        self.root = root  # top-level window for dialogs
        self.presenter: Optional[ProfilesPresenter] = None

        # Tk variables
        self.dhcp_ip = tk.BooleanVar(value=False)
        self.dhcp_dns = tk.BooleanVar(value=False)
        self.profile_search_var = tk.StringVar(value="")
        self.profile_adapter_filter_var = tk.StringVar(value="Все адаптеры")

        self._build(parent)

    def bind_presenter(self, presenter: "ProfilesPresenter") -> None:
        self.presenter = presenter

    # ── Build widgets ────────────────────────────────────────────

    def _build(self, parent: tk.Widget) -> None:
        """Build the three-tab network module (profile / summary / current)."""
        self.tabview = ctk.CTkTabview(parent, fg_color=self.colors["card"], corner_radius=8)
        self.tabview.pack(fill="both", expand=True)
        self.tabview.add("Профиль")
        self.tabview.add("Сводка")
        self.tabview.add("Текущая сеть")

        self._build_profile_tab(self.tabview.tab("Профиль"))
        self._build_summary_tab(self.tabview.tab("Сводка"))
        self._build_current_tab(self.tabview.tab("Текущая сеть"))

    def _build_profile_tab(self, tab: tk.Widget) -> None:
        tab.grid_columnconfigure(1, weight=1)
        tab.grid_rowconfigure(0, weight=1)

        # ── Left: profile list ───────────────────────────────────
        left = ctk.CTkFrame(tab, fg_color=self.colors["card"], width=260, corner_radius=0)
        left.grid(row=0, column=0, sticky="ns", padx=(0, 8))
        left.grid_propagate(False)

        # Search
        self.search_entry = ctk.CTkEntry(
            left, textvariable=self.profile_search_var,
            placeholder_text="Поиск профиля...", height=32, corner_radius=6,
            border_color=self.colors["border"], fg_color=self.colors["input_bg"],
            text_color=self.colors["text"],
        )
        self.search_entry.pack(fill="x", padx=8, pady=(8, 4))
        self.search_entry.bind("<KeyRelease>", lambda _: self._on_search())

        # Adapter filter
        self.profile_adapter_filter = ctk.CTkComboBox(
            left, state="readonly", values=["Все адаптеры"],
            variable=self.profile_adapter_filter_var, width=240, height=32,
            corner_radius=6, border_color=self.colors["border"],
            fg_color=self.colors["input_bg"],
            button_color=self.colors["combo_button"],
            button_hover_color=self.colors["combo_button_hover"],
            dropdown_fg_color=self.colors["card"],
            dropdown_hover_color="#EFF6FF",
            dropdown_text_color=self.colors["text"],
            text_color=self.colors["text"],
            text_color_disabled=self.colors["text"],
            command=lambda _: self._on_search(),
        )
        self.profile_adapter_filter.pack(fill="x", padx=8, pady=(0, 4))

        # Listbox
        list_holder = ctk.CTkFrame(left, fg_color="transparent")
        list_holder.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        self.profile_list = tk.Listbox(
            list_holder, bg=self.colors["list_bg"], fg=self.colors["text"],
            selectbackground=self.colors["accent"], selectforeground="#FFFFFF",
            font=("Segoe UI", 12), relief="flat", borderwidth=0,
            highlightthickness=0, exportselection=False,
        )
        self.profile_list.pack(side="left", fill="both", expand=True)
        scroll = ctk.CTkScrollbar(list_holder, orientation="vertical", command=self.profile_list.yview)
        self.profile_list.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.profile_list.bind("<<ListboxSelect>>", self._on_select)

        # Buttons
        btn_row = ctk.CTkFrame(left, fg_color="transparent")
        btn_row.pack(fill="x", padx=8, pady=(0, 8))
        for text, cmd in [
            ("＋", self._on_create),
            ("✕", self._on_delete),
            ("⧉", self._on_duplicate),
        ]:
            ctk.CTkButton(btn_row, text=text, width=50, height=32, command=cmd).pack(side="left", padx=(0, 4))

        ctk.CTkButton(btn_row, text="Импорт", width=70, height=32, command=self._on_import).pack(side="right", padx=(4, 0))
        ctk.CTkButton(btn_row, text="Экспорт", width=70, height=32, command=self._on_export).pack(side="right")

        # ── Right: form ──────────────────────────────────────────
        right = ctk.CTkFrame(tab, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_columnconfigure(1, weight=1)

        row = 0
        # Profile name
        ctk.CTkLabel(right, text="Имя профиля", text_color=self.colors["text"]).grid(row=row, column=0, sticky="w", padx=(8, 4), pady=4)
        self.name_entry = ctk.CTkEntry(right, height=34, corner_radius=6, border_color=self.colors["border"], fg_color=self.colors["input_bg"], text_color=self.colors["text"])
        self.name_entry.grid(row=row, column=1, sticky="ew", padx=(0, 8), pady=4)
        row += 1

        # Adapter combo
        ctk.CTkLabel(right, text="Адаптер", text_color=self.colors["text"]).grid(row=row, column=0, sticky="w", padx=(8, 4), pady=4)
        self.adapter_combo = ctk.CTkComboBox(
            right, state="readonly", values=["Ethernet", "Wi-Fi"], height=34,
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
        self.adapter_combo.grid(row=row, column=1, sticky="ew", padx=(0, 8), pady=4)
        row += 1

        # DHCP IP checkbox
        ctk.CTkCheckBox(right, text="DHCP (IP)", variable=self.dhcp_ip, command=self._toggle_ip_state).grid(row=row, column=0, columnspan=2, sticky="w", padx=8, pady=4)
        row += 1

        # IP fields
        for label_text, attr in [("IP адрес", "ip_entry"), ("Маска", "mask_entry"), ("Шлюз", "gw_entry")]:
            ctk.CTkLabel(right, text=label_text, text_color=self.colors["text"]).grid(row=row, column=0, sticky="w", padx=(8, 4), pady=4)
            entry = ctk.CTkEntry(right, height=34, corner_radius=6, border_color=self.colors["border"], fg_color=self.colors["input_bg"], text_color=self.colors["text"])
            entry.grid(row=row, column=1, sticky="ew", padx=(0, 8), pady=4)
            setattr(self, attr, entry)
            row += 1

        # DHCP DNS checkbox
        ctk.CTkCheckBox(right, text="DHCP (DNS)", variable=self.dhcp_dns, command=self._toggle_dns_state).grid(row=row, column=0, columnspan=2, sticky="w", padx=8, pady=4)
        row += 1

        # DNS fields
        for label_text, attr in [("DNS основной", "dns1_entry"), ("DNS альтернативный", "dns2_entry")]:
            ctk.CTkLabel(right, text=label_text, text_color=self.colors["text"]).grid(row=row, column=0, sticky="w", padx=(8, 4), pady=4)
            entry = ctk.CTkEntry(right, height=34, corner_radius=6, border_color=self.colors["border"], fg_color=self.colors["input_bg"], text_color=self.colors["text"])
            entry.grid(row=row, column=1, sticky="ew", padx=(0, 8), pady=4)
            setattr(self, attr, entry)
            row += 1

        # Action buttons
        action_row = ctk.CTkFrame(right, fg_color="transparent")
        action_row.grid(row=row, column=0, columnspan=2, sticky="ew", padx=8, pady=(12, 8))
        ctk.CTkButton(action_row, text="💾 Сохранить", height=36, command=self._on_save).pack(side="left", padx=(0, 8))
        ctk.CTkButton(action_row, text="▶ Применить", height=36, command=self._on_apply).pack(side="left")

    def _build_summary_tab(self, tab: tk.Widget) -> None:
        self.summary_text = ctk.CTkTextbox(tab, font=ctk.CTkFont(family="Consolas", size=12))
        self.summary_text.pack(fill="both", expand=True, padx=8, pady=8)

    def _build_current_tab(self, tab: tk.Widget) -> None:
        self.current_net_text = ctk.CTkTextbox(tab, font=ctk.CTkFont(family="Consolas", size=12))
        self.current_net_text.pack(fill="both", expand=True, padx=8, pady=8)

    # ── Toggle helpers ───────────────────────────────────────────

    def _toggle_ip_state(self) -> None:
        state = "disabled" if self.dhcp_ip.get() else "normal"
        for entry in (self.ip_entry, self.mask_entry, self.gw_entry):
            entry.configure(state=state)

    def _toggle_dns_state(self) -> None:
        state = "disabled" if self.dhcp_dns.get() else "normal"
        for entry in (self.dns1_entry, self.dns2_entry):
            entry.configure(state=state)

    # ── Protocol implementation ──────────────────────────────────

    def show_profiles_list(self, names: List[str], selected: Optional[str]) -> None:
        self.profile_list.delete(0, "end")
        for name in names:
            self.profile_list.insert("end", name)
        if selected and selected in names:
            idx = names.index(selected)
            self.profile_list.selection_set(idx)
            self.profile_list.see(idx)

    def load_profile_form(self, profile: Profile) -> None:
        self._set_entry(self.name_entry, profile.name)
        # Adapter
        adapters = self.presenter.get_adapters() if self.presenter else []
        if adapters:
            self.adapter_combo.configure(values=adapters)
        self.adapter_combo.set(profile.adapter or (adapters[0] if adapters else ""))

        self.dhcp_ip.set(profile.ip_mode == IPMode.DHCP)
        self._toggle_ip_state()
        self._set_entry(self.ip_entry, profile.ipv4 or "")
        self._set_entry(self.mask_entry, profile.mask or "")
        self._set_entry(self.gw_entry, profile.gateway or "")

        self.dhcp_dns.set(profile.dns_mode == DNSMode.DHCP)
        self._toggle_dns_state()
        self._set_entry(self.dns1_entry, profile.dns_primary or "")
        self._set_entry(self.dns2_entry, profile.dns_secondary or "")

        self._update_summary()

    def show_message(self, title: str, message: str) -> None:
        show_message(self.root, title, message, self.colors)

    def ask_yes_no(self, title: str, message: str) -> bool:
        return ask_yes_no(self.root, title, message, self.colors)

    def ask_rename_action(self, old_name: str, new_name: str) -> str:
        return ask_rename_action(self.root, old_name, new_name, self.colors)

    def get_adapter_filter(self) -> str:
        return self.profile_adapter_filter_var.get()

    def get_search_query(self) -> str:
        return self.profile_search_var.get()

    def update_adapter_filter_values(self, values: List[str]) -> None:
        self.profile_adapter_filter.configure(values=values)
        if self.profile_adapter_filter_var.get() not in values:
            self.profile_adapter_filter_var.set("Все адаптеры")

    def update_wifi_profile_combo(self, names: List[str]) -> None:
        # Delegated to main_window which holds the wifi view
        pass

    def refresh_related_panels(self) -> None:
        # Delegated to main_window
        pass

    # ── Form helpers ─────────────────────────────────────────────

    def _read_form(self) -> dict:
        return {
            "name": self.name_entry.get(),
            "adapter": self.adapter_combo.get(),
            "dhcp_ip": self.dhcp_ip.get(),
            "ip": self.ip_entry.get(),
            "mask": self.mask_entry.get(),
            "gateway": self.gw_entry.get(),
            "dhcp_dns": self.dhcp_dns.get(),
            "dns_primary": self.dns1_entry.get(),
            "dns_secondary": self.dns2_entry.get(),
        }

    def _update_summary(self) -> None:
        if not self.presenter:
            return
        text = self.presenter.get_summary_text(self._read_form())
        self.summary_text.delete("1.0", "end")
        self.summary_text.insert("end", text)

    @staticmethod
    def _set_entry(entry: tk.Widget, value: str) -> None:
        state = str(entry.cget("state"))
        if state == "disabled":
            entry.configure(state="normal")
            entry.delete(0, "end")
            entry.insert(0, value)
            entry.configure(state="disabled")
        else:
            entry.delete(0, "end")
            entry.insert(0, value)

    # ── Event handlers ───────────────────────────────────────────

    def _on_search(self) -> None:
        if self.presenter:
            self.presenter.refresh_list()

    def _on_select(self, _event: object) -> None:
        sel = self.profile_list.curselection()
        if sel and self.presenter:
            name = self.profile_list.get(sel[0])
            self.presenter.on_select(name)
            self._update_summary()

    def _on_create(self) -> None:
        if self.presenter:
            self.presenter.create_profile()

    def _on_delete(self) -> None:
        sel = self.profile_list.curselection()
        if sel and self.presenter:
            name = self.profile_list.get(sel[0])
            self.presenter.delete_profile(name)

    def _on_duplicate(self) -> None:
        sel = self.profile_list.curselection()
        if sel and self.presenter:
            name = self.profile_list.get(sel[0])
            self.presenter.duplicate_profile(name)

    def _on_save(self) -> None:
        if self.presenter:
            self.presenter.save_profile(self._read_form())
            self._update_summary()

    def _on_apply(self) -> None:
        if self.presenter:
            self.presenter.apply_profile(self._read_form())

    def _on_export(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if path and self.presenter:
            self.presenter.export_profiles(path)

    def _on_import(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json"), ("All files", "*.*")])
        if path and self.presenter:
            self.presenter.import_profiles(path)

    # ── Theme update ─────────────────────────────────────────────

    def update_colors(self, colors: dict) -> None:
        """Re-apply colours after theme switch."""
        self.colors = colors
        # Update listbox colours
        self.profile_list.configure(bg=colors["list_bg"], fg=colors["text"], selectbackground=colors["accent"])
