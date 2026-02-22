"""Wi-Fi feature view — main layout per spec.

Layout:
  ┌──────────────────────────────────────────────────────────┐
  │  [Adapter]  [Status: Connected — SSID]  [Networks: N]   │
  │             [🔍 Scan] [Connect] [Disconnect]             │
  │  Search: [___________]                                   │
  ├──────────────────────────────────────────────────────────┤
  │  Networks table  (Signal | SSID | MAC | Enc | Ch | GHz) │
  ├──────────────────────────────────────────────────────────┤
  │  [Профили Wi-Fi] | [Параметры Wi-Fi]  (segmented btn)   │
  │  panel below (profiles or options)                       │
  └──────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk
from typing import List, Optional, TYPE_CHECKING

import customtkinter as ctk

from quickip.core.ui.theme import get_palette
from quickip.core.events.types import ThemeChanged
from quickip.features.wifi.repository import WifiNetworkSnapshot
from quickip.features.wifi.view.profiles_panel import ProfilesPanel
from quickip.features.wifi.view.options_panel import OptionsPanel

if TYPE_CHECKING:
    from quickip.features.wifi.presenter import WifiPresenter

logger = logging.getLogger(__name__)

_NET_COLS = ("signal", "ssid", "mac", "auth", "channel", "ghz", "mbps", "proto")
_NET_HEADS = {
    "signal": "Сигнал%", "ssid": "SSID", "mac": "MAC",
    "auth": "Шифрование", "channel": "Канал",
    "ghz": "ГГц", "mbps": "Мбит/с", "proto": "Протокол",
}
_NET_W = {
    "signal": 80, "ssid": 280, "mac": 160, "auth": 175,
    "channel": 75, "ghz": 85, "mbps": 85, "proto": 115,
}


def _f(size: int, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(size=size, weight=weight)


class WifiView(ctk.CTkFrame):
    """Top-level Wi-Fi view: status bar + network table + panel switcher."""

    def __init__(self, parent, presenter: "WifiPresenter") -> None:
        super().__init__(parent, fg_color="transparent")
        import queue
        self._presenter = presenter
        self._networks: List[WifiNetworkSnapshot] = []
        self._scan_queue: queue.Queue = queue.Queue(maxsize=1)

        mode = ctk.get_appearance_mode().lower()
        self.colors = get_palette(mode)
        self._build()

        try:
            container = presenter._container
            container.event_bus.subscribe(ThemeChanged, self._on_theme_changed)
        except Exception:
            pass

        presenter.bind_view(self)
        # Start status polling (needs tk root)
        self.after(100, lambda: presenter.start_status_polling(self.winfo_toplevel()))
        logger.debug("WifiView initialised")

    # ── Layout ────────────────────────────────────────────────────

    def _build(self) -> None:
        c = self.colors
        self.grid_rowconfigure(1, weight=0)
        self.grid_rowconfigure(3, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # ── Top bar ───────────────────────────────────────────────
        top = ctk.CTkFrame(
            self, fg_color=c.get("card_inner", c["input_bg"]),
            border_width=1, border_color=c["border"], corner_radius=8,
        )
        top.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        top.grid_columnconfigure(0, weight=1)

        info_row = ctk.CTkFrame(top, fg_color="transparent")
        info_row.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 4))
        info_row.grid_columnconfigure(1, weight=1)

        self._adapter_lbl = ctk.CTkLabel(
            info_row, text="Адаптер: —", font=_f(12), text_color=c["text"], anchor="w",
        )
        self._adapter_lbl.grid(row=0, column=0, sticky="w", padx=(0, 20))

        self._status_lbl = ctk.CTkLabel(
            info_row, text="Статус: —", font=_f(12, "bold"),
            text_color=c["text"], anchor="w",
        )
        self._status_lbl.grid(row=0, column=1, sticky="w")

        self._count_lbl = ctk.CTkLabel(
            info_row, text="Сетей: 0", font=_f(11),
            text_color=c.get("text_secondary", c["text"]), anchor="e",
        )
        self._count_lbl.grid(row=0, column=2, sticky="e", padx=(20, 0))

        btn_row = ctk.CTkFrame(top, fg_color="transparent")
        btn_row.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 8))

        self._scan_btn = ctk.CTkButton(
            btn_row, text="🔍 Сканировать", width=130, height=30, font=_f(12),
            fg_color=c["primary"], hover_color=c["hover"], text_color="#FFFFFF",
            command=self._scan,
        )
        self._scan_btn.pack(side="left", padx=(0, 8))

        self._connect_btn = ctk.CTkButton(
            btn_row, text="Подключить", width=110, height=30, font=_f(12),
            fg_color=c["primary"], hover_color=c["hover"], text_color="#FFFFFF",
            command=self._connect, state="disabled",
        )
        self._connect_btn.pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row, text="Отключить", width=100, height=30, font=_f(12),
            fg_color=c["card"], hover_color=c["border"], text_color=c["text"],
            border_width=1, border_color=c["border"],
            command=self._disconnect,
        ).pack(side="left", padx=(0, 20))

        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._apply_filter())
        ctk.CTkEntry(
            btn_row, textvariable=self._search_var,
            width=200, height=30, font=_f(12),
            fg_color=c["input_bg"], text_color=c["text"],
            border_color=c["border"], placeholder_text="Поиск по SSID…",
        ).pack(side="left")

        # ── Networks table ────────────────────────────────────────
        tree_wrap = tk.Frame(self, bg=c["list_bg"])
        tree_wrap.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 4))
        tree_wrap.grid_rowconfigure(0, weight=1)
        tree_wrap.grid_columnconfigure(0, weight=1)

        style = ttk.Style()
        style.configure(
            "Wifi.Treeview",
            background=c["list_bg"], foreground=c["list_text"],
            fieldbackground=c["list_bg"], rowheight=28,
            font=("Segoe UI", 13),
        )
        style.configure("Wifi.Treeview.Heading",
                         background=c["card"], foreground=c["text"],
                         font=("Segoe UI", 12, "bold"))
        style.map("Wifi.Treeview",
                  background=[("selected", c["list_selected_bg"])],
                  foreground=[("selected", c["list_selected_text"])])

        self._tree = ttk.Treeview(
            tree_wrap, columns=_NET_COLS, show="headings",
            style="Wifi.Treeview", selectmode="browse", height=12,
        )
        for col in _NET_COLS:
            self._tree.heading(col, text=_NET_HEADS[col])
            self._tree.column(
                col, width=_NET_W[col], minwidth=40,
                stretch=(col == "ssid"),
            )

        vsb = ttk.Scrollbar(tree_wrap, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        self._tree.tag_configure("green",  foreground="#22C55E")
        self._tree.tag_configure("yellow", foreground="#EAB308")
        self._tree.tag_configure("red",    foreground="#EF4444")
        self._tree.bind("<<TreeviewSelect>>", self._on_row_select)

        # ── Bottom panel switcher ─────────────────────────────────
        switcher_row = ctk.CTkFrame(self, fg_color="transparent")
        switcher_row.grid(row=2, column=0, sticky="ew", padx=8, pady=(4, 0))

        self._seg = ctk.CTkSegmentedButton(
            switcher_row,
            values=["Профили Wi-Fi", "Параметры Wi-Fi"],
            command=self._switch_panel,
            font=_f(12),
            fg_color=c["card"],
            selected_color=c["primary"],
            selected_hover_color=c["hover"],
            unselected_color=c["card"],
            unselected_hover_color=c["border"],
            text_color=c["text"],
        )
        self._seg.pack(fill="x")
        self._seg.set("Профили Wi-Fi")

        self._panel_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._panel_frame.grid(row=3, column=0, sticky="nsew", padx=0, pady=0)
        self._panel_frame.grid_rowconfigure(0, weight=1)
        self._panel_frame.grid_columnconfigure(0, weight=1)

        p = self._presenter
        self._profiles_panel = ProfilesPanel(self._panel_frame, self.colors, p)
        self._options_panel = OptionsPanel(self._panel_frame, self.colors, p)
        self._profiles_panel.grid(row=0, column=0, sticky="nsew")
        self._options_panel.grid(row=0, column=0, sticky="nsew")
        self._switch_panel("Профили Wi-Fi")

    # ── Tab lifecycle ─────────────────────────────────────────────

    def on_tab_enter(self) -> None:
        """Called when user navigates to this tab — trigger one auto-scan."""
        if self._scan_btn.cget("state") != "disabled":
            self._scan()

    # ── Actions ───────────────────────────────────────────────────

    def _scan(self) -> None:
        self._scan_btn.configure(state="disabled", text="⏳ Поиск…")
        # clear stale result
        try:
            self._scan_queue.get_nowait()
        except Exception:
            pass
        self._presenter.scan(callback=self._on_scan_done_bg)
        self._poll_scan_result()

    def _on_scan_done_bg(self, networks: List[WifiNetworkSnapshot]) -> None:
        """Called from background thread — only touches thread-safe queue."""
        try:
            self._scan_queue.put_nowait(networks)
        except Exception:
            pass

    def _poll_scan_result(self) -> None:
        """Main-thread poller: checks scan queue every 200 ms."""
        import queue as _queue
        try:
            networks = self._scan_queue.get_nowait()
            self._populate_networks(networks)
            return  # done
        except _queue.Empty:
            pass
        # Still waiting — reschedule if button still disabled
        if self._scan_btn.cget("state") == "disabled":
            self.after(200, self._poll_scan_result)

    def _populate_networks(self, networks: List[WifiNetworkSnapshot]) -> None:
        self._networks = networks
        self._scan_btn.configure(state="normal", text="🔍 Сканировать")
        self._count_lbl.configure(text=f"Сетей: {len(networks)}")
        self._apply_filter()

    def _apply_filter(self) -> None:
        q = self._search_var.get().lower()
        for iid in self._tree.get_children():
            self._tree.delete(iid)
        for net in self._networks:
            if q and q not in net.ssid.lower():
                continue
            tag = (
                "green" if net.signal_pct >= 70
                else "yellow" if net.signal_pct >= 40
                else "red"
            )
            ghz = f"{net.freq_ghz:.3f}" if net.freq_ghz else "—"
            mbps = str(net.mbps) if net.mbps else "—"
            self._tree.insert(
                "", "end",
                values=(
                    f"{net.signal_pct}%", net.ssid, net.bssid,
                    net.auth, net.channel, ghz, mbps, net.protocol,
                ),
                tags=(tag,),
            )

    def _on_row_select(self, _event: tk.Event) -> None:
        self._connect_btn.configure(state="normal" if self._tree.selection() else "disabled")

    def _connect(self) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        ssid = self._tree.item(sel[0], "values")[1]
        self._connect_btn.configure(state="disabled", text="⏳")
        self._presenter.connect(ssid, callback=self._on_connect_done)

    def _on_connect_done(self, success: bool, message: str) -> None:
        def _upd():
            self._connect_btn.configure(state="normal", text="Подключить")
        self.after(0, _upd)

    def _disconnect(self) -> None:
        self._presenter.disconnect()

    # ── Status update (called from presenter via root.after) ──────

    def update_status(self, status: dict) -> None:
        name = status.get("name", "—")
        ssid = status.get("ssid", "")
        state = status.get("state", "")
        signal = status.get("signal", 0)
        self._adapter_lbl.configure(text=f"Адаптер: {name}")
        if state.lower() == "connected":
            self._status_lbl.configure(
                text=f"✅ Подключено — {ssid} ({signal}%)",
                text_color="#22C55E",
            )
        else:
            self._status_lbl.configure(
                text=f"⭕ {state.capitalize() or 'Отключено'}",
                text_color=self.colors.get("text_secondary", self.colors["text"]),
            )

    # ── Panel switcher ────────────────────────────────────────────

    def _switch_panel(self, value: str) -> None:
        if value == "Профили Wi-Fi":
            self._profiles_panel.lift()
            self._options_panel.lower()
        else:
            self._options_panel.lift()
            self._profiles_panel.lower()

    # ── Theme ─────────────────────────────────────────────────────

    def _on_theme_changed(self, event: ThemeChanged) -> None:
        self.colors = get_palette(event.theme)
        self.update_colors(self.colors)

    def update_colors(self, colors: dict) -> None:
        self.colors = colors
        for panel in (self._profiles_panel, self._options_panel):
            try:
                panel.update_colors(colors)
            except Exception:
                pass
