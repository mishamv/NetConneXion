"""Tools feature — adapters panel.

Left list of adapter names; right side shows collapsible detail sections
(IPv4, IPv6, DNS, gateway, MAC, speed/media, status).
"""

from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from typing import List, Optional, TYPE_CHECKING

import customtkinter as ctk

if TYPE_CHECKING:
    from quickip.features.tools.services.adapters import AdapterDetail
    from quickip.features.tools.presenter import ToolsPresenter

logger = logging.getLogger(__name__)


def _f(size: int, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(size=size, weight=weight)


class _DetailSection(ctk.CTkFrame):
    """Collapsible section showing a heading + rows of (label, value)."""

    def __init__(self, parent, title: str, colors: dict) -> None:
        c = colors
        super().__init__(
            parent,
            fg_color=c.get("card_inner", c["input_bg"]),
            border_width=1, border_color=c["border"], corner_radius=8,
        )
        self._colors = colors
        self._expanded = True

        self._header = ctk.CTkButton(
            self, text=f"▼  {title}", font=_f(12, "bold"),
            fg_color="transparent", hover_color=c["border"],
            text_color=c["text"], anchor="w", height=30,
            command=self._toggle,
        )
        self._header.pack(fill="x", padx=6, pady=(4, 2))

        self._body = ctk.CTkFrame(self, fg_color="transparent")
        self._body.pack(fill="x", padx=10, pady=(0, 6))
        self._body.grid_columnconfigure(1, weight=1)
        self._row_idx = 0

    def add_row(self, label: str, value: str) -> None:
        c = self._colors
        ctk.CTkLabel(
            self._body, text=label + ":", font=_f(11),
            text_color=c.get("text_secondary", c["text"]), anchor="w",
        ).grid(row=self._row_idx, column=0, sticky="w", padx=(0, 8), pady=1)
        ctk.CTkLabel(
            self._body, text=value or "—", font=_f(11),
            text_color=c["text"], anchor="w", wraplength=280,
        ).grid(row=self._row_idx, column=1, sticky="ew", pady=1)
        self._row_idx += 1

    def _toggle(self) -> None:
        self._expanded = not self._expanded
        title = self._header.cget("text")
        arrow = "▼" if self._expanded else "▶"
        self._header.configure(text=arrow + title[1:])
        if self._expanded:
            self._body.pack(fill="x", padx=10, pady=(0, 6))
        else:
            self._body.pack_forget()


class AdaptersPanel(ctk.CTkFrame):
    """Two-pane panel: adapter list on the left, details on the right."""

    def __init__(self, parent, colors: dict, presenter: "ToolsPresenter") -> None:
        super().__init__(parent, fg_color="transparent")
        self._colors = colors
        self._presenter = presenter
        self._adapters: List["AdapterDetail"] = []
        self._selected_name: Optional[str] = None
        self._fetch_queue: queue.Queue = queue.Queue(maxsize=1)
        self._build()

    # ── Layout ────────────────────────────────────────────────────

    def _build(self) -> None:
        c = self._colors
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ── Left list ─────────────────────────────────────────────
        left = ctk.CTkFrame(self, fg_color=c["card"], width=200, corner_radius=8)
        left.grid(row=0, column=0, sticky="nsew", padx=(8, 4), pady=8)
        left.grid_propagate(False)
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkFrame(left, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))

        ctk.CTkLabel(
            hdr, text="Адаптеры", font=_f(13, "bold"), text_color=c["text"],
        ).pack(side="left")

        ctk.CTkButton(
            hdr, text="↻", width=28, height=28, font=_f(14),
            fg_color="transparent", hover_color=c["border"],
            text_color=c["text"], command=self._refresh,
        ).pack(side="right")

        self._list_frame = ctk.CTkScrollableFrame(left, fg_color="transparent")
        self._list_frame.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 8))

        # ── Right detail ──────────────────────────────────────────
        right = ctk.CTkScrollableFrame(self, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=(4, 8), pady=8)
        right.grid_columnconfigure(0, weight=1)
        self._detail_frame = right

        self._placeholder = ctk.CTkLabel(
            self._detail_frame,
            text="Выберите адаптер для просмотра деталей",
            font=_f(13), text_color=c.get("text_secondary", c["text"]),
        )
        self._placeholder.grid(row=0, column=0, pady=40)

    # ── Data loading ──────────────────────────────────────────────

    def _refresh(self) -> None:
        """Start background fetch; poll queue on main thread."""
        try:
            self._fetch_queue.get_nowait()  # clear stale
        except queue.Empty:
            pass
        threading.Thread(target=self._fetch, daemon=True, name="adapters_fetch").start()
        self.after(300, self._check_fetch_result)

    def _fetch(self) -> None:
        """Background worker — only touches thread-safe queue."""
        try:
            adapters = self._presenter.fetch_adapters()
            try:
                self._fetch_queue.put_nowait(adapters)
            except queue.Full:
                pass
        except Exception:
            logger.exception("AdaptersPanel fetch error")

    def _check_fetch_result(self) -> None:
        """Main-thread poller: check queue every 300 ms."""
        try:
            adapters = self._fetch_queue.get_nowait()
            self._populate_list(adapters)
        except queue.Empty:
            self.after(300, self._check_fetch_result)  # still loading

    def _populate_list(self, adapters: List["AdapterDetail"]) -> None:
        self._adapters = adapters
        for w in self._list_frame.winfo_children():
            w.destroy()
        c = self._colors
        for ad in adapters:
            status_color = "#22C55E" if ad.is_up else "#6B7280"
            row = ctk.CTkFrame(
                self._list_frame,
                fg_color="transparent", corner_radius=6, cursor="hand2",
            )
            row.pack(fill="x", pady=1)
            indicator = ctk.CTkLabel(row, text="●", font=_f(10),
                                     text_color=status_color, width=14)
            indicator.pack(side="left", padx=(6, 2))
            lbl = ctk.CTkLabel(
                row, text=ad.name, font=_f(12),
                text_color=c["text"], anchor="w",
            )
            lbl.pack(side="left", fill="x", expand=True, pady=4, padx=(0, 6))
            for widget in (row, indicator, lbl):
                widget.bind("<Button-1>",
                            lambda _e, n=ad.name: self._select(n))

        if adapters:
            self._select(adapters[0].name)

    def _select(self, name: str) -> None:
        self._selected_name = name
        ad = next((a for a in self._adapters if a.name == name), None)
        if ad is None:
            return
        self._show_details(ad)

    def _show_details(self, ad: "AdapterDetail") -> None:
        for w in self._detail_frame.winfo_children():
            w.destroy()

        c = self._colors
        ctk.CTkLabel(
            self._detail_frame,
            text=ad.name, font=_f(16, "bold"), text_color=c["text"], anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=8, pady=(12, 4))

        ctk.CTkLabel(
            self._detail_frame,
            text=ad.description, font=_f(11),
            text_color=c.get("text_secondary", c["text"]), anchor="w",
        ).grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))

        sections = []

        # IPv4 section
        ip4 = _DetailSection(self._detail_frame, "IPv4", c)
        ip4.add_row("IP-адрес", ad.ipv4 or "—")
        ip4.add_row("Маска подсети", ad.subnet_mask or "—")
        ip4.add_row("Шлюз", ad.gateway or "—")
        ip4.add_row("CIDR", f"/{ad.prefix_length}" if ad.prefix_length else "—")
        ip4.add_row("Тип адреса", "DHCP" if ad.is_dhcp else "Статический")
        sections.append(ip4)

        # DNS section
        dns_sec = _DetailSection(self._detail_frame, "DNS", c)
        dns_sec.add_row("DNS-серверы", ad.dns or "—")
        sections.append(dns_sec)

        # IPv6 section
        ip6 = _DetailSection(self._detail_frame, "IPv6", c)
        ip6.add_row("IP-адрес", ad.ipv6 or "—")
        sections.append(ip6)

        # Physical section
        phy = _DetailSection(self._detail_frame, "Физические параметры", c)
        phy.add_row("MAC-адрес", ad.mac or "—")
        phy.add_row("Скорость", ad.speed or "—")
        phy.add_row("Тип сети", ad.media or "—")
        phy.add_row("Статус", ad.status or "—")
        sections.append(phy)

        for i, sec in enumerate(sections):
            sec.grid(row=i + 2, column=0, sticky="ew", padx=8, pady=(0, 6))
        self._detail_frame.grid_columnconfigure(0, weight=1)

    # ── Colors ────────────────────────────────────────────────────

    def update_colors(self, colors: dict) -> None:
        self._colors = colors
