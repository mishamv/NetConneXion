"""Tools feature view — CTkTabview with 4 tabs.

Tabs: Подключения | Адаптеры | Консоль | Сканер
Each tab hosts a dedicated panel class. ThemeChanged events propagate
to all panels via update_colors().
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import customtkinter as ctk

from quickip.core.ui.theme import get_palette
from quickip.core.events.types import ThemeChanged
from quickip.features.tools.view.connections_panel import ConnectionsPanel
from quickip.features.tools.view.adapters_panel import AdaptersPanel
from quickip.features.tools.view.console_panel import ConsolePanel
from quickip.features.tools.view.scanner_panel import ScannerPanel

if TYPE_CHECKING:
    from quickip.features.tools.presenter import ToolsPresenter

logger = logging.getLogger(__name__)

_TABS = (
    ("Подключения", "connections"),
    ("Адаптеры",    "adapters"),
    ("Консоль",     "консоль"),
    ("Сканер",      "scanner"),
)


def _f(size: int, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(size=size, weight=weight)


class ToolsView(ctk.CTkFrame):
    """Top-level view for the Tools feature — four-tab layout."""

    def __init__(self, parent, presenter: "ToolsPresenter") -> None:
        super().__init__(parent, fg_color="transparent")
        self._presenter = presenter

        mode = ctk.get_appearance_mode().lower()
        self.colors = get_palette(mode)

        self._panels: list = []
        self._build()

        # Subscribe to theme changes
        try:
            container = presenter._container
            container.event_bus.subscribe(ThemeChanged, self._on_theme_changed)
        except Exception:
            pass

        presenter.bind_view(self)
        logger.debug("ToolsView initialised")

    # ── Layout ────────────────────────────────────────────────────

    def _build(self) -> None:
        c = self.colors

        ctk.CTkLabel(
            self, text="Инструменты", font=_f(20, "bold"),
            text_color=c["text"], anchor="w",
        ).pack(fill="x", padx=20, pady=(16, 8))

        self._tabs = ctk.CTkTabview(
            self,
            fg_color=c["card"],
            segmented_button_fg_color=c["card"],
            segmented_button_selected_color=c["primary"],
            segmented_button_selected_hover_color=c["hover"],
            segmented_button_unselected_color=c["card"],
            segmented_button_unselected_hover_color=c["border"],
            text_color=c["text"],
            text_color_disabled=c.get("text_secondary", c["text"]),
        )
        self._tabs.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        for label, _ in _TABS:
            self._tabs.add(label)

        p = self._presenter
        tab_frames = [self._tabs.tab(label) for label, _ in _TABS]
        for tf in tab_frames:
            tf.grid_rowconfigure(0, weight=1)
            tf.grid_columnconfigure(0, weight=1)

        self._conn_panel = ConnectionsPanel(tab_frames[0], c, p)
        self._conn_panel.grid(row=0, column=0, sticky="nsew")

        self._adapter_panel = AdaptersPanel(tab_frames[1], c, p)
        self._adapter_panel.grid(row=0, column=0, sticky="nsew")

        self._console_panel = ConsolePanel(tab_frames[2], c, p)
        self._console_panel.grid(row=0, column=0, sticky="nsew")

        self._scanner_panel = ScannerPanel(tab_frames[3], c, p)
        self._scanner_panel.grid(row=0, column=0, sticky="nsew")

        self._panels = [
            self._conn_panel,
            self._adapter_panel,
            self._console_panel,
            self._scanner_panel,
        ]

    # ── Theme ─────────────────────────────────────────────────────

    def _on_theme_changed(self, event: ThemeChanged) -> None:
        self.colors = get_palette(event.theme)
        self.update_colors(self.colors)

    def update_colors(self, colors: dict) -> None:
        self.colors = colors
        c = colors
        try:
            self._tabs.configure(
                fg_color=c["card"],
                segmented_button_fg_color=c["card"],
                segmented_button_selected_color=c["primary"],
                segmented_button_selected_hover_color=c["hover"],
                segmented_button_unselected_color=c["card"],
                segmented_button_unselected_hover_color=c["border"],
                text_color=c["text"],
            )
        except Exception:
            pass
        for panel in self._panels:
            try:
                panel.update_colors(colors)
            except Exception:
                pass

    # ── Lifecycle ─────────────────────────────────────────────────

    def on_hide(self) -> None:
        """Called by main window when switching away from this tab."""
        try:
            self._conn_panel.on_hide()
        except Exception:
            pass
