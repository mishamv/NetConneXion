"""Wi-Fi feature — options panel.

Three checkboxes that map to WifiOptions fields, plus a Save button.

  ☑ Отключать Wi-Fi при подключении LAN
  ☐ Автоматически переключаться на более сильный сигнал того же SSID
  ☐ Включить журналирование Wi-Fi событий
  [Сохранить параметры]
"""

from __future__ import annotations

import logging
import tkinter as tk
from typing import TYPE_CHECKING

import customtkinter as ctk

if TYPE_CHECKING:
    from quickip.features.wifi.presenter import WifiPresenter

logger = logging.getLogger(__name__)


def _f(size: int, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(size=size, weight=weight)


class OptionsPanel(ctk.CTkFrame):
    """Wi-Fi options panel: three toggles + save."""

    def __init__(self, parent, colors: dict, presenter: "WifiPresenter") -> None:
        super().__init__(parent, fg_color="transparent")
        self._colors = colors
        self._presenter = presenter
        self._build()
        self.after(100, self._load)

    # ── Layout ────────────────────────────────────────────────────

    def _build(self) -> None:
        c = self._colors
        self.grid_columnconfigure(0, weight=1)

        card = ctk.CTkFrame(self, fg_color=c["card"], corner_radius=8)
        card.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card, text="Параметры Wi-Fi", font=_f(13, "bold"), text_color=c["text"],
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 6))

        # ── Checkboxes ────────────────────────────────────────────
        self._lan_var = tk.BooleanVar(value=False)
        self._roam_var = tk.BooleanVar(value=False)
        self._log_var = tk.BooleanVar(value=False)

        checks = [
            (self._lan_var,  "Отключать Wi-Fi при подключении LAN"),
            (self._roam_var, "Автоматически переключаться на более сильный сигнал того же SSID"),
            (self._log_var,  "Включить журналирование Wi-Fi событий"),
        ]
        for row_idx, (var, label) in enumerate(checks, start=1):
            ctk.CTkCheckBox(
                card,
                text=label,
                variable=var,
                font=_f(12),
                text_color=c["text"],
                fg_color=c.get("primary", c["text"]),
                hover_color=c.get("hover", c["border"]),
            ).grid(row=row_idx, column=0, sticky="w", padx=12, pady=4)

        # ── Save button + feedback label ──────────────────────────
        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.grid(row=4, column=0, sticky="w", padx=12, pady=(10, 8))

        ctk.CTkButton(
            btn_row,
            text="Сохранить параметры",
            width=160, height=32, font=_f(12),
            fg_color=c["primary"], hover_color=c["hover"], text_color="#FFFFFF",
            command=self._save,
        ).pack(side="left", padx=(0, 12))

        self._msg_lbl = ctk.CTkLabel(
            btn_row, text="", font=_f(11),
            text_color=c.get("text_secondary", c["text"]),
        )
        self._msg_lbl.pack(side="left")

    # ── Data ──────────────────────────────────────────────────────

    def _load(self) -> None:
        try:
            opts = self._presenter.load_options()
            self._lan_var.set(opts.disable_wifi_when_lan)
            self._roam_var.set(opts.roam_strongest_same_ssid)
            self._log_var.set(opts.enable_logging)
        except Exception:
            logger.exception("OptionsPanel._load error")

    def _save(self) -> None:
        from quickip.features.wifi.repository import WifiOptions
        try:
            opts = WifiOptions(
                disable_wifi_when_lan=self._lan_var.get(),
                roam_strongest_same_ssid=self._roam_var.get(),
                enable_logging=self._log_var.get(),
            )
            self._presenter.save_options(opts)
            self._msg_lbl.configure(
                text="Сохранено",
                text_color=self._colors.get("text_secondary", self._colors["text"]),
            )
        except Exception as exc:
            self._msg_lbl.configure(text=str(exc), text_color="#EF4444")

    # ── Colors ────────────────────────────────────────────────────

    def update_colors(self, colors: dict) -> None:
        self._colors = colors
